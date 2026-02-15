"""
Tests for AgentTemplate and related classes.
"""

import pytest
from datetime import datetime

from src.agents.templates.agent_template import (
    AgentTemplate,
    TemplateParameter,
    TemplatePrompt,
    OutputTransform,
    ParameterType,
    TemplateValidationError,
)


class TestTemplateParameter:
    """Tests for TemplateParameter class."""

    def test_string_parameter_validation(self):
        """Test string parameter validation."""
        param = TemplateParameter(
            name="brand_name",
            type=ParameterType.STRING,
            required=True,
        )

        # Valid string
        assert param.validate("My Brand") == []

        # Missing required
        assert len(param.validate(None)) == 1

        # Wrong type
        errors = param.validate(123)
        assert len(errors) == 1
        assert "must be string" in errors[0]

    def test_enum_parameter_validation(self):
        """Test enum parameter validation."""
        param = TemplateParameter(
            name="style",
            type=ParameterType.ENUM,
            allowed=["casual", "professional", "fun"],
            default="professional",
        )

        # Valid value
        assert param.validate("casual") == []

        # Invalid value
        errors = param.validate("formal")
        assert len(errors) == 1
        assert "must be one of" in errors[0]

    def test_integer_parameter_with_range(self):
        """Test integer parameter with min/max validation."""
        param = TemplateParameter(
            name="word_count",
            type=ParameterType.INTEGER,
            min_value=100,
            max_value=5000,
        )

        # Valid value
        assert param.validate(1000) == []

        # Too low
        errors = param.validate(50)
        assert len(errors) == 1
        assert ">= 100" in errors[0]

        # Too high
        errors = param.validate(10000)
        assert len(errors) == 1
        assert "<= 5000" in errors[0]

    def test_string_parameter_with_pattern(self):
        """Test string parameter with regex pattern."""
        param = TemplateParameter(
            name="hashtag",
            type=ParameterType.STRING,
            pattern=r"^#[a-zA-Z0-9]+$",
        )

        # Valid hashtag
        assert param.validate("#BrandName") == []

        # Invalid format
        errors = param.validate("no-hashtag")
        assert len(errors) == 1
        assert "must match pattern" in errors[0]

    def test_get_value_with_default(self):
        """Test getting effective value with defaults."""
        param = TemplateParameter(
            name="tone",
            type=ParameterType.STRING,
            default="professional",
        )

        assert param.get_value() == "professional"
        assert param.get_value("casual") == "casual"
        assert param.get_value(None) == "professional"

    def test_serialization(self):
        """Test parameter serialization/deserialization."""
        param = TemplateParameter(
            name="count",
            type=ParameterType.INTEGER,
            description="Word count",
            default=1000,
            min_value=100,
            max_value=5000,
        )

        data = param.to_dict()
        restored = TemplateParameter.from_dict(data)

        assert restored.name == param.name
        assert restored.type == param.type
        assert restored.default == param.default
        assert restored.min_value == param.min_value
        assert restored.max_value == param.max_value


class TestTemplatePrompt:
    """Tests for TemplatePrompt class."""

    def test_simple_render(self):
        """Test simple variable substitution."""
        prompt = TemplatePrompt(
            name="system",
            template="Brand: {{ brand_name }}\nVoice: {{ voice }}",
        )

        result = prompt.render({
            "brand_name": "Acme Corp",
            "voice": "professional",
        })

        assert "Brand: Acme Corp" in result
        assert "Voice: professional" in result

    def test_render_with_missing_vars(self):
        """Test rendering with missing variables leaves placeholders intact."""
        prompt = TemplatePrompt(
            name="intro",
            template="Hello {{ name }}, welcome to {{ company }}!",
        )

        result = prompt.render({"name": "Alice"})

        assert "Hello Alice" in result
        # Missing variables are left as unreplaced placeholders
        assert "{{ company }}" in result

    def test_condition_evaluation(self):
        """Test conditional prompt application."""
        prompt = TemplatePrompt(
            name="shorts_intro",
            template="Keep it short!",
            condition="format == 'shorts'",
        )

        # Condition met
        assert prompt.should_apply({"format": "shorts"})

        # Condition not met
        assert not prompt.should_apply({"format": "long_form"})

    def test_condition_with_invalid_expression(self):
        """Test that invalid conditions default to False."""
        prompt = TemplatePrompt(
            name="test",
            template="Test",
            condition="undefined_var > 10",  # Will fail
        )

        # Should return False on error, not raise
        assert not prompt.should_apply({})


