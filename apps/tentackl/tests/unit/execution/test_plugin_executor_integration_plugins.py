"""
Tests for integration plugin registration in PLUGIN_REGISTRY.

Validates that list_integrations and execute_outbound_action are
properly registered and resolve to the correct handlers.
"""

import importlib
import pytest

from src.infrastructure.execution_runtime.plugin_executor import PLUGIN_REGISTRY, is_plugin_type


class TestIntegrationPluginRegistration:
    """Tests for integration plugins in PLUGIN_REGISTRY."""

    def test_list_integrations_in_registry(self):
        """list_integrations is registered in PLUGIN_REGISTRY."""
        assert "list_integrations" in PLUGIN_REGISTRY

    def test_execute_outbound_action_in_registry(self):
        """execute_outbound_action is registered in PLUGIN_REGISTRY."""
        assert "execute_outbound_action" in PLUGIN_REGISTRY

    def test_list_integrations_is_plugin_type(self):
        """list_integrations is identified as a plugin type."""
        assert is_plugin_type("list_integrations") is True

    def test_execute_outbound_action_is_plugin_type(self):
        """execute_outbound_action is identified as a plugin type."""
        assert is_plugin_type("execute_outbound_action") is True

    def test_list_integrations_resolves_to_handler(self):
        """list_integrations resolves to the correct handler function."""
        module_path, handler_name = PLUGIN_REGISTRY["list_integrations"]
        module = importlib.import_module(module_path)
        handler = getattr(module, handler_name)

        assert callable(handler)
        assert handler_name == "list_integrations_handler"

    def test_execute_outbound_action_resolves_to_handler(self):
        """execute_outbound_action resolves to the correct handler function."""
        module_path, handler_name = PLUGIN_REGISTRY["execute_outbound_action"]
        module = importlib.import_module(module_path)
        handler = getattr(module, handler_name)

        assert callable(handler)
        assert handler_name == "execute_outbound_action_handler"
