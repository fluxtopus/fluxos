"""
Agent Configuration Parser

This module implements parsing and validation of agent configurations
from YAML/JSON into structured AgentConfig objects.
"""

import yaml
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

from ..interfaces.configurable_agent import (
    ConfigParserInterface,
    AgentConfig,
    ExecutionStrategy,
    CapabilityConfig,
    StateSchema,
    ResourceConstraints,
    SuccessMetric
)
from ..core.exceptions import ValidationError
import structlog

logger = structlog.get_logger(__name__)


class AgentConfigParser(ConfigParserInterface):
    """Parser for agent configurations"""
    
    def __init__(self, schema_path: Optional[str] = None):
        self.schema_path = schema_path
        self._schema = None
        if schema_path:
            self._load_schema()
    
    def _load_schema(self) -> None:
        """Load JSON schema for validation"""
        try:
            with open(self.schema_path, 'r') as f:
                self._schema = json.load(f)
        except Exception as e:
            logger.warning(
                "Failed to load schema, validation will be limited",
                error=str(e)
            )
    
    async def parse(self, config_data: Dict[str, Any]) -> AgentConfig:
        """Parse raw configuration data into AgentConfig"""
        try:
            # Validate against schema if available
            if self._schema and HAS_JSONSCHEMA:
                try:
                    jsonschema.validate(config_data, self._schema)
                except jsonschema.ValidationError as e:
                    raise ValidationError(f"Schema validation failed: {e.message}")
            
            # Parse capabilities
            capabilities = []
            for cap_data in config_data.get("capabilities", []):
                capabilities.append(CapabilityConfig(
                    tool=cap_data["tool"],
                    config=cap_data.get("config", {}),
                    permissions=cap_data.get("permissions"),
                    sandbox=cap_data.get("sandbox", False)
                ))
            
            # Parse state schema
            state_data = config_data.get("state_schema", {})
            state_schema = StateSchema(
                required=state_data.get("required", []),
                output=state_data.get("output", []),
                checkpoint=state_data.get("checkpoint"),
                validation_rules=state_data.get("validation_rules")
            )
            
            # Parse resources
            resources_data = config_data.get("resources", {})
            resources = ResourceConstraints(
                model=resources_data.get("model", "gpt-3.5-turbo"),
                max_tokens=resources_data.get("max_tokens", 1000),
                timeout=resources_data.get("timeout", 300),
                max_retries=resources_data.get("max_retries", 3),
                memory_mb=resources_data.get("memory_mb"),
                cpu_cores=resources_data.get("cpu_cores"),
                temperature=resources_data.get("temperature", 0.7),
                response_format=resources_data.get("response_format")
            )
            
            # Parse success metrics
            metrics = []
            for metric_data in config_data.get("success_metrics", []):
                metrics.append(SuccessMetric(
                    metric=metric_data["metric"],
                    threshold=metric_data["threshold"],
                    operator=metric_data.get("operator", "gte")
                ))
            
            # Parse execution strategy
            strategy_str = config_data.get("execution_strategy", "sequential")
            try:
                strategy = ExecutionStrategy(strategy_str)
            except ValueError:
                raise ValidationError(f"Invalid execution strategy: {strategy_str}")
            
            # Create AgentConfig
            config = AgentConfig(
                name=config_data["name"],
                type=config_data["type"],
                version=config_data.get("version", "1.0.0"),
                description=config_data.get("description"),
                capabilities=capabilities,
                prompt_template=config_data["prompt_template"],
                execution_strategy=strategy,
                state_schema=state_schema,
                resources=resources,
                success_metrics=metrics,
                metadata=config_data.get("metadata"),
                parent_config=config_data.get("parent_config"),
                hooks=config_data.get("hooks")
            )
            
            logger.info(
                "Configuration parsed successfully",
                name=config.name,
                type=config.type,
                version=config.version
            )
            
            return config
            
        except KeyError as e:
            raise ValidationError(f"Missing required field: {e}")
        except Exception as e:
            logger.error("Failed to parse configuration", error=str(e))
            raise
    
    async def validate(self, config: AgentConfig) -> Dict[str, Any]:
        """Validate an agent configuration"""
        errors = []
        warnings = []
        info = []
        
        # Name validation
        if not config.name:
            errors.append("Agent name is required")
        elif not config.name.replace("-", "").replace("_", "").isalnum():
            warnings.append("Agent name should contain only alphanumeric characters, hyphens, and underscores")
        
        # Type validation
        if not config.type:
            errors.append("Agent type is required")
        
        # Version validation
        if not self._is_valid_semver(config.version):
            warnings.append(f"Version '{config.version}' is not valid semantic versioning")
        
        # Capability validation
        if not config.capabilities:
            warnings.append("No capabilities defined - agent will have limited functionality")
        else:
            for i, cap in enumerate(config.capabilities):
                if not cap.tool:
                    errors.append(f"Capability {i} missing tool name")
                if cap.sandbox and not cap.permissions:
                    warnings.append(f"Capability '{cap.tool}' is sandboxed but has no permissions defined")
        
        # Prompt template validation
        if not config.prompt_template:
            errors.append("Prompt template is required")
        else:
            # Check for template variables, including dotted paths (e.g., {user.name})
            import re
            raw_vars = re.findall(r'\{([^}]+)\}', config.prompt_template)
            vars_normalized: List[str] = []
            for v in raw_vars:
                v = v.strip()
                if not v:
                    continue
                # Take the root identifier before any dot path
                root = v.split('.', 1)[0]
                if root:
                    vars_normalized.append(root)
            if vars_normalized:
                # Deduplicate while preserving insertion order
                seen = []
                for name in vars_normalized:
                    if name not in seen:
                        seen.append(name)
                info.append(f"Prompt template uses variables: {', '.join(seen)}")
        
        # State schema validation
        if not config.state_schema.required and not config.state_schema.output:
            warnings.append("State schema has no required or output fields defined")
        
        # Duplicate field check
        duplicates = set(config.state_schema.required) & set(config.state_schema.output)
        if duplicates:
            warnings.append(f"Fields appear in both required and output: {', '.join(duplicates)}")
        
        # Resource validation
        if config.resources.max_tokens <= 0:
            errors.append("Max tokens must be positive")
        elif config.resources.max_tokens > 32000:
            warnings.append("Max tokens is very high - this may be expensive")
        
        if config.resources.timeout <= 0:
            errors.append("Timeout must be positive")
        elif config.resources.timeout < 30:
            warnings.append("Timeout is very low - complex tasks may fail")
        
        # Success metrics validation
        if not config.success_metrics:
            warnings.append("No success metrics defined - all executions will be considered successful")
        else:
            for metric in config.success_metrics:
                if metric.operator not in ["gte", "lte", "eq", "neq"]:
                    errors.append(f"Invalid operator '{metric.operator}' for metric '{metric.metric}'")
        
        # Model validation
        known_models = [
            "gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o",
            "claude-2", "claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
            "gemini-pro", "gemini-ultra", "llama-2-70b", "mixtral-8x7b"
        ]
        if config.resources.model not in known_models:
            warnings.append(f"Unknown model '{config.resources.model}' - ensure it's available")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "info": info
        }
    
    async def merge_configs(
        self,
        base: AgentConfig,
        override: Dict[str, Any]
    ) -> AgentConfig:
        """Merge configurations with inheritance"""
        try:
            # Convert base config to dict
            base_dict = self._config_to_dict(base)
            
            # Deep merge with override
            merged_dict = self._deep_merge(base_dict, override)
            
            # Parse merged config
            merged_config = await self.parse(merged_dict)
            
            # Preserve parent reference
            if base.parent_config and "parent_config" not in override:
                merged_config.parent_config = base.parent_config
            
            logger.info(
                "Configurations merged",
                base_name=base.name,
                override_fields=list(override.keys())
            )
            
            return merged_config
            
        except Exception as e:
            logger.error("Failed to merge configurations", error=str(e))
            raise
    
    def _config_to_dict(self, config: AgentConfig) -> Dict[str, Any]:
        """Convert AgentConfig to dictionary"""
        return {
            "name": config.name,
            "type": config.type,
            "version": config.version,
            "description": config.description,
            "capabilities": [
                {
                    "tool": cap.tool,
                    "config": cap.config,
                    "permissions": cap.permissions,
                    "sandbox": cap.sandbox
                }
                for cap in config.capabilities
            ],
            "prompt_template": config.prompt_template,
            "execution_strategy": config.execution_strategy.value,
            "state_schema": {
                "required": config.state_schema.required,
                "output": config.state_schema.output,
                "checkpoint": config.state_schema.checkpoint,
                "validation_rules": config.state_schema.validation_rules
            },
            "resources": {
                "model": config.resources.model,
                "max_tokens": config.resources.max_tokens,
                "timeout": config.resources.timeout,
                "max_retries": config.resources.max_retries,
                "memory_mb": config.resources.memory_mb,
                "cpu_cores": config.resources.cpu_cores
            },
            "success_metrics": [
                {
                    "metric": metric.metric,
                    "threshold": metric.threshold,
                    "operator": metric.operator
                }
                for metric in config.success_metrics
            ],
            "metadata": config.metadata,
            "parent_config": config.parent_config,
            "hooks": config.hooks
        }
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _is_valid_semver(self, version: str) -> bool:
        """Check if version string is valid semantic versioning"""
        import re
        pattern = r'^(\d+)\.(\d+)\.(\d+)(?:-(\w+(?:\.\w+)*))?(?:\+(\w+(?:\.\w+)*))?$'
        return bool(re.match(pattern, version))
    
    async def parse_from_yaml(self, yaml_text: str) -> AgentConfig:
        """
        Parse agent configuration directly from YAML text.

        Args:
            yaml_text: YAML string containing agent configuration

        Returns:
            Parsed AgentConfig

        Raises:
            ValidationError: If YAML is invalid or parsing fails
        """
        try:
            config_data = yaml.safe_load(yaml_text)
            if not isinstance(config_data, dict):
                raise ValidationError("YAML must contain a dictionary at the top level")

            return await self.parse(config_data)
        except yaml.YAMLError as e:
            raise ValidationError(f"Invalid YAML syntax: {e}")
        except Exception as e:
            raise ValidationError(f"Failed to parse YAML: {e}")

    @staticmethod
    def load_from_file(file_path: str) -> Dict[str, Any]:
        """Load configuration from file"""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        with open(path, 'r') as f:
            if path.suffix in ['.yaml', '.yml']:
                return yaml.safe_load(f)
            elif path.suffix == '.json':
                return json.load(f)
            else:
                raise ValueError(f"Unsupported file format: {path.suffix}")
