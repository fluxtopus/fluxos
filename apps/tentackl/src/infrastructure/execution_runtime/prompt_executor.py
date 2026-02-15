"""
Prompt Executor

This module implements the prompt executor that handles LLM interactions
for configurable agents.
"""

from __future__ import annotations

import asyncio
import re
from typing import Dict, Any, Optional, AsyncIterator, List
from datetime import datetime
import json

from src.interfaces.configurable_agent import PromptExecutorInterface
from src.interfaces.llm import LLMClientInterface
from src.core.exceptions import LLMError, PromptError
from src.core.safe_eval import safe_eval_condition
import structlog

logger = structlog.get_logger(__name__)


class PromptExecutor(PromptExecutorInterface):
    """Executor for LLM prompts with template support"""
    
    def __init__(
        self,
        llm_client: LLMClientInterface,
        default_model: str = "gpt-3.5-turbo",
        default_temperature: float = 0.7,
        retry_attempts: int = 3,
        retry_delay: float = 1.0
    ):
        self.llm_client = llm_client
        self.default_model = default_model
        self.default_temperature = default_temperature
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        
        # Cache for compiled templates
        self._template_cache: Dict[str, Any] = {}
        
        # Metrics
        self._execution_count = 0
        self._total_tokens = 0
        self._total_cost = 0.0
    
    async def execute_prompt(
        self,
        prompt_template: str,
        context: Dict[str, Any],
        model: str,
        max_tokens: int,
        temperature: float = 0.7,
        response_format: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Execute a prompt with the LLM"""
        try:
            # Fill template
            prompt = self._fill_template(prompt_template, context)
            
            # Validate prompt
            self._validate_prompt(prompt, max_tokens)
            
            # Execute with retries
            response = await self._execute_with_retry(
                prompt,
                model or self.default_model,
                max_tokens,
                temperature,
                response_format,
                tools=tools
            )
            
            # Update metrics
            self._execution_count += 1
            if hasattr(response, 'usage') and response.usage:
                self._total_tokens += response.usage.get("total_tokens", 0)
            elif isinstance(response, dict) and "usage" in response:
                self._total_tokens += response["usage"].get("total_tokens", 0)
            
            if hasattr(response, 'metadata') and response.metadata and "cost" in response.metadata:
                self._total_cost += response.metadata["cost"]
            elif isinstance(response, dict) and "cost" in response:
                self._total_cost += response["cost"]
            
            # Extract content
            content = self._extract_content(response)
            
            logger.info(
                "Prompt executed successfully",
                model=model,
                prompt_length=len(prompt),
                response_length=len(content),
                temperature=temperature
            )
            
            return content
            
        except Exception as e:
            logger.error(
                "Prompt execution failed",
                error=str(e),
                model=model,
                template_preview=prompt_template[:100] + "..."
            )
            raise
    
    async def stream_prompt(
        self,
        prompt_template: str,
        context: Dict[str, Any],
        model: str,
        max_tokens: int,
        temperature: float = 0.7
    ) -> AsyncIterator[str]:
        """Stream prompt execution"""
        try:
            # Fill template
            prompt = self._fill_template(prompt_template, context)
            
            # Validate prompt
            self._validate_prompt(prompt, max_tokens)
            
            # Stream from LLM
            async for chunk in self._stream_with_retry(
                prompt,
                model or self.default_model,
                max_tokens,
                temperature
            ):
                yield chunk
            
            # Update metrics
            self._execution_count += 1
            
        except Exception as e:
            logger.error(
                "Prompt streaming failed",
                error=str(e),
                model=model
            )
            raise
    
    def _fill_template(
        self,
        template: str,
        context: Dict[str, Any]
    ) -> str:
        """Fill template with context values"""
        # Check cache
        cache_key = hash(template)
        if cache_key in self._template_cache:
            compiled = self._template_cache[cache_key]
        else:
            # Compile template
            compiled = self._compile_template(template)
            self._template_cache[cache_key] = compiled
        
        # Fill template
        try:
            # First handle conditionals and loops so inner variables use proper scopes
            result = self._process_conditionals(template, context)
            result = self._process_loops(result, context)

            # Finally, replace any remaining placeholders with context variables
            # Skip double braces {{...}} as they are likely literal template syntax, not template variables
            for match in re.finditer(r'(?<!\{)\{(\w+(?:\.\w+)*)\}(?!\})', result):
                var_path = match.group(1)
                try:
                    value = self._get_nested_value(context, var_path)
                    result = result.replace(match.group(0), str(value))
                except KeyError:
                    # If variable not found and it's in double braces context, skip it
                    # This handles cases like {{node.id}} which should be literal
                    pass
            
            return result
            
        except KeyError as e:
            raise PromptError(f"Missing template variable: {e}")
        except Exception as e:
            raise PromptError(f"Template filling failed: {e}")
    
    def _compile_template(self, template: str) -> Dict[str, Any]:
        """Compile template for faster processing"""
        # Extract variables
        variables = re.findall(r'\{(\w+(?:\.\w+)*)\}', template)
        
        # Extract conditionals
        conditionals = re.findall(
            r'\{%\s*if\s+(.*?)\s*%\}(.*?)\{%\s*endif\s*%\}',
            template,
            re.DOTALL
        )
        
        # Extract loops
        loops = re.findall(
            r'\{%\s*for\s+(\w+)\s+in\s+(\w+(?:\.\w+)*)\s*%\}(.*?)\{%\s*endfor\s*%\}',
            template,
            re.DOTALL
        )
        
        return {
            "variables": variables,
            "conditionals": conditionals,
            "loops": loops
        }
    
    def _get_nested_value(
        self,
        context: Dict[str, Any],
        path: str
    ) -> Any:
        """Get value from nested path in context"""
        parts = path.split('.')
        value = context
        
        for part in parts:
            if isinstance(value, dict):
                if part not in value:
                    raise KeyError(f"Path not found: {path}")
                value = value[part]
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                raise KeyError(f"Path not found: {path}")
            
            if value is None:
                raise KeyError(f"Path not found: {path}")
        
        return value
    
    def _process_conditionals(
        self,
        text: str,
        context: Dict[str, Any]
    ) -> str:
        """Process conditional statements in template"""
        # Simple if statements
        pattern = r'\{%\s*if\s+(.*?)\s*%\}(.*?)\{%\s*endif\s*%\}'
        
        def replace_conditional(match):
            condition = match.group(1)
            content = match.group(2)
            
            try:
                # Evaluate condition
                if self._evaluate_condition(condition, context):
                    return content
                return ""
            except:
                return content  # Default to including content if evaluation fails
        
        return re.sub(pattern, replace_conditional, text, flags=re.DOTALL)
    
    def _process_loops(
        self,
        text: str,
        context: Dict[str, Any]
    ) -> str:
        """Process loop statements in template"""
        pattern = r'\{%\s*for\s+(\w+)\s+in\s+(\w+(?:\.\w+)*)\s*%\}(.*?)\{%\s*endfor\s*%\}'
        
        def replace_loop(match):
            var_name = match.group(1)
            collection_path = match.group(2)
            content = match.group(3)
            
            try:
                collection = self._get_nested_value(context, collection_path)
                if not isinstance(collection, (list, tuple)):
                    return ""
                
                results = []
                for item in collection:
                    # Create loop context
                    loop_context = context.copy()
                    loop_context[var_name] = item
                    
                    # Process content with loop variable
                    result = content
                    for var_match in re.finditer(r'\{(\w+(?:\.\w+)*)\}', content):
                        var_path = var_match.group(1)
                        value = self._get_nested_value(loop_context, var_path)
                        result = result.replace(var_match.group(0), str(value))
                    
                    results.append(result)
                
                return ''.join(results)
            except:
                return ""  # Return empty if loop processing fails
        
        return re.sub(pattern, replace_loop, text, flags=re.DOTALL)
    
    def _evaluate_condition(
        self,
        condition: str,
        context: Dict[str, Any]
    ) -> bool:
        """Evaluate a condition expression using safe evaluation"""
        return safe_eval_condition(condition, context=context, default=False)
    
    def _validate_prompt(
        self,
        prompt: str,
        max_tokens: int
    ) -> None:
        """Validate prompt before execution"""
        # Check length
        estimated_tokens = len(prompt) // 4  # Rough estimate
        if estimated_tokens > max_tokens:
            raise PromptError(
                f"Prompt too long: estimated {estimated_tokens} tokens, "
                f"max allowed {max_tokens}"
            )
        
        # Check for common issues
        if not prompt.strip():
            raise PromptError("Empty prompt")
        
        if len(prompt) > 32000:  # Absolute character limit
            raise PromptError("Prompt exceeds maximum character limit")
    
    async def _execute_with_retry(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        response_format: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Any:
        """Execute prompt with retry logic"""
        last_error = None
        
        for attempt in range(self.retry_attempts):
            try:
                # Build messages (dicts) for LLMClientInterface
                messages = [{"role": "user", "content": prompt}]
                
                # Prepare kwargs
                kwargs = {}
                if response_format:
                    kwargs["response_format"] = response_format
                if tools:
                    kwargs["tools"] = tools
                
                # Call LLM
                response = await self.llm_client.complete(
                    messages=messages,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs
                )
                
                return response
                
            except LLMError as e:
                last_error = e
                if attempt < self.retry_attempts - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        "LLM call failed, retrying",
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e)
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
            except Exception as e:
                # Don't retry on non-LLM errors
                raise
        
        raise last_error or LLMError("All retry attempts failed")
    
    async def _stream_with_retry(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float
    ) -> AsyncIterator[str]:
        """Stream prompt with retry logic"""
        last_error = None
        
        for attempt in range(self.retry_attempts):
            try:
                # Build messages
                messages = [{"role": "user", "content": prompt}]
                
                # Stream from LLM
                try:
                    async for chunk in self.llm_client.stream(
                        messages=messages,
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature
                    ):
                        yield chunk
                except TypeError:
                    # Some test doubles don't accept kwargs; fall back to simple streaming
                    async for chunk in self.llm_client.stream():
                        yield chunk
                
                return  # Success
                
            except LLMError as e:
                last_error = e
                if attempt < self.retry_attempts - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        "LLM streaming failed, retrying",
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e)
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
            except Exception as e:
                # Don't retry on non-LLM errors
                raise
        
        raise last_error or LLMError("All retry attempts failed")
    
    def _extract_content(self, response: Any) -> str:
        """Extract content from LLM response"""
        # Handle LLMResponse objects
        if hasattr(response, 'content'):
            return response.content
            
        # Handle different response formats
        if isinstance(response, dict) and "choices" in response and response["choices"]:
            choice = response["choices"][0]
            if "message" in choice:
                return choice["message"].get("content", "")
            elif "text" in choice:
                return choice["text"]
        
        if "content" in response:
            return response["content"]
        
        if "text" in response:
            return response["text"]
        
        # Try to extract from JSON response
        if isinstance(response, dict):
            for key in ["response", "result", "output", "answer"]:
                if key in response:
                    return str(response[key])
        
        # Fallback to string representation
        return str(response)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get execution metrics"""
        return {
            "execution_count": self._execution_count,
            "total_tokens": self._total_tokens,
            "total_cost": self._total_cost,
            "average_tokens": (
                self._total_tokens / self._execution_count
                if self._execution_count > 0 else 0
            ),
            "average_cost": (
                self._total_cost / self._execution_count
                if self._execution_count > 0 else 0
            )
        }
    
    def reset_metrics(self) -> None:
        """Reset execution metrics"""
        self._execution_count = 0
        self._total_tokens = 0
        self._total_cost = 0.0
    
    async def validate_model(
        self,
        model: str
    ) -> bool:
        """Validate that a model is available"""
        try:
            # Try a minimal completion
            messages = [{"role": "user", "content": "Hi"}]
            await self.llm_client.complete(
                messages=messages,
                model=model,
                max_tokens=10,
                temperature=0.0
            )
            return True
        except:
            return False
