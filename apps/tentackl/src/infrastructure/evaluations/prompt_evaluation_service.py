# REVIEW: Owns Redis and DB clients with manual lifecycle; errors can leave
# REVIEW: clients open.
# REVIEW: Default model hard-coded here and in API helpers; risk of drift.
"""
Prompt Evaluation Service

Service for evaluating prompts using LLM-as-judge methodology with rubric scoring.
Integrates with workflow and agent publishing to act as a CI/CD quality gate.

Features:
- LLM-as-judge evaluation with 6 dimensions
- Redis caching with hash-based invalidation (7-day TTL)
- Cache key: SHA256 of (prompt + threshold + prompt_type + model)

Usage:
    async with PromptEvaluationService() as eval_service:
        result = await eval_service.evaluate_prompt("Your prompt here")
        if not result.passed:
            print(f"Failed: {result.justification}")
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from uuid import UUID
import asyncio
import uuid
import json
import re
import yaml
import hashlib
import structlog
import redis.asyncio as redis_async

from src.llm.openrouter_client import OpenRouterClient
from src.interfaces.database import Database
from src.database.evaluation_models import (
    PromptEvaluation,
    PromptEvaluationType,
    PromptEvaluationResult,
)
from src.interfaces.llm import LLMMessage
from src.evaluation.rubrics import (
    EvaluationConfig,
    EvaluationResult,
    EvaluationRubric,
    EvaluationStatus,
    DimensionScore,
    PromptType,
    STANDARD_RUBRICS,
    calculate_weighted_score,
    determine_evaluation_status,
)
from src.core.config import settings

logger = structlog.get_logger(__name__)


# System prompt for the evaluation agent
EVALUATION_SYSTEM_PROMPT = """You are an expert prompt evaluator specializing in LLM prompt engineering. Your task is to assess prompts using a rubric-based scoring system and provide actionable feedback.

**Evaluation Dimensions (1-5 scale each):**

1. **Clarity** - Is the prompt clear and unambiguous?
   - 5: Crystal clear, no ambiguity whatsoever
   - 4: Very clear with minor ambiguities
   - 3: Generally clear but some parts unclear
   - 2: Confusing in several places
   - 1: Extremely unclear or contradictory

2. **Specificity** - Are instructions specific enough?
   - 5: Highly specific with exact requirements
   - 4: Specific with minor gaps
   - 3: Moderately specific
   - 2: Vague in key areas
   - 1: No specific guidance

3. **Safety** - Does it avoid encouraging harmful outputs?
   - 5: Explicitly guards against harmful outputs with clear boundaries
   - 4: Generally safe with minor concerns
   - 3: Neutral - no explicit safety considerations
   - 2: Could potentially lead to harmful outputs
   - 1: Actively encourages or lacks guardrails for harmful outputs

4. **Output Format** - Does it specify expected output format?
   - 5: Exact format specified with examples
   - 4: Format clearly described
   - 3: Format mentioned but not detailed
   - 2: Format implied but unclear
   - 1: No format guidance

5. **Context** - Does it provide sufficient context?
   - 5: Complete context with background, purpose, and constraints
   - 4: Good context with minor gaps
   - 3: Basic context provided
   - 2: Insufficient context
   - 1: No context provided

6. **Constraints** - Are constraints clearly stated?
   - 5: All constraints explicit with clear boundaries
   - 4: Most constraints clear
   - 3: Some constraints mentioned
   - 2: Few constraints specified
   - 1: No constraints defined

**Pass/Fail Criteria:**
- **PASS**: Overall score >= {threshold} AND no dimension score < 2
- **PASS_WITH_WARNINGS**: Overall score >= {threshold} but has dimension scores of 2
- **FAIL**: Overall score < {threshold} OR any dimension score = 1 OR safety score < 3

**CRITICAL: You MUST return ONLY valid JSON matching this exact schema:**

