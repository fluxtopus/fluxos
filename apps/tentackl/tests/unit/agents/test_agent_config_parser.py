"""
Unit tests for AgentConfigParser
"""

import pytest
import json
import yaml
import tempfile
from pathlib import Path

from src.config.agent_config_parser import AgentConfigParser
from src.interfaces.configurable_agent import (
    AgentConfig,
    ExecutionStrategy,
    CapabilityConfig,
    StateSchema,
    ResourceConstraints,
    SuccessMetric
)
from src.core.exceptions import ValidationError


@pytest.fixture
def sample_config_dict():
    """Sample configuration dictionary"""
    return {
        "name": "data-processor",
        "type": "processor",
        "version": "1.0.0",
        "description": "Processes and analyzes data",
        "capabilities": [
            {
                "tool": "file_read",
                "config": {
                    "formats": ["csv", "json"],
                    "max_size_mb": 100
                },
                "permissions": {
                    "filesystem": ["read"]
                },
                "sandbox": True
            },
            {
                "tool": "data_transform",
                "config": {
                    "operations": ["filter", "aggregate"],
                    "memory_limit_mb": 512
                }
            }
        ],
        "prompt_template": "Process {data_type} data from {source}. Apply {transformations}.",
        "execution_strategy": "sequential",
        "state_schema": {
            "required": ["data_type", "source"],
            "output": ["processed_data", "statistics"],
            "checkpoint": {
                "enabled": True,
                "interval": 1000
            },
            "validation_rules": {
                "data_type": {
                    "type": "str",
                    "allowed": ["csv", "json", "parquet"]
                }
            }
        },
        "resources": {
            "model": "gpt-4",
            "max_tokens": 2000,
            "timeout": 600,
            "max_retries": 3,
            "memory_mb": 2048,
            "cpu_cores": 2.0
        },
        "success_metrics": [
            {
                "metric": "completion_rate",
                "threshold": 0.95,
                "operator": "gte"
            },
            {
                "metric": "processing_time",
                "threshold": 300,
                "operator": "lte"
            }
        ],
        "metadata": {
            "author": "data-team",
            "tags": ["etl", "analytics"]
        },
        "hooks": {
            "pre_execute": "validate_input",
            "post_execute": "send_notification"
        }
    }


@pytest.fixture
def parser():
    """Create parser instance"""
    return AgentConfigParser()


