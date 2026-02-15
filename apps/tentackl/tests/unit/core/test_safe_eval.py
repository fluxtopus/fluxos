"""
Unit tests for safe_eval module (SEC-001).

Verifies that the simpleeval-based safe_eval() and safe_eval_condition()
utilities correctly evaluate allowed expressions and block dangerous ones.
"""

import pytest

from src.core.safe_eval import safe_eval, safe_eval_condition


class TestSafeEval:
    """Tests for safe_eval function."""

    def test_simple_arithmetic(self):
        assert safe_eval("2 + 3") == 5
        assert safe_eval("10 - 4") == 6
        assert safe_eval("3 * 7") == 21
        assert safe_eval("15 / 3") == 5.0

    def test_comparisons(self):
        assert safe_eval("5 > 3") is True
        assert safe_eval("2 >= 2") is True
        assert safe_eval("1 < 0") is False
        assert safe_eval("3 == 3") is True
        assert safe_eval("3 != 4") is True

    def test_boolean_logic(self):
        assert safe_eval("True and True") is True
        assert safe_eval("True and False") is False
        assert safe_eval("True or False") is True
        assert safe_eval("not False") is True

    def test_variable_access(self):
        assert safe_eval("x + y", names={"x": 10, "y": 20}) == 30
        assert safe_eval("name == 'alice'", names={"name": "alice"}) is True

    def test_string_containment(self):
        assert safe_eval("'hello' in greeting", names={"greeting": "hello world"}) is True
        assert safe_eval("x in items", names={"x": 2, "items": [1, 2, 3]}) is True

    def test_list_comprehension(self):
        result = safe_eval("[x * 2 for x in items]", names={"items": [1, 2, 3]})
        assert result == [2, 4, 6]

    def test_filtered_list_comprehension(self):
        result = safe_eval(
            "[x for x in items if x > 2]",
            names={"items": [1, 2, 3, 4, 5]},
        )
        assert result == [3, 4, 5]

    def test_dict_access(self):
        data = {"key": "value", "nested": {"inner": 42}}
        assert safe_eval("data['key']", names={"data": data}) == "value"
        assert safe_eval("data['nested']['inner']", names={"data": data}) == 42

    def test_builtin_functions(self):
        assert safe_eval("len(items)", names={"items": [1, 2, 3]}) == 3
        assert safe_eval("str(42)") == "42"
        assert safe_eval("int('7')") == 7
        assert safe_eval("abs(-5)") == 5
        assert safe_eval("min(items)", names={"items": [3, 1, 2]}) == 1
        assert safe_eval("max(items)", names={"items": [3, 1, 2]}) == 3

    def test_ternary_expression(self):
        assert safe_eval("'yes' if x > 0 else 'no'", names={"x": 5}) == "yes"
        assert safe_eval("'yes' if x > 0 else 'no'", names={"x": -1}) == "no"

    def test_blocks_import(self):
        with pytest.raises(Exception):
            safe_eval("__import__('os').system('echo pwned')")

    def test_blocks_dunder_access(self):
        with pytest.raises(Exception):
            safe_eval("().__class__.__bases__[0].__subclasses__()")

    def test_blocks_builtins_bypass(self):
        with pytest.raises(Exception):
            safe_eval("globals()")

    def test_blocks_exec(self):
        with pytest.raises(Exception):
            safe_eval("exec('print(1)')")

    def test_blocks_open(self):
        with pytest.raises(Exception):
            safe_eval("open('/etc/passwd').read()")


class TestSafeEvalCondition:
    """Tests for safe_eval_condition function."""

    def test_simple_true_condition(self):
        assert safe_eval_condition("x > 5", context={"x": 10}) is True

    def test_simple_false_condition(self):
        assert safe_eval_condition("x > 5", context={"x": 2}) is False

    def test_equality_comparison(self):
        assert safe_eval_condition("status == 'active'", context={"status": "active"}) is True
        assert safe_eval_condition("status == 'active'", context={"status": "inactive"}) is False

    def test_compound_condition(self):
        assert safe_eval_condition(
            "score > 80 and status == 'active'",
            context={"score": 85, "status": "active"},
        ) is True
        assert safe_eval_condition(
            "score > 80 and status == 'active'",
            context={"score": 70, "status": "active"},
        ) is False

    def test_containment_check(self):
        assert safe_eval_condition(
            "format == 'shorts'",
            context={"format": "shorts"},
        ) is True

    def test_in_operator(self):
        assert safe_eval_condition(
            "'twitter' in target_platforms",
            context={"target_platforms": ["twitter", "blog"]},
        ) is True
        assert safe_eval_condition(
            "'instagram' in target_platforms",
            context={"target_platforms": ["twitter", "blog"]},
        ) is False

    def test_returns_default_on_error(self):
        # Missing variable - should return default
        assert safe_eval_condition("undefined_var > 10", context={}, default=False) is False
        assert safe_eval_condition("undefined_var > 10", context={}, default=True) is True

    def test_returns_default_on_invalid_expression(self):
        assert safe_eval_condition("???invalid!!!", context={}, default=False) is False

    def test_empty_context(self):
        assert safe_eval_condition("True", context={}) is True
        assert safe_eval_condition("False", context={}) is False

    def test_numeric_comparison_in_context(self):
        context = {"estimated_duration": 75, "max_duration": 60}
        assert safe_eval_condition(
            "estimated_duration > max_duration",
            context=context,
        ) is True

    def test_blocks_dangerous_expressions(self):
        # Should return default (False), not execute dangerous code
        assert safe_eval_condition(
            "__import__('os').system('echo pwned')",
            context={},
            default=False,
        ) is False
