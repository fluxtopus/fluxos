"""Event filtering and transformation utilities for the Event Bus."""

import json
import re
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
import jsonpath_ng
from jsonpath_ng import parse
import structlog

from src.interfaces.event_bus import Event

logger = structlog.get_logger()


@dataclass
class FilterRule:
    """Represents a filter rule for events."""
    field: str  # JSONPath or field name
    operator: str  # eq, ne, gt, lt, gte, lte, in, contains, regex
    value: Any  # Value to compare against
    

@dataclass
class TransformRule:
    """Represents a transformation rule for events."""
    source_path: str  # JSONPath to source value
    target_path: str  # Path in target object
    default: Any = None  # Default value if source not found
    transform_fn: Optional[str] = None  # Optional transformation function


class EventFilter:
    """
    Advanced event filtering engine.
    
    Supports:
    - JSONPath expressions
    - Multiple operators (eq, ne, gt, lt, gte, lte, in, contains, regex)
    - Complex boolean logic (AND, OR, NOT)
    - Nested field access
    """
    
    def __init__(self):
        self._compiled_paths: Dict[str, jsonpath_ng.JSONPath] = {}
        
    def matches(self, event: Event, filter_config: Dict[str, Any]) -> bool:
        """
        Check if event matches filter configuration.
        
        Args:
            event: Event to check
            filter_config: Filter configuration
            
        Returns:
            bool: True if event matches filter
        """
        if not filter_config:
            return True
            
        # Handle different filter formats
        if 'rules' in filter_config:
            return self._evaluate_rules(event, filter_config['rules'], filter_config.get('logic', 'AND'))
        elif 'jsonpath' in filter_config:
            return self._evaluate_jsonpath(event, filter_config['jsonpath'])
        elif 'expression' in filter_config:
            return self._evaluate_expression(event, filter_config['expression'])
        else:
            # Simple key-value matching
            return self._evaluate_simple(event, filter_config)
    
    def _evaluate_rules(self, event: Event, rules: List[Dict[str, Any]], logic: str = 'AND') -> bool:
        """Evaluate a list of filter rules with boolean logic."""
        results = []
        
        for rule_config in rules:
            rule = FilterRule(
                field=rule_config['field'],
                operator=rule_config.get('operator', 'eq'),
                value=rule_config['value']
            )
            results.append(self._evaluate_rule(event, rule))
        
        if logic == 'AND':
            return all(results)
        elif logic == 'OR':
            return any(results)
        elif logic == 'NOT':
            return not any(results)
        else:
            return all(results)  # Default to AND
    
    def _evaluate_rule(self, event: Event, rule: FilterRule) -> bool:
        """Evaluate a single filter rule."""
        # Get value from event
        value = self._get_event_value(event, rule.field)
        
        # Apply operator
        if rule.operator == 'eq':
            return value == rule.value
        elif rule.operator == 'ne':
            return value != rule.value
        elif rule.operator == 'gt':
            return value > rule.value if value is not None else False
        elif rule.operator == 'lt':
            return value < rule.value if value is not None else False
        elif rule.operator == 'gte':
            return value >= rule.value if value is not None else False
        elif rule.operator == 'lte':
            return value <= rule.value if value is not None else False
        elif rule.operator == 'in':
            return value in rule.value if isinstance(rule.value, (list, tuple, set)) else False
        elif rule.operator == 'contains':
            if isinstance(value, str) and isinstance(rule.value, str):
                return rule.value in value
            elif isinstance(value, (list, tuple)):
                return rule.value in value
            return False
        elif rule.operator == 'regex':
            if isinstance(value, str) and isinstance(rule.value, str):
                return bool(re.match(rule.value, value))
            return False
        else:
            logger.warning(f"Unknown operator: {rule.operator}")
            return False
    
    def _evaluate_jsonpath(self, event: Event, jsonpath_expr: str) -> bool:
        """Evaluate a JSONPath expression."""
        try:
            # Convert event to dict for JSONPath evaluation
            event_dict = self._event_to_dict(event)
            
            # Compile and cache JSONPath
            if jsonpath_expr not in self._compiled_paths:
                self._compiled_paths[jsonpath_expr] = parse(jsonpath_expr)
            
            path = self._compiled_paths[jsonpath_expr]
            matches = path.find(event_dict)
            
            # If matches found and any are truthy, return True
            return any(match.value for match in matches)
            
        except Exception as e:
            logger.error(f"Error evaluating JSONPath: {e}", jsonpath=jsonpath_expr)
            return False
    
    def _evaluate_expression(self, event: Event, expression: str) -> bool:
        """Evaluate a simple expression."""
        # This is a placeholder - in production use a safe expression evaluator
        # For now, just return True
        return True
    
    def _evaluate_simple(self, event: Event, filter_config: Dict[str, Any]) -> bool:
        """Evaluate simple key-value matching."""
        for key, expected_value in filter_config.items():
            actual_value = self._get_event_value(event, key)
            if actual_value != expected_value:
                return False
        return True
    
    def _get_event_value(self, event: Event, field: str) -> Any:
        """Get value from event by field path."""
        # Handle dot notation
        if '.' in field:
            parts = field.split('.')
            value = self._event_to_dict(event)
            
            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return None
                    
            return value
        
        # Direct field access
        event_dict = self._event_to_dict(event)
        return event_dict.get(field)
    
    def _event_to_dict(self, event: Event) -> Dict[str, Any]:
        """Convert event to dictionary for processing."""
        return {
            'id': event.id,
            'source': event.source,
            'source_type': event.source_type.value,
            'event_type': event.event_type,
            'timestamp': event.timestamp.isoformat(),
            'data': event.data,
            'metadata': event.metadata,
            'workflow_id': event.workflow_id,
            'agent_id': event.agent_id
        }