class TestOutputTransform:
    """Tests for OutputTransform class."""

    def test_add_transform(self):
        """Test adding a new field."""
        transform = OutputTransform(
            name="add_source",
            transform_type="add",
            target_field="source",
            value="AI Generated",
        )

        output = {"title": "Test"}
        result = transform.apply(output, {})

        assert result["source"] == "AI Generated"
        assert result["title"] == "Test"

    def test_add_with_template_value(self):
        """Test adding with templated value."""
        transform = OutputTransform(
            name="add_url",
            transform_type="add",
            target_field="url",
            value="https://example.com/{{ slug }}",
        )

        output = {"title": "Test", "slug": "test-post"}
        result = transform.apply(output, {})

        assert result["url"] == "https://example.com/test-post"

    def test_conditional_transform(self):
        """Test transform with condition."""
        transform = OutputTransform(
            name="add_hashtags",
            condition="format == 'shorts'",
            transform_type="add",
            target_field="hashtags",
            value=["#shorts", "#video"],
        )

        output = {"title": "Test"}

        # With matching condition
        result = transform.apply(output, {"format": "shorts"})
        assert "hashtags" in result

        # Without matching condition
        result = transform.apply(output, {"format": "long_form"})
        assert "hashtags" not in result

    def test_remove_transform(self):
        """Test removing a field."""
        transform = OutputTransform(
            name="remove_internal",
            transform_type="remove",
            target_field="internal_id",
        )

        output = {"title": "Test", "internal_id": "abc123"}
        result = transform.apply(output, {})

        assert "internal_id" not in result
        assert "title" in result


