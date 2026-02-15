"""Unit tests for workflow compiler service"""

import pytest
from src.services.workflow_compiler import WorkflowCompiler


@pytest.fixture
def compiler():
    """Create workflow compiler instance"""
    return WorkflowCompiler()


@pytest.mark.unit
def test_compile_simple_workflow(compiler):
    """Test compiling a simple workflow"""
    workflow_json = {
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "data": {"label": "Start"}
            },
            {
                "id": "2",
                "type": "action",
                "data": {
                    "label": "Send Email",
                    "provider": "email",
                    "template": "welcome"
                }
            }
        ],
        "edges": [
            {"source": "1", "target": "2"}
        ]
    }
    
    result = compiler.compile(workflow_json)
    
    assert "name" in result
    assert "steps" in result
    assert len(result["steps"]) > 0


@pytest.mark.unit
def test_compile_conditional_workflow(compiler):
    """Test compiling workflow with conditional logic"""
    workflow_json = {
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "data": {"label": "Start"}
            },
            {
                "id": "2",
                "type": "condition",
                "data": {
                    "label": "Check Status",
                    "condition": "status == 'active'"
                }
            },
            {
                "id": "3",
                "type": "action",
                "data": {
                    "label": "Send Email",
                    "provider": "email"
                }
            },
            {
                "id": "4",
                "type": "action",
                "data": {
                    "label": "Send SMS",
                    "provider": "sms"
                }
            }
        ],
        "edges": [
            {"source": "1", "target": "2"},
            {"source": "2", "target": "3", "condition": "true"},
            {"source": "2", "target": "4", "condition": "false"}
        ]
    }
    
    result = compiler.compile(workflow_json)
    
    assert "steps" in result
    # Should have conditional steps
    assert any("condition" in step for step in result.get("steps", []))


@pytest.mark.unit
def test_compile_empty_workflow(compiler):
    """Test compiling empty workflow"""
    workflow_json = {
        "nodes": [],
        "edges": []
    }
    
    result = compiler.compile(workflow_json)
    
    assert "steps" in result
    assert len(result["steps"]) == 0


@pytest.mark.unit
def test_compile_multi_provider_workflow(compiler):
    """Test compiling workflow with multiple providers"""
    workflow_json = {
        "nodes": [
            {
                "id": "1",
                "type": "trigger",
                "data": {"label": "Start"}
            },
            {
                "id": "2",
                "type": "action",
                "action_type": "notify",
                "config": {"provider": "email"},
                "provider": "email",
                "data": {"label": "Send Email"}
            },
            {
                "id": "3",
                "type": "action",
                "action_type": "notify",
                "config": {"provider": "sms"},
                "provider": "sms",
                "data": {"label": "Send SMS"}
            },
            {
                "id": "4",
                "type": "action",
                "action_type": "notify",
                "config": {"provider": "slack"},
                "provider": "slack",
                "data": {"label": "Send Slack"}
            }
        ],
        "edges": [
            {"source": "1", "target": "2"},
            {"source": "2", "target": "3"},
            {"source": "3", "target": "4"}
        ]
    }

    result = compiler.compile(workflow_json)

    assert "steps" in result
    steps = result["steps"]
    providers = [step.get("agent", {}).get("config", {}).get("provider") for step in steps]
    providers = [p for p in providers if p]

    # Should have multiple provider steps
    assert len(providers) >= 3