{{
  "evaluation_result": "pass" | "pass_with_warnings" | "fail",
  "dimension_scores": {{
    "clarity": {{"score": 1-5, "feedback": "explanation"}},
    "specificity": {{"score": 1-5, "feedback": "explanation"}},
    "safety": {{"score": 1-5, "feedback": "explanation"}},
    "output_format": {{"score": 1-5, "feedback": "explanation"}},
    "context": {{"score": 1-5, "feedback": "explanation"}},
    "constraints": {{"score": 1-5, "feedback": "explanation"}}
  }},
  "overall_score": 1.0-5.0,
  "passed": true | false,
  "justification": "Clear explanation of the decision",
  "improvement_suggestions": [
    {{"dimension": "name", "suggestion": "specific improvement", "priority": "high" | "medium" | "low"}}
  ]
}}

**Important Guidelines:**
- Be objective and consistent in your scoring
- Provide specific, actionable feedback for each dimension
- Don't inflate scores - be realistic and constructive
- For system prompts: emphasize safety and clarity
- For agent prompts: emphasize specificity and output format
- Always suggest improvements, even for passing prompts
- Return ONLY the JSON object, no other text"""


class PromptEvaluationService:
    """
    Service for evaluating prompts using LLM-as-judge methodology.

    This service runs prompts through an LLM judge to assess quality
    across multiple dimensions and provide pass/fail decisions.

    Features:
    - Caches results with 7-day TTL and hash-based invalidation
    - First call: ~2-5 seconds (LLM API call)
    - Subsequent identical calls: ~10ms (Redis lookup)
    """

    # Redis DB for evaluation cache (using DB 14 as per plan)
    CACHE_DB = 14
    CACHE_PREFIX = "eval:"
    CACHE_TTL_SECONDS = 86400 * 7  # 7 days
    # Cache version - bump this when rubrics or evaluation logic changes
    CACHE_VERSION = "v1"

    # Score conversion helpers (DB stores integers, API uses floats)
    @staticmethod
    def _score_to_db(score: float) -> int:
        """Convert 1.0-5.0 float score to integer (multiply by 100)."""
        return round(score * 100)

    @staticmethod
    def _score_from_db(score: int) -> float:
        """Convert integer back to 1.0-5.0 float."""
        return score / 100.0

    def __init__(
        self,
        llm_client: Optional[OpenRouterClient] = None,
        default_model: str = "google/gemini-2.5-flash-preview",
        enable_cache: bool = True,
        enable_db_persistence: bool = True,
    ):
        """
        Initialize the evaluation service.

        Args:
            llm_client: Optional LLM client. If not provided, one will be created.
            default_model: Default model to use for evaluation.
            enable_cache: Whether to enable Redis caching (default: True).
            enable_db_persistence: Whether to persist results to database (default: True).
        """
        self.llm_client = llm_client
        self.default_model = default_model
        self.enable_cache = enable_cache
        self.enable_db_persistence = enable_db_persistence
        self._owns_client = False
        self._redis_client: Optional[redis_async.Redis] = None
        self._db: Optional[Database] = None

    def _generate_cache_key(self, prompt: str, config: EvaluationConfig) -> str:
        """
        Generate deterministic cache key using SHA256.

        Key components:
        - cache version (for invalidation on rubric/logic changes)
        - prompt text
        - threshold
        - prompt_type
        - model

        Returns:
            Cache key in format: eval:<sha256_hash>
        """
        key_data = json.dumps({
            "version": self.CACHE_VERSION,  # Include version for invalidation
            "prompt": prompt,
            "threshold": config.threshold,
            "prompt_type": config.prompt_type.value,
            "model": config.model or self.default_model,
        }, sort_keys=True)
        hash_digest = hashlib.sha256(key_data.encode()).hexdigest()
        return f"{self.CACHE_PREFIX}{hash_digest}"

    async def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached evaluation result from Redis."""
        if not self.enable_cache or not self._redis_client:
            return None

        try:
            cached = await self._redis_client.get(cache_key)
            if cached:
                logger.debug("Cache hit", cache_key=cache_key[:24])
                return json.loads(cached)
            return None
        except Exception as e:
            logger.warning("Cache get error", error=str(e), cache_key=cache_key[:24])
            return None

    async def _set_cached_result(self, cache_key: str, result_data: Dict[str, Any]) -> None:
        """Store evaluation result in Redis with TTL."""
        if not self.enable_cache or not self._redis_client:
            return

        try:
            # Set with 7-day TTL to prevent unbounded cache growth
            await self._redis_client.set(
                cache_key,
                json.dumps(result_data),
                ex=self.CACHE_TTL_SECONDS
            )
            logger.debug("Cache set", cache_key=cache_key[:24], ttl_days=7)
        except Exception as e:
            logger.warning("Cache set error", error=str(e), cache_key=cache_key[:24])

    async def _persist_to_db(
        self,
        prompt_text: str,
        result: EvaluationResult,
        prompt_path: Optional[str] = None,
        task_id: Optional[UUID] = None,
        agent_spec_id: Optional[UUID] = None,
    ) -> None:
        """
        Persist evaluation result to database.

        Args:
            prompt_text: The evaluated prompt text.
            result: The evaluation result.
            prompt_path: Optional path/location identifier for the prompt.
            task_id: Optional task ID if evaluating a task prompt.
            agent_spec_id: Optional agent spec ID if evaluating an agent prompt.
        """
        if not self.enable_db_persistence or not self._db:
            return

        try:
            # Map prompt_type string to enum
            prompt_type_map = {
                "system_prompt": PromptEvaluationType.SYSTEM_PROMPT,
                "agent_prompt": PromptEvaluationType.AGENT_PROMPT,
                "workflow_prompt": PromptEvaluationType.WORKFLOW_PROMPT,
                "general": PromptEvaluationType.GENERAL,
            }
            prompt_type = prompt_type_map.get(
                result.prompt_type, PromptEvaluationType.GENERAL
            )

            # Map evaluation status to result enum
            result_map = {
                "pass": PromptEvaluationResult.PASS,
                "pass_with_warnings": PromptEvaluationResult.PASS_WITH_WARNINGS,
                "fail": PromptEvaluationResult.FAIL,
            }
            eval_result = result_map.get(
                result.evaluation_result.value, PromptEvaluationResult.FAIL
            )

            # Serialize dimension scores for JSON storage
            dimension_scores_json = {}
            for dim_name, dim_score in result.dimension_scores.items():
                dimension_scores_json[dim_name] = {
                    "score": dim_score.score,
                    "feedback": dim_score.feedback,
                    "weight": dim_score.weight,
                }

            # Create the model instance with integer-converted scores
            evaluation = PromptEvaluation(
                prompt_text=prompt_text[:10000],  # Truncate if too long
                prompt_type=prompt_type,
                prompt_path=prompt_path,
                task_id=task_id,
                agent_spec_id=agent_spec_id,
                evaluation_result=eval_result,
                overall_score=self._score_to_db(result.overall_score),
                dimension_scores=dimension_scores_json,
                justification=result.justification,
                improvement_suggestions=result.improvement_suggestions,
                threshold=self._score_to_db(result.threshold),
                model_used=self.default_model,
            )

            async with self._db.get_session() as session:
                session.add(evaluation)
                await session.commit()
                logger.debug(
                    "Evaluation persisted to DB",
                    evaluation_id=str(evaluation.id),
                    passed=result.passed
                )

        except Exception as e:
            # Don't fail the evaluation if persistence fails
            logger.warning("Failed to persist evaluation to DB", error=str(e))

    async def __aenter__(self):
        """Async context manager entry - initialize the LLM client, Redis, and DB."""
        if not self.llm_client:
            self.llm_client = OpenRouterClient()
            self._owns_client = True
            await self.llm_client.__aenter__()

        # Initialize Redis cache connection
        if self.enable_cache:
            try:
                self._redis_client = await redis_async.from_url(
                    settings.REDIS_URL,
                    db=self.CACHE_DB,
                    decode_responses=True
                )
                await self._redis_client.ping()
                logger.info("Evaluation cache connected", db=self.CACHE_DB)
            except Exception as e:
                logger.warning("Cache initialization failed, continuing without cache", error=str(e))
                self._redis_client = None

        # Initialize database connection for persistence
        if self.enable_db_persistence:
            try:
                self._db = Database()
                logger.info("Evaluation DB persistence enabled")
            except Exception as e:
                logger.warning("DB initialization failed, continuing without persistence", error=str(e))
                self._db = None

        logger.info(
            "PromptEvaluationService initialized",
            model=self.default_model,
            cache_enabled=self.enable_cache and self._redis_client is not None,
            db_enabled=self.enable_db_persistence and self._db is not None
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources."""
        if self._owns_client and self.llm_client:
            await self.llm_client.__aexit__(exc_type, exc_val, exc_tb)

        if self._redis_client:
            await self._redis_client.aclose()
            logger.debug("Evaluation cache disconnected")

        logger.info("PromptEvaluationService cleaned up")

    def _serialize_result(self, result: EvaluationResult) -> Dict[str, Any]:
        """Serialize EvaluationResult for caching."""
        dimension_scores_data = {}
        for dim_name, dim_score in result.dimension_scores.items():
            dimension_scores_data[dim_name] = {
                "score": dim_score.score,
                "feedback": dim_score.feedback,
                "weight": dim_score.weight
            }

        return {
            "evaluation_id": result.evaluation_id,
            "passed": result.passed,
            "evaluation_result": result.evaluation_result.value,
            "overall_score": result.overall_score,
            "dimension_scores": dimension_scores_data,
            "justification": result.justification,
            "improvement_suggestions": result.improvement_suggestions,
            "prompt_type": result.prompt_type,
            "threshold": result.threshold,
            "can_override": result.can_override
        }

    def _deserialize_result(self, data: Dict[str, Any]) -> EvaluationResult:
        """Deserialize cached data to EvaluationResult."""
        dimension_scores = {}
        for dim_name, dim_data in data.get("dimension_scores", {}).items():
            dimension_scores[dim_name] = DimensionScore(
                score=dim_data["score"],
                feedback=dim_data["feedback"],
                weight=dim_data["weight"]
            )

        return EvaluationResult(
            evaluation_id=data["evaluation_id"],
            passed=data["passed"],
            evaluation_result=EvaluationStatus(data["evaluation_result"]),
            overall_score=data["overall_score"],
            dimension_scores=dimension_scores,
            justification=data["justification"],
            improvement_suggestions=data["improvement_suggestions"],
            prompt_type=data["prompt_type"],
            threshold=data["threshold"],
            can_override=data["can_override"]
        )

    async def evaluate_prompt(
        self,
        prompt: str,
        config: Optional[EvaluationConfig] = None,
    ) -> EvaluationResult:
        """
        Evaluate a single prompt using LLM-as-judge.

        Results are cached indefinitely using hash-based invalidation.
        Cache key: SHA256(prompt + threshold + prompt_type + model)

        Args:
            prompt: The prompt text to evaluate.
            config: Optional evaluation configuration.

        Returns:
            EvaluationResult with scores, pass/fail decision, and feedback.
        """
        config = config or EvaluationConfig()

        # Check cache first
        cache_key = self._generate_cache_key(prompt, config)
        cached_data = await self._get_cached_result(cache_key)
        if cached_data:
            logger.info(
                "Returning cached evaluation result",
                cache_key=cache_key[:24],
                cached_score=cached_data.get("overall_score")
            )
            return self._deserialize_result(cached_data)

        evaluation_id = str(uuid.uuid4())

        logger.info(
            "Evaluating prompt (cache miss)",
            evaluation_id=evaluation_id,
            prompt_type=config.prompt_type.value,
            threshold=config.threshold,
            model=config.model or self.default_model
        )

        try:
            # Build the evaluation request
            system_prompt = EVALUATION_SYSTEM_PROMPT.format(threshold=config.threshold)

            user_message = f"""Evaluate the following prompt:

**Prompt Type:** {config.prompt_type.value}
**Pass Threshold:** {config.threshold}

**Prompt to Evaluate:**
```
{prompt}
```

Return your evaluation as valid JSON."""

            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_message),
            ]

            # Call the LLM
            model = config.model or self.default_model
            response = await self.llm_client.create_completion(
                messages=messages,
                model=model,
                temperature=0.1,  # Low temperature for consistent scoring
                max_tokens=2000,
            )

            # Parse the response
            content = response.content.strip()

            # Try to extract JSON from the response
            result_data = self._parse_json_response(content)

            # Build the evaluation result
            dimension_scores = {}
            raw_scores = {}

            for dim_name, dim_data in result_data.get("dimension_scores", {}).items():
                if isinstance(dim_data, dict):
                    score = dim_data.get("score", 3)
                    feedback = dim_data.get("feedback", "")
                else:
                    score = dim_data if isinstance(dim_data, int) else 3
                    feedback = ""

                dimension_scores[dim_name] = DimensionScore(
                    score=score,
                    feedback=feedback,
                    weight=self._get_dimension_weight(dim_name, config)
                )
                raw_scores[dim_name] = score

            # Calculate overall score
            rubric = config.get_rubric()
            overall_score = result_data.get("overall_score")
            if overall_score is None:
                overall_score = calculate_weighted_score(raw_scores, rubric)

            # Determine status
            status = determine_evaluation_status(
                overall_score=overall_score,
                dimension_scores=raw_scores,
                rubric=rubric,
                config=config
            )

            passed = status == EvaluationStatus.PASS

            # Check if override is allowed
            can_override = True
            safety_score = raw_scores.get("safety", 5)
            if safety_score < config.fail_on_safety_below:
                can_override = False  # Cannot override safety failures

            result = EvaluationResult(
                evaluation_id=evaluation_id,
                passed=passed,
                evaluation_result=status,
                overall_score=overall_score,
                dimension_scores=dimension_scores,
                justification=result_data.get("justification", ""),
                improvement_suggestions=result_data.get("improvement_suggestions", []),
                prompt_type=config.prompt_type.value,
                threshold=config.threshold,
                can_override=can_override
            )

            # Cache the result
            await self._set_cached_result(cache_key, self._serialize_result(result))

            # Persist to database
            await self._persist_to_db(prompt_text=prompt, result=result)

            logger.info(
                "Prompt evaluation complete",
                evaluation_id=evaluation_id,
                passed=passed,
                status=status.value,
                overall_score=overall_score,
                cached=True,
                persisted=self.enable_db_persistence and self._db is not None
            )

            return result

        except Exception as e:
            logger.error(
                "Prompt evaluation failed",
                evaluation_id=evaluation_id,
                error=str(e)
            )
            # Return a failed result on error
            return EvaluationResult(
                evaluation_id=evaluation_id,
                passed=False,
                evaluation_result=EvaluationStatus.FAIL,
                overall_score=0.0,
                dimension_scores={},
                justification=f"Evaluation failed with error: {str(e)}",
                improvement_suggestions=[],
                prompt_type=config.prompt_type.value,
                threshold=config.threshold,
                can_override=True
            )

    async def evaluate_agent_spec_prompt(
        self,
        yaml_content: str,
        config: Optional[EvaluationConfig] = None,
    ) -> EvaluationResult:
        """
        Evaluate the system prompt from an agent specification.

        Args:
            yaml_content: The agent YAML content.
            config: Optional evaluation configuration.

        Returns:
            EvaluationResult for the agent's system prompt.
        """
        config = config or EvaluationConfig(prompt_type=PromptType.AGENT_PROMPT)

        try:
            spec = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            logger.error("Invalid agent YAML", error=str(e))
            return EvaluationResult(
                evaluation_id=str(uuid.uuid4()),
                passed=False,
                evaluation_result=EvaluationStatus.FAIL,
                overall_score=0.0,
                dimension_scores={},
                justification=f"Invalid YAML: {str(e)}",
                improvement_suggestions=[],
                prompt_type=config.prompt_type.value,
                threshold=config.threshold,
                can_override=True
            )

        # Extract system prompt from agent config
        agent_config = spec.get("agent", {})
        state_schema = agent_config.get("state_schema", {})
        llm_config = state_schema.get("config", {})
        system_prompt = llm_config.get("system_prompt", "")

        if not system_prompt:
            # No prompt to evaluate - pass by default
            return EvaluationResult(
                evaluation_id=str(uuid.uuid4()),
                passed=True,
                evaluation_result=EvaluationStatus.PASS,
                overall_score=5.0,
                dimension_scores={},
                justification="No system prompt found in agent spec - skipping evaluation",
                improvement_suggestions=[],
                prompt_type=config.prompt_type.value,
                threshold=config.threshold,
                can_override=True
            )

        # Use agent_prompt type for higher threshold
        eval_config = EvaluationConfig(
            threshold=config.threshold or 3.5,  # Higher default for agents
            prompt_type=PromptType.AGENT_PROMPT,
            model=config.model
        )

        return await self.evaluate_prompt(prompt=system_prompt, config=eval_config)

    async def evaluate_workflow_spec_prompts(
        self,
        yaml_content: str,
        config: Optional[EvaluationConfig] = None,
    ) -> Dict[str, EvaluationResult]:
        """
        Evaluate all non-template prompts found in a workflow YAML spec.

        Returns a map of `path -> EvaluationResult`.
        """
        base_config = config or EvaluationConfig(prompt_type=PromptType.WORKFLOW_PROMPT)

        try:
            spec = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError as exc:
            logger.error("Invalid workflow YAML", error=str(exc))
            return {}

        prompt_fields = {"prompt", "system_prompt"}
        discovered: List[tuple[str, str]] = []

        def _walk(value: Any, path: str) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    child_path = f"{path}.{key}" if path else key
                    if (
                        key in prompt_fields
                        and isinstance(child, str)
                        and child.strip()
                        and not self._is_template_reference(child.strip())
                    ):
                        discovered.append((child_path, child))
                    _walk(child, child_path)
                return

            if isinstance(value, list):
                for index, child in enumerate(value):
                    child_path = f"{path}[{index}]"
                    _walk(child, child_path)

        _walk(spec, "")

        results: Dict[str, EvaluationResult] = {}
        for prompt_path, prompt_text in discovered:
            eval_config = EvaluationConfig(
                threshold=base_config.threshold,
                rubric_name=base_config.rubric_name,
                custom_rubric=base_config.custom_rubric,
                prompt_type=PromptType.WORKFLOW_PROMPT,
                model=base_config.model,
                fail_on_safety_below=base_config.fail_on_safety_below,
            )
            results[prompt_path] = await self.evaluate_prompt(
                prompt=prompt_text,
                config=eval_config,
            )

        return results

    # Regex to match JSON objects (handles nested braces)
    _JSON_OBJECT_PATTERN = re.compile(
        r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        re.DOTALL
    )

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response, handling markdown wrapping.

        Handles common LLM response formats:
        - Raw JSON
        - JSON wrapped in ```json ... ``` code blocks
        - JSON wrapped in ``` ... ``` code blocks
        - JSON embedded in prose text

        Args:
            content: The LLM response content

        Returns:
            Parsed JSON as dict, or empty dict if parsing fails
        """
        # Try direct parse first (most efficient path)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Strip markdown code blocks
        clean = re.sub(r'```(?:json)?\n?', '', content).strip()
        clean = clean.rstrip('`')

        # Try parsing the cleaned content
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            pass

        # Find first JSON object in content
        match = self._JSON_OBJECT_PATTERN.search(clean)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse JSON response", content=content[:100])
        return {}

    def _is_template_reference(self, value: str) -> bool:
        """Check if a value is a template reference."""
        return (
            value.startswith("${") or
            value.startswith("${{") or
            "${node." in value or
            "${parameters." in value or
            "${{node." in value or
            "${{parameters." in value
        )

    def _get_dimension_weight(self, dim_name: str, config: EvaluationConfig) -> float:
        """Get the weight for a dimension from the rubric."""
        rubric = config.get_rubric()
        for dim in rubric.dimensions:
            if dim.name == dim_name:
                return dim.weight
        return 1.0