class TestAgentTemplate:
    """Tests for AgentTemplate class."""

    def test_basic_creation(self):
        """Test creating a basic template."""
        template = AgentTemplate(
            name="brand-youtube",
            version="1.0.0",
            domain="content",
            agent_type="youtube_script",
            description="Brand-specific YouTube template",
        )

        assert template.name == "brand-youtube"
        assert template.template_id == "content:youtube_script:brand-youtube"
        assert template.created_at is not None

    def test_validation_success(self):
        """Test successful template validation."""
        template = AgentTemplate(
            name="valid-template",
            version="1.0.0",
            domain="content",
            agent_type="draft",
            parameters=[
                TemplateParameter(
                    name="tone",
                    type=ParameterType.STRING,
                    default="professional",
                ),
            ],
        )

        errors = template.validate()
        assert errors == []

    def test_validation_missing_fields(self):
        """Test validation catches missing required fields."""
        template = AgentTemplate(
            name="",
            version="",
            domain="",
            agent_type="",
        )

        errors = template.validate()
        assert len(errors) >= 4  # name, version, domain, agent_type

    def test_validation_invalid_version(self):
        """Test validation catches invalid version format."""
        template = AgentTemplate(
            name="test",
            version="v1",  # Invalid semver
            domain="content",
            agent_type="draft",
        )

        errors = template.validate()
        assert any("version format" in e for e in errors)

    def test_validation_duplicate_parameters(self):
        """Test validation catches duplicate parameter names."""
        template = AgentTemplate(
            name="test",
            version="1.0.0",
            domain="content",
            agent_type="draft",
            parameters=[
                TemplateParameter(name="tone", type=ParameterType.STRING),
                TemplateParameter(name="tone", type=ParameterType.STRING),
            ],
        )

        errors = template.validate()
        assert any("Duplicate parameter" in e for e in errors)

    def test_validate_parameters(self):
        """Test validating provided parameter values."""
        template = AgentTemplate(
            name="test",
            version="1.0.0",
            domain="content",
            agent_type="draft",
            parameters=[
                TemplateParameter(
                    name="word_count",
                    type=ParameterType.INTEGER,
                    required=True,
                    min_value=100,
                ),
            ],
        )

        # Valid
        assert template.validate_parameters({"word_count": 500}) == []

        # Missing required
        errors = template.validate_parameters({})
        assert len(errors) == 1

        # Too low
        errors = template.validate_parameters({"word_count": 50})
        assert len(errors) == 1

    def test_get_effective_parameters(self):
        """Test getting merged parameters with defaults."""
        template = AgentTemplate(
            name="test",
            version="1.0.0",
            domain="content",
            agent_type="draft",
            parameters=[
                TemplateParameter(
                    name="tone",
                    type=ParameterType.STRING,
                    default="professional",
                ),
                TemplateParameter(
                    name="length",
                    type=ParameterType.INTEGER,
                    default=1000,
                ),
            ],
        )

        # Override one, use default for other
        result = template.get_effective_parameters({"tone": "casual"})

        assert result["tone"] == "casual"
        assert result["length"] == 1000

    def test_get_applicable_prompts(self):
        """Test getting prompts based on conditions."""
        template = AgentTemplate(
            name="test",
            version="1.0.0",
            domain="content",
            agent_type="youtube_script",
            prompts=[
                TemplatePrompt(
                    name="shorts_intro",
                    template="Keep it under 60 seconds!",
                    condition="format == 'shorts'",
                ),
                TemplatePrompt(
                    name="long_intro",
                    template="Take your time to explain...",
                    condition="format == 'long_form'",
                ),
                TemplatePrompt(
                    name="common",
                    template="Always be engaging!",
                ),
            ],
        )

        # For shorts format
        prompts = template.get_applicable_prompts({"format": "shorts"})
        assert "shorts_intro" in prompts
        assert "long_intro" not in prompts
        assert "common" in prompts

    def test_apply_transforms(self):
        """Test applying output transformations."""
        template = AgentTemplate(
            name="test",
            version="1.0.0",
            domain="content",
            agent_type="draft",
            output_transforms=[
                OutputTransform(
                    name="add_generator",
                    transform_type="add",
                    target_field="generated_by",
                    value="Tentackl AI",
                ),
                OutputTransform(
                    name="add_hashtags",
                    condition="format == 'shorts'",
                    transform_type="add",
                    target_field="hashtags",
                    value=["#shorts"],
                ),
            ],
        )

        output = {"title": "Test Video", "script": "..."}

        # Without shorts context
        result = template.apply_transforms(output, {"format": "long_form"})
        assert result["generated_by"] == "Tentackl AI"
        assert "hashtags" not in result

        # With shorts context
        result = template.apply_transforms(output, {"format": "shorts"})
        assert result["generated_by"] == "Tentackl AI"
        assert "hashtags" in result

    def test_yaml_serialization(self):
        """Test YAML export and import."""
        template = AgentTemplate(
            name="test-template",
            version="1.0.0",
            domain="content",
            agent_type="youtube_script",
            description="Test template",
            parameters=[
                TemplateParameter(
                    name="brand_voice",
                    type=ParameterType.STRING,
                    default="professional",
                ),
            ],
            prompts=[
                TemplatePrompt(
                    name="system",
                    template="You are a content creator.",
                ),
            ],
        )

        # Export to YAML
        yaml_str = template.to_yaml()
        assert "name: test-template" in yaml_str
        assert "version: 1.0.0" in yaml_str

        # Import from YAML
        restored = AgentTemplate.from_yaml(yaml_str)
        assert restored.name == template.name
        assert restored.version == template.version
        assert len(restored.parameters) == 1
        assert len(restored.prompts) == 1

    def test_json_serialization(self):
        """Test JSON export and import."""
        template = AgentTemplate(
            name="test-template",
            version="1.0.0",
            domain="content",
            agent_type="draft",
            parameters=[
                TemplateParameter(
                    name="length",
                    type=ParameterType.INTEGER,
                    default=500,
                ),
            ],
        )

        # Export to JSON
        json_str = template.to_json()
        assert '"name": "test-template"' in json_str

        # Import from JSON
        restored = AgentTemplate.from_json(json_str)
        assert restored.name == template.name
        assert len(restored.parameters) == 1