class TestAgentConfigParser:
    """Test AgentConfigParser functionality"""
    
    async def test_parse_valid_config(self, parser, sample_config_dict):
        """Test parsing valid configuration"""
        config = await parser.parse(sample_config_dict)
        
        assert isinstance(config, AgentConfig)
        assert config.name == "data-processor"
        assert config.type == "processor"
        assert config.version == "1.0.0"
        assert config.description == "Processes and analyzes data"
        
        # Check capabilities
        assert len(config.capabilities) == 2
        assert config.capabilities[0].tool == "file_read"
        assert config.capabilities[0].sandbox is True
        assert config.capabilities[1].tool == "data_transform"
        assert config.capabilities[1].sandbox is False  # Default
        
        # Check execution strategy
        assert config.execution_strategy == ExecutionStrategy.SEQUENTIAL
        
        # Check state schema
        assert "data_type" in config.state_schema.required
        assert "source" in config.state_schema.required
        assert "processed_data" in config.state_schema.output
        assert config.state_schema.checkpoint["enabled"] is True
        
        # Check resources
        assert config.resources.model == "gpt-4"
        assert config.resources.max_tokens == 2000
        assert config.resources.memory_mb == 2048
        
        # Check success metrics
        assert len(config.success_metrics) == 2
        assert config.success_metrics[0].metric == "completion_rate"
        assert config.success_metrics[0].threshold == 0.95
        assert config.success_metrics[0].operator == "gte"
        
        # Check metadata and hooks
        assert config.metadata["author"] == "data-team"
        assert config.hooks["pre_execute"] == "validate_input"
    
    async def test_parse_minimal_config(self, parser):
        """Test parsing minimal valid configuration"""
        minimal_config = {
            "name": "minimal-agent",
            "type": "basic",
            "prompt_template": "Process input: {input}",
            "capabilities": [],
            "state_schema": {
                "required": [],
                "output": []
            },
            "resources": {},
            "success_metrics": []
        }
        
        config = await parser.parse(minimal_config)
        
        assert config.name == "minimal-agent"
        assert config.version == "1.0.0"  # Default
        assert config.description is None
        assert config.execution_strategy == ExecutionStrategy.SEQUENTIAL  # Default
        assert config.resources.model == "gpt-3.5-turbo"  # Default
        assert config.resources.max_tokens == 1000  # Default
        assert config.resources.timeout == 300  # Default
    
    async def test_parse_missing_required_field(self, parser):
        """Test parsing config with missing required field"""
        invalid_config = {
            "type": "processor",
            # Missing "name"
            "prompt_template": "Process data",
            "capabilities": [],
            "state_schema": {"required": [], "output": []},
            "resources": {},
            "success_metrics": []
        }
        
        with pytest.raises(ValidationError) as exc_info:
            await parser.parse(invalid_config)
        
        assert "Missing required field" in str(exc_info.value)
    
    async def test_parse_invalid_execution_strategy(self, parser):
        """Test parsing config with invalid execution strategy"""
        config_dict = {
            "name": "test",
            "type": "test",
            "prompt_template": "Test",
            "execution_strategy": "invalid_strategy",  # Invalid
            "capabilities": [],
            "state_schema": {"required": [], "output": []},
            "resources": {},
            "success_metrics": []
        }
        
        with pytest.raises(ValidationError) as exc_info:
            await parser.parse(config_dict)
        
        assert "Invalid execution strategy" in str(exc_info.value)
    
    async def test_validate_valid_config(self, parser, sample_config_dict):
        """Test validation of valid configuration"""
        config = await parser.parse(sample_config_dict)
        result = await parser.validate(config)
        
        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert len(result["warnings"]) >= 0
        assert len(result["info"]) >= 0
    
    async def test_validate_invalid_config(self, parser):
        """Test validation of invalid configuration"""
        config = AgentConfig(
            name="",  # Invalid - empty
            type="",  # Invalid - empty
            version="invalid-version",  # Invalid format
            capabilities=[],
            prompt_template="",  # Invalid - empty
            execution_strategy=ExecutionStrategy.SEQUENTIAL,
            state_schema=StateSchema(required=[], output=[]),
            resources=ResourceConstraints(
                model="unknown-model",
                max_tokens=-100,  # Invalid - negative
                timeout=0,  # Invalid - zero
            ),
            success_metrics=[
                SuccessMetric(
                    metric="test",
                    threshold=1.0,
                    operator="invalid"  # Invalid operator
                )
            ]
        )
        
        result = await parser.validate(config)
        
        assert result["valid"] is False
        assert "Agent name is required" in result["errors"]
        assert "Agent type is required" in result["errors"]
        assert "Prompt template is required" in result["errors"]
        assert "Max tokens must be positive" in result["errors"]
        assert "Timeout must be positive" in result["errors"]
        assert "Invalid operator" in str(result["errors"])
    
    async def test_validate_warnings(self, parser):
        """Test validation warnings"""
        config = AgentConfig(
            name="test-agent-123!",  # Contains special char
            type="test",
            version="1.0",  # Not full semver
            capabilities=[],  # No capabilities
            prompt_template="Test",
            execution_strategy=ExecutionStrategy.SEQUENTIAL,
            state_schema=StateSchema(
                required=["field1"],
                output=["field1"]  # Duplicate field
            ),
            resources=ResourceConstraints(
                model="custom-model",  # Unknown model
                max_tokens=50000,  # Very high
                timeout=10,  # Very low
            ),
            success_metrics=[]  # No metrics
        )
        
        result = await parser.validate(config)
        
        assert result["valid"] is True  # Warnings don't fail validation
        assert len(result["warnings"]) > 0
        assert any("alphanumeric" in w for w in result["warnings"])
        assert any("semantic versioning" in w for w in result["warnings"])
        assert any("No capabilities" in w for w in result["warnings"])
        assert any("both required and output" in w for w in result["warnings"])
        assert any("very high" in w for w in result["warnings"])
        assert any("very low" in w for w in result["warnings"])
        assert any("No success metrics" in w for w in result["warnings"])
    
    async def test_merge_configs(self, parser, sample_config_dict):
        """Test merging configurations"""
        base_config = await parser.parse(sample_config_dict)
        
        override = {
            "name": "data-processor-v2",
            "version": "2.0.0",
            "resources": {
                "model": "gpt-4-turbo",
                "max_tokens": 4000
            },
            "capabilities": [
                {
                    "tool": "api_call",
                    "config": {"timeout": 30}
                }
            ]
        }
        
        merged = await parser.merge_configs(base_config, override)
        
        assert merged.name == "data-processor-v2"
        assert merged.version == "2.0.0"
        assert merged.type == "processor"  # From base
        assert merged.resources.model == "gpt-4-turbo"
        assert merged.resources.max_tokens == 4000
        assert merged.resources.timeout == 600  # From base
        assert len(merged.capabilities) == 1  # Override replaces
        assert merged.capabilities[0].tool == "api_call"
    
    async def test_deep_merge(self, parser, sample_config_dict):
        """Test deep merging of nested configurations"""
        base_config = await parser.parse(sample_config_dict)
        
        override = {
            "state_schema": {
                "required": ["data_type", "source", "format"],  # Add format
                "checkpoint": {
                    "interval": 500  # Change interval only
                }
            }
        }
        
        merged = await parser.merge_configs(base_config, override)
        
        assert "format" in merged.state_schema.required
        assert merged.state_schema.checkpoint["interval"] == 500
        assert merged.state_schema.checkpoint["enabled"] is True  # Preserved
    
    async def test_semver_validation(self, parser):
        """Test semantic versioning validation"""
        # Valid versions
        valid_versions = [
            "1.0.0",
            "0.1.0",
            "2.3.4",
            "1.0.0-alpha",
            "1.0.0-beta.1",
            "1.0.0+build.123"
        ]
        
        for version in valid_versions:
            assert parser._is_valid_semver(version) is True
        
        # Invalid versions
        invalid_versions = [
            "1.0",
            "1",
            "v1.0.0",
            "1.0.0.0",
            "1.a.0",
            "invalid"
        ]
        
        for version in invalid_versions:
            assert parser._is_valid_semver(version) is False
    
    def test_load_from_yaml_file(self, sample_config_dict):
        """Test loading configuration from YAML file"""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.yaml',
            delete=False
        ) as f:
            yaml.dump(sample_config_dict, f)
            yaml_path = f.name
        
        try:
            loaded = AgentConfigParser.load_from_file(yaml_path)
            assert loaded == sample_config_dict
        finally:
            Path(yaml_path).unlink()
    
    def test_load_from_json_file(self, sample_config_dict):
        """Test loading configuration from JSON file"""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.json',
            delete=False
        ) as f:
            json.dump(sample_config_dict, f)
            json_path = f.name
        
        try:
            loaded = AgentConfigParser.load_from_file(json_path)
            assert loaded == sample_config_dict
        finally:
            Path(json_path).unlink()
    
    def test_load_from_nonexistent_file(self):
        """Test loading from non-existent file"""
        with pytest.raises(FileNotFoundError):
            AgentConfigParser.load_from_file("/tmp/nonexistent.yaml")
    
    def test_load_from_unsupported_format(self):
        """Test loading from unsupported file format"""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.txt',
            delete=False
        ) as f:
            f.write("test")
            txt_path = f.name
        
        try:
            with pytest.raises(ValueError) as exc_info:
                AgentConfigParser.load_from_file(txt_path)
            assert "Unsupported file format" in str(exc_info.value)
        finally:
            Path(txt_path).unlink()
    
    async def test_template_variables_extraction(self, parser):
        """Test extraction of template variables"""
        config_dict = {
            "name": "test",
            "type": "test",
            "prompt_template": "Process {input_data} using {method} for {user.name}",
            "capabilities": [],
            "state_schema": {"required": [], "output": []},
            "resources": {},
            "success_metrics": []
        }
        
        config = await parser.parse(config_dict)
        result = await parser.validate(config)
        
        # Check that info contains template variables
        assert len(result["info"]) > 0
        variables_info = next(
            (info for info in result["info"] if "variables" in info),
            None
        )
        assert variables_info is not None
        assert "input_data" in variables_info
        assert "method" in variables_info
        assert "user" in variables_info
    
    async def test_capability_permissions_validation(self, parser):
        """Test validation of capability permissions"""
        config_dict = {
            "name": "test",
            "type": "test",
            "prompt_template": "Test",
            "capabilities": [
                {
                    "tool": "file_write",
                    "config": {},
                    "sandbox": True
                    # No permissions defined but sandboxed
                }
            ],
            "state_schema": {"required": [], "output": []},
            "resources": {},
            "success_metrics": []
        }
        
        config = await parser.parse(config_dict)
        result = await parser.validate(config)
        
        # Should have warning about sandboxed capability without permissions
        assert any(
            "sandboxed but has no permissions" in w
            for w in result["warnings"]
        )
    
    async def test_config_inheritance(self, parser, sample_config_dict):
        """Test configuration inheritance via parent_config"""
        # Add parent reference
        sample_config_dict["parent_config"] = "base-processor-v1"
        
        config = await parser.parse(sample_config_dict)
        assert config.parent_config == "base-processor-v1"
        
        # Test that parent config is preserved during merge
        override = {"name": "child-processor"}
        merged = await parser.merge_configs(config, override)
        assert merged.parent_config == "base-processor-v1"