class EventTransformer:
    """
    Event transformation engine.
    
    Supports:
    - Field mapping
    - Value transformation
    - Default values
    - Nested object creation
    """
    
    def __init__(self):
        self._compiled_paths: Dict[str, jsonpath_ng.JSONPath] = {}
    
    def transform(self, event: Event, transform_config: Dict[str, Any]) -> Event:
        """
        Transform an event according to configuration.
        
        Args:
            event: Event to transform
            transform_config: Transformation configuration
            
        Returns:
            Event: Transformed event
        """
        if not transform_config:
            return event
        
        # Create new event data
        transformed_data = {}
        
        if 'mapping' in transform_config:
            transformed_data = self._apply_mapping(event, transform_config['mapping'])
        elif 'rules' in transform_config:
            transformed_data = self._apply_rules(event, transform_config['rules'])
        else:
            # Simple field selection
            transformed_data = self._apply_simple(event, transform_config)
        
        # Create new event with transformed data
        return Event(
            id=event.id,  # Keep original ID
            source=event.source,
            source_type=event.source_type,
            event_type=transform_config.get('event_type', event.event_type),
            timestamp=event.timestamp,
            data=transformed_data,
            metadata={**event.metadata, 'original_type': event.event_type},
            workflow_id=event.workflow_id,
            agent_id=event.agent_id
        )
    
    def _apply_mapping(self, event: Event, mapping: Dict[str, Any]) -> Dict[str, Any]:
        """Apply field mapping transformation."""
        result = {}
        event_dict = self._event_to_dict(event)
        
        for target_field, source_config in mapping.items():
            if isinstance(source_config, str):
                # Simple field mapping
                value = self._get_value_by_path(event_dict, source_config)
                if value is not None:
                    self._set_nested_value(result, target_field, value)
            elif isinstance(source_config, dict):
                # Complex mapping with options
                source_path = source_config.get('path', source_config.get('source'))
                default_value = source_config.get('default')
                transform_fn = source_config.get('transform')
                
                value = self._get_value_by_path(event_dict, source_path)
                if value is None:
                    value = default_value
                    
                if value is not None and transform_fn:
                    value = self._apply_transform_function(value, transform_fn)
                    
                if value is not None:
                    self._set_nested_value(result, target_field, value)
        
        return result
    
    def _apply_rules(self, event: Event, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply transformation rules."""
        result = {}
        event_dict = self._event_to_dict(event)
        
        for rule_config in rules:
            rule = TransformRule(
                source_path=rule_config['source'],
                target_path=rule_config['target'],
                default=rule_config.get('default'),
                transform_fn=rule_config.get('transform')
            )
            
            value = self._get_value_by_path(event_dict, rule.source_path)
            if value is None:
                value = rule.default
                
            if value is not None and rule.transform_fn:
                value = self._apply_transform_function(value, rule.transform_fn)
                
            if value is not None:
                self._set_nested_value(result, rule.target_path, value)
        
        return result
    
    def _apply_simple(self, event: Event, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply simple field selection."""
        result = {}
        event_dict = self._event_to_dict(event)
        
        for field in config.get('fields', []):
            value = self._get_value_by_path(event_dict, field)
            if value is not None:
                self._set_nested_value(result, field, value)
        
        return result
    
    def _get_value_by_path(self, data: Dict[str, Any], path: str) -> Any:
        """Get value from nested dictionary by path."""
        if path.startswith('$'):
            # JSONPath expression
            try:
                if path not in self._compiled_paths:
                    self._compiled_paths[path] = parse(path)
                
                jsonpath = self._compiled_paths[path]
                matches = jsonpath.find(data)
                
                if matches:
                    return matches[0].value
                return None
                
            except Exception as e:
                logger.error(f"Error evaluating JSONPath: {e}", path=path)
                return None
        else:
            # Dot notation
            parts = path.split('.')
            value = data
            
            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return None
                    
            return value
    
    def _set_nested_value(self, data: Dict[str, Any], path: str, value: Any):
        """Set value in nested dictionary by path."""
        parts = path.split('.')
        current = data
        
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            current = current[part]
            
        current[parts[-1]] = value
    
    def _apply_transform_function(self, value: Any, transform_fn: str) -> Any:
        """Apply transformation function to value."""
        # Built-in transformations
        if transform_fn == 'uppercase':
            return str(value).upper() if value is not None else None
        elif transform_fn == 'lowercase':
            return str(value).lower() if value is not None else None
        elif transform_fn == 'string':
            return str(value) if value is not None else None
        elif transform_fn == 'int':
            try:
                return int(value)
            except (ValueError, TypeError):
                return None
        elif transform_fn == 'float':
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        elif transform_fn == 'bool':
            return bool(value)
        elif transform_fn == 'json':
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return value
        else:
            # Custom transform functions would be registered here
            return value
    
    def _event_to_dict(self, event: Event) -> Dict[str, Any]:
        """Convert event to dictionary for processing."""
        return {
            'id': event.id,
            'source': event.source,
            'source_type': event.source_type.value,
            'event_type': event.event_type,
            'timestamp': event.timestamp.isoformat(),
            'data': event.data,
            'metadata': event.metadata,
            'workflow_id': event.workflow_id,
            'agent_id': event.agent_id
        }