"""
Data models for the Prompt Evaluation and Optimization System.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4


class PatternType(str, Enum):
    """Types of output patterns to match."""

    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    REGEX = "regex"
    JSON_PATH = "json_path"
    CUSTOM_VALIDATOR = "custom_validator"


class Severity(str, Enum):
    """Severity levels for validation violations."""

    ERROR = "error"
    WARNING = "warning"


class OutputType(str, Enum):
    """Expected output format types."""

    JSON = "json"
    YAML = "yaml"
    TEXT = "text"
    MARKDOWN = "markdown"


@dataclass
class OutputPattern:
    """
    Expected pattern in the output.

    Used to verify that LLM output contains (or doesn't contain)
    specific patterns, either as literal strings or regex.
    """

    pattern_type: Literal["contains", "regex", "not_contains", "json_path", "custom_validator"]
    pattern: str
    description: str
    weight: float = 1.0
    validator: Optional[str] = None  # For custom_validator type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_type": self.pattern_type,
            "pattern": self.pattern,
            "description": self.description,
            "weight": self.weight,
            "validator": self.validator,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutputPattern":
        return cls(
            pattern_type=data["pattern_type"],
            pattern=data["pattern"],
            description=data.get("description", ""),
            weight=data.get("weight", 1.0),
            validator=data.get("validator"),
        )


@dataclass
class TemplateSyntaxRule:
    """
    Rule for validating template syntax in LLM outputs.

    Used to enforce correct template syntax like {{step_X.outputs.field}}.
    """

    name: str
    valid_patterns: List[str]  # Regex patterns that are valid
    invalid_patterns: List[str]  # Regex patterns that should NOT appear
    error_message: str
    severity: Literal["error", "warning"] = "error"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "valid_patterns": self.valid_patterns,
            "invalid_patterns": self.invalid_patterns,
            "error_message": self.error_message,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemplateSyntaxRule":
        return cls(
            name=data["name"],
            valid_patterns=data.get("valid_patterns", []),
            invalid_patterns=data.get("invalid_patterns", []),
            error_message=data["error_message"],
            severity=data.get("severity", "error"),
        )


@dataclass
class FormatRequirements:
    """
    Structural format requirements for LLM output.

    Specifies expected output type, JSON schema, template syntax rules,
    and other format constraints.
    """

    expected_type: Literal["json", "yaml", "text", "markdown"] = "json"
    json_schema: Optional[Dict[str, Any]] = None
    template_syntax_rules: Optional[List[TemplateSyntaxRule]] = None
    max_length: Optional[int] = None
    required_fields: Optional[List[str]] = None
    validate_agent_types: bool = False  # Validate agent_type values against allowed list
    validate_output_fields: bool = False  # Validate output fields match agent type

    def to_dict(self) -> Dict[str, Any]:
        result = {"expected_type": self.expected_type}
        if self.json_schema:
            result["json_schema"] = self.json_schema
        if self.template_syntax_rules:
            result["template_syntax_rules"] = [r.to_dict() for r in self.template_syntax_rules]
        if self.max_length:
            result["max_length"] = self.max_length
        if self.required_fields:
            result["required_fields"] = self.required_fields
        if self.validate_agent_types:
            result["validate_agent_types"] = self.validate_agent_types
        if self.validate_output_fields:
            result["validate_output_fields"] = self.validate_output_fields
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FormatRequirements":
        template_rules = None
        if "template_syntax_rules" in data and data["template_syntax_rules"]:
            template_rules = [TemplateSyntaxRule.from_dict(r) for r in data["template_syntax_rules"]]
        return cls(
            expected_type=data.get("expected_type", "json"),
            json_schema=data.get("json_schema"),
            template_syntax_rules=template_rules,
            max_length=data.get("max_length"),
            required_fields=data.get("required_fields"),
            validate_agent_types=data.get("validate_agent_types", False),
            validate_output_fields=data.get("validate_output_fields", False),
        )


@dataclass
class TestCase:
    """
    A single test case for prompt evaluation.

    Defines the input context, expected output patterns,
    and format requirements for testing a prompt.
    """

    id: str
    name: str
    input_context: Dict[str, Any]
    expected_output_patterns: List[OutputPattern]
    format_requirements: FormatRequirements
    description: str = ""
    tags: List[str] = field(default_factory=list)
    priority: int = 0  # Higher priority = run first
    prompt_type: str = "general"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "input_context": self.input_context,
            "expected_output_patterns": [p.to_dict() for p in self.expected_output_patterns],
            "format_requirements": self.format_requirements.to_dict(),
            "tags": self.tags,
            "priority": self.priority,
            "prompt_type": self.prompt_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCase":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            input_context=data.get("input_context", {}),
            expected_output_patterns=[
                OutputPattern.from_dict(p) for p in data.get("expected_output_patterns", [])
            ],
            format_requirements=FormatRequirements.from_dict(data.get("format_requirements", {})),
            tags=data.get("tags", []),
            priority=data.get("priority", 0),
            prompt_type=data.get("prompt_type", "general"),
        )


@dataclass
class Violation:
    """A single validation violation found in the output."""

    rule_name: str
    pattern_matched: str
    message: str
    severity: Literal["error", "warning"] = "error"
    position: Optional[int] = None
    context: Optional[str] = None  # Surrounding text for debugging

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "rule_name": self.rule_name,
            "pattern_matched": self.pattern_matched,
            "message": self.message,
            "severity": self.severity,
        }
        if self.position is not None:
            result["position"] = self.position
        if self.context:
            result["context"] = self.context
        return result


@dataclass
class ValidationResult:
    """Result of format validation."""

    valid: bool
    violations: List[Violation] = field(default_factory=list)
    format_score: float = 1.0  # 0-1, percentage of valid patterns

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "violations": [v.to_dict() for v in self.violations],
            "format_score": self.format_score,
        }


@dataclass
class EvalTestResult:
    """Result of testing a prompt against a single test case."""

    test_case_id: str
    test_case_name: str
    passed: bool
    content_score: float  # 0-1, how well content matches expectations
    format_score: float  # 0-1, how well format matches requirements
    pattern_matches: Dict[str, bool]  # Which patterns matched
    format_violations: List[str]  # What format rules were violated
    raw_output: str  # The actual LLM output
    execution_time_ms: int = 0
    error: Optional[str] = None

    @property
    def overall_score(self) -> float:
        """Combined score (60% content, 40% format)."""
        return (self.content_score * 0.6) + (self.format_score * 0.4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_case_id": self.test_case_id,
            "test_case_name": self.test_case_name,
            "passed": self.passed,
            "content_score": self.content_score,
            "format_score": self.format_score,
            "overall_score": self.overall_score,
            "pattern_matches": self.pattern_matches,
            "format_violations": self.format_violations,
            "raw_output": self.raw_output[:500] + "..." if len(self.raw_output) > 500 else self.raw_output,
            "execution_time_ms": self.execution_time_ms,
            "error": self.error,
        }


@dataclass
class PromptEvalResult:
    """Aggregated result of evaluating a prompt against multiple test cases."""

    passed: bool
    overall_score: float  # 0-1
    content_score: float  # 0-1
    format_score: float  # 0-1
    test_results: List[EvalTestResult]
    tests_passed: int
    tests_failed: int
    total_tests: int
    execution_time_ms: int = 0

    def get_test_passed(self, test_case_id: str) -> bool:
        """Check if a specific test case passed."""
        for result in self.test_results:
            if result.test_case_id == test_case_id:
                return result.passed
        return False

    def get_failed_tests(self) -> List[EvalTestResult]:
        """Get all failed test results."""
        return [r for r in self.test_results if not r.passed]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "overall_score": self.overall_score,
            "content_score": self.content_score,
            "format_score": self.format_score,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "total_tests": self.total_tests,
            "execution_time_ms": self.execution_time_ms,
            "test_results": [r.to_dict() for r in self.test_results],
        }


@dataclass
class OptimizationAttempt:
    """Record of a single optimization attempt."""

    iteration: int
    prompt_version: str
    changes_made: List[str]
    eval_result: PromptEvalResult
    timestamp: datetime = field(default_factory=datetime.utcnow)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "prompt_version": self.prompt_version[:200] + "..." if len(self.prompt_version) > 200 else self.prompt_version,
            "changes_made": self.changes_made,
            "eval_result": self.eval_result.to_dict(),
            "timestamp": self.timestamp.isoformat(),
            "notes": self.notes,
        }


@dataclass
class OptimizationContext:
    """Context for prompt optimization."""

    original_prompt: str
    current_prompt: str
    eval_results: PromptEvalResult
    failed_test_cases: List[TestCase]
    failure_analysis: str
    iteration: int
    previous_attempts: List[OptimizationAttempt]
    constraints: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_prompt": self.original_prompt[:500] + "..." if len(self.original_prompt) > 500 else self.original_prompt,
            "current_prompt": self.current_prompt[:500] + "..." if len(self.current_prompt) > 500 else self.current_prompt,
            "eval_results": self.eval_results.to_dict(),
            "failed_test_cases": [tc.to_dict() for tc in self.failed_test_cases],
            "failure_analysis": self.failure_analysis,
            "iteration": self.iteration,
            "previous_attempts_count": len(self.previous_attempts),
            "constraints": self.constraints,
        }


@dataclass
class OptimizationConfig:
    """Configuration for the optimization loop."""

    max_iterations: int = 5
    pass_threshold: float = 0.9  # 90% of test cases must pass
    format_threshold: float = 0.95  # 95% format compliance
    early_stop_on_perfect: bool = True
    enable_rollback: bool = True
    save_history: bool = True
    eval_model: str = "openai/gpt-4o-mini"
    optimizer_model: str = "openai/gpt-4o"
    eval_temperature: float = 0.3
    optimizer_temperature: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_iterations": self.max_iterations,
            "pass_threshold": self.pass_threshold,
            "format_threshold": self.format_threshold,
            "early_stop_on_perfect": self.early_stop_on_perfect,
            "enable_rollback": self.enable_rollback,
            "save_history": self.save_history,
            "eval_model": self.eval_model,
            "optimizer_model": self.optimizer_model,
            "eval_temperature": self.eval_temperature,
            "optimizer_temperature": self.optimizer_temperature,
        }


@dataclass
class SpecificFix:
    """A specific fix made to the prompt."""

    issue: str
    before_snippet: str
    after_snippet: str
    test_cases_addressed: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue": self.issue,
            "before_snippet": self.before_snippet,
            "after_snippet": self.after_snippet,
            "test_cases_addressed": self.test_cases_addressed,
        }


@dataclass
class PromptImprovement:
    """Result of prompt optimization."""

    improved_prompt: str
    changes_explanation: List[str]
    confidence_score: float  # 0-1, how confident the optimizer is
    specific_fixes: List[SpecificFix]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "improved_prompt": self.improved_prompt[:500] + "..." if len(self.improved_prompt) > 500 else self.improved_prompt,
            "changes_explanation": self.changes_explanation,
            "confidence_score": self.confidence_score,
            "specific_fixes": [f.to_dict() for f in self.specific_fixes],
        }


@dataclass
class OptimizationResult:
    """Result of the full optimization loop."""

    success: bool
    original_prompt: str
    final_prompt: str
    best_prompt: str
    iterations: int
    history: List[OptimizationAttempt]
    final_eval: PromptEvalResult
    original_score: float
    final_score: float
    improvement_summary: str
    execution_time_ms: int = 0
    run_id: Optional[UUID] = field(default_factory=uuid4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "run_id": str(self.run_id) if self.run_id else None,
            "original_prompt": self.original_prompt[:200] + "..." if len(self.original_prompt) > 200 else self.original_prompt,
            "final_prompt": self.final_prompt[:200] + "..." if len(self.final_prompt) > 200 else self.final_prompt,
            "iterations": self.iterations,
            "original_score": self.original_score,
            "final_score": self.final_score,
            "improvement_summary": self.improvement_summary,
            "execution_time_ms": self.execution_time_ms,
            "final_eval": self.final_eval.to_dict(),
            "history": [h.to_dict() for h in self.history],
        }


def get_template_syntax_rules() -> List[TemplateSyntaxRule]:
    """
    Get the standard template syntax rules for task planner outputs.

    These rules enforce correct template syntax like {{step_X.outputs.field}}.
    """
    return [
        TemplateSyntaxRule(
            name="outputs_plural",
            valid_patterns=[
                r"\{\{step_\d+\.outputs\.\w+\}\}",  # {{step_1.outputs.content}}
            ],
            invalid_patterns=[
                r"\{\{step_\d+\.output\}\}",  # {{step_1.output}} - missing 's' and field
                r"\{\{step_\d+\.output\.\w+\}\}",  # {{step_1.output.field}} - missing 's'
                r"\{\{step_\d+\.result\}\}",  # {{step_1.result}} - wrong accessor
                r"\{\{step_\d+\.data\}\}",  # {{step_1.data}} - wrong accessor
            ],
            error_message="Use {{step_X.outputs.field}} syntax, not {{step_X.output}} or {{step_X.result}}",
            severity="error",
        ),
        TemplateSyntaxRule(
            name="field_required",
            valid_patterns=[
                r"\{\{step_\d+\.outputs\.\w+\}\}",
            ],
            invalid_patterns=[
                r"\{\{step_\d+\.outputs\}\}(?!\.\w)",  # {{step_1.outputs}} without field
            ],
            error_message="Must specify field name: {{step_X.outputs.field_name}}",
            severity="error",
        ),
        TemplateSyntaxRule(
            name="valid_step_reference",
            valid_patterns=[
                r"\{\{step_\d+\.outputs\.\w+\}\}",
            ],
            invalid_patterns=[
                r"\{\{step\.outputs\.\w+\}\}",  # Missing step number
                r"\{\{outputs\.\w+\}\}",  # Missing step reference entirely
            ],
            error_message="Step reference must include step number: {{step_X.outputs.field}}",
            severity="error",
        ),
    ]


# Agent-specific output field mappings for validation
AGENT_OUTPUT_FIELDS = {
    "web_research": ["findings", "research_summary", "citations", "sources"],
    "http_fetch": ["content", "status_code", "headers"],
    "summarize": ["summary", "key_points"],
    "compose": ["content", "formatted_content"],
    "analyze": ["analysis", "findings", "insights"],
    "aggregate": ["aggregated", "combined", "merged"],
    "generate_image": ["image_base64", "content_type", "image_url"],
    "file_storage": ["file_id", "cdn_url", "public_url"],
    "pdf_composer": ["pdf_base64", "pdf_url"],
    "notify": ["status", "message_id"],
    "send_email": ["sent", "message_id", "recipients", "tracking_id"],
    "brand_strategist": ["strategy", "recommendations", "analysis"],
    "marketing_strategist": ["strategy", "campaigns", "recommendations"],
    "data_scientist": ["analysis", "insights", "visualizations"],
    "draft": ["content", "draft"],
    "edit": ["content", "edited_content"],
}