class TestComplexTemplate:
    """Tests for complex real-world template scenarios."""

    def test_youtube_shorts_template(self):
        """Test a realistic YouTube Shorts template."""
        template = AgentTemplate(
            name="brand-youtube-shorts",
            version="1.0.0",
            domain="content",
            agent_type="youtube_script",
            description="Brand-customized YouTube Shorts template",
            parameters=[
                TemplateParameter(
                    name="brand_name",
                    type=ParameterType.STRING,
                    required=True,
                    description="The brand name",
                ),
                TemplateParameter(
                    name="brand_voice",
                    type=ParameterType.ENUM,
                    allowed=["professional", "casual", "fun", "educational"],
                    default="professional",
                ),
                TemplateParameter(
                    name="max_duration",
                    type=ParameterType.INTEGER,
                    default=60,
                    min_value=15,
                    max_value=60,
                ),
                TemplateParameter(
                    name="cta_style",
                    type=ParameterType.ENUM,
                    allowed=["subscribe", "like", "comment", "visit_link"],
                    default="subscribe",
                ),
            ],
            prompts=[
                TemplatePrompt(
                    name="system",
                    template="""You are creating content for {{ brand_name }}.
Brand voice: {{ brand_voice }}
Maximum duration: {{ max_duration }} seconds
Always end with a {{ cta_style }} call-to-action.""",
                ),
            ],
            output_transforms=[
                OutputTransform(
                    name="add_branding",
                    transform_type="add",
                    target_field="branding",
                    value={
                        "brand": "{{ brand_name }}",
                        "voice": "{{ brand_voice }}",
                    },
                ),
                OutputTransform(
                    name="cap_duration",
                    condition="estimated_duration > max_duration",
                    transform_type="modify",
                    target_field="estimated_duration",
                    expression="max_duration",
                ),
            ],
        )

        # Validate template structure
        assert template.validate() == []

        # Test parameter validation
        errors = template.validate_parameters({
            "brand_name": "Acme Corp",
            "brand_voice": "fun",
            "max_duration": 45,
        })
        assert errors == []

        # Test with invalid enum value
        errors = template.validate_parameters({
            "brand_name": "Acme",
            "brand_voice": "boring",  # Not in allowed list
        })
        assert len(errors) == 1

        # Test prompt rendering
        context = {
            "brand_name": "Acme Corp",
            "brand_voice": "fun",
            "max_duration": 45,
            "cta_style": "subscribe",
        }
        system_prompt = template.get_prompt("system", context)
        assert "Acme Corp" in system_prompt
        assert "fun" in system_prompt
        assert "45 seconds" in system_prompt

    def test_marketing_campaign_template(self):
        """Test a marketing campaign content template."""
        template = AgentTemplate(
            name="marketing-campaign",
            version="2.0.0",
            domain="content",
            agent_type="draft",
            parameters=[
                TemplateParameter(
                    name="campaign_name",
                    type=ParameterType.STRING,
                    required=True,
                ),
                TemplateParameter(
                    name="target_platforms",
                    type=ParameterType.LIST,
                    default=["twitter", "blog"],
                ),
                TemplateParameter(
                    name="launch_date",
                    type=ParameterType.STRING,
                    pattern=r"^\d{4}-\d{2}-\d{2}$",  # YYYY-MM-DD
                ),
            ],
            prompts=[
                TemplatePrompt(
                    name="twitter_system",
                    template="Write a tweet for {{ campaign_name }}. Keep under 280 chars.",
                    condition="'twitter' in target_platforms",
                ),
                TemplatePrompt(
                    name="blog_system",
                    template="Write a blog post for {{ campaign_name }}. Be thorough.",
                    condition="'blog' in target_platforms",
                ),
            ],
            output_transforms=[
                OutputTransform(
                    name="add_campaign_meta",
                    transform_type="add",
                    target_field="campaign_metadata",
                    value={
                        "campaign": "{{ campaign_name }}",
                        "generated_at": "{{ timestamp }}",
                    },
                ),
            ],
        )

        # Validate
        assert template.validate() == []

        # Test launch date pattern validation
        errors = template.validate_parameters({
            "campaign_name": "Summer Sale",
            "launch_date": "2024-07-01",
        })
        assert errors == []

        errors = template.validate_parameters({
            "campaign_name": "Summer Sale",
            "launch_date": "July 1st",  # Wrong format
        })
        assert len(errors) == 1
