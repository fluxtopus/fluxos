"""
Test Case Library - Stores and retrieves test cases for prompt evaluation.

Test cases can be stored in the database or loaded from YAML files.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
import yaml

from src.eval.models import (
    FormatRequirements,
    OutputPattern,
    TemplateSyntaxRule,
    TestCase,
    get_template_syntax_rules,
)

logger = structlog.get_logger(__name__)


class TestCaseLibrary:
    """
    Stores and retrieves test cases for prompt evaluation.

    Test cases are stored in memory but can also be loaded from YAML files.
    Database storage can be added later.
    """

    def __init__(self):
        """Initialize the test case library."""
        self._test_cases: Dict[str, TestCase] = {}
        self._by_prompt_type: Dict[str, List[str]] = {}
        self._by_tag: Dict[str, List[str]] = {}

    def add(self, test_case: TestCase) -> None:
        """
        Add a test case to the library.

        Args:
            test_case: TestCase to add
        """
        self._test_cases[test_case.id] = test_case

        # Index by prompt type
        if test_case.prompt_type not in self._by_prompt_type:
            self._by_prompt_type[test_case.prompt_type] = []
        if test_case.id not in self._by_prompt_type[test_case.prompt_type]:
            self._by_prompt_type[test_case.prompt_type].append(test_case.id)

        # Index by tags
        for tag in test_case.tags:
            if tag not in self._by_tag:
                self._by_tag[tag] = []
            if test_case.id not in self._by_tag[tag]:
                self._by_tag[tag].append(test_case.id)

    def get(self, test_case_id: str) -> Optional[TestCase]:
        """
        Get a test case by ID.

        Args:
            test_case_id: ID of the test case

        Returns:
            TestCase or None if not found
        """
        return self._test_cases.get(test_case_id)

    def get_for_prompt_type(
        self,
        prompt_type: str,
        tags: Optional[List[str]] = None,
    ) -> List[TestCase]:
        """
        Get all test cases for a prompt type, optionally filtered by tags.

        Args:
            prompt_type: Type of prompt (e.g., "task_planner")
            tags: Optional list of tags to filter by

        Returns:
            List of matching TestCase objects
        """
        # Get by prompt type
        case_ids = self._by_prompt_type.get(prompt_type, [])

        # Filter by tags if specified
        if tags:
            tag_case_ids = set()
            for tag in tags:
                tag_case_ids.update(self._by_tag.get(tag, []))
            case_ids = [cid for cid in case_ids if cid in tag_case_ids]

        return [self._test_cases[cid] for cid in case_ids if cid in self._test_cases]

    def get_by_tags(self, tags: List[str]) -> List[TestCase]:
        """
        Get all test cases that have any of the specified tags.

        Args:
            tags: List of tags to match

        Returns:
            List of matching TestCase objects
        """
        case_ids = set()
        for tag in tags:
            case_ids.update(self._by_tag.get(tag, []))

        return [self._test_cases[cid] for cid in case_ids if cid in self._test_cases]

    def list_all(self) -> List[TestCase]:
        """
        Get all test cases.

        Returns:
            List of all TestCase objects
        """
        return list(self._test_cases.values())

    def load_from_yaml(self, yaml_path: Path) -> int:
        """
        Load test cases from a YAML file.

        Args:
            yaml_path: Path to YAML file

        Returns:
            Number of test cases loaded
        """
        try:
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)

            test_cases_data = data.get("test_cases", [])
            count = 0

            for tc_data in test_cases_data:
                test_case = self._parse_test_case(tc_data)
                self.add(test_case)
                count += 1

            logger.info("test_cases_loaded", path=str(yaml_path), count=count)
            return count

        except Exception as e:
            logger.error("test_case_load_failed", path=str(yaml_path), error=str(e))
            raise

    def _parse_test_case(self, data: Dict[str, Any]) -> TestCase:
        """
        Parse a test case from dictionary data.

        Args:
            data: Dictionary with test case data

        Returns:
            TestCase object
        """
        # Parse output patterns
        patterns = []
        for pattern_data in data.get("expected_output_patterns", []):
            patterns.append(
                OutputPattern(
                    pattern_type=pattern_data["pattern_type"],
                    pattern=pattern_data["pattern"],
                    description=pattern_data.get("description", ""),
                    weight=pattern_data.get("weight", 1.0),
                    validator=pattern_data.get("validator"),
                )
            )

        # Parse format requirements
        format_data = data.get("format_requirements", {})
        template_rules = None

        if "template_syntax_rules" in format_data:
            # Check if it's a list of rule names or full rules
            rules_data = format_data["template_syntax_rules"]
            if rules_data and isinstance(rules_data[0], str):
                # List of rule names - get from default rules
                default_rules = {r.name: r for r in get_template_syntax_rules()}
                template_rules = [default_rules[name] for name in rules_data if name in default_rules]
            else:
                # Full rule definitions
                template_rules = [
                    TemplateSyntaxRule(
                        name=r["name"],
                        valid_patterns=r.get("valid_patterns", []),
                        invalid_patterns=r.get("invalid_patterns", []),
                        error_message=r["error_message"],
                        severity=r.get("severity", "error"),
                    )
                    for r in rules_data
                ]

        format_requirements = FormatRequirements(
            expected_type=format_data.get("expected_type", "json"),
            json_schema=format_data.get("json_schema"),
            template_syntax_rules=template_rules,
            max_length=format_data.get("max_length"),
            required_fields=format_data.get("required_fields"),
        )

        return TestCase(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            input_context=data.get("input_context", {}),
            expected_output_patterns=patterns,
            format_requirements=format_requirements,
            tags=data.get("tags", []),
            priority=data.get("priority", 0),
            prompt_type=data.get("prompt_type", "general"),
        )


def get_task_planner_test_cases() -> List[TestCase]:
    """
    Get the built-in test cases for task planner template syntax.

    Returns:
        List of TestCase objects for task planner validation
    """
    template_rules = get_template_syntax_rules()

    return [
        TestCase(
            id="template_outputs_plural",
            name="Uses outputs (plural) syntax",
            description="Verify step references use {{step_X.outputs.field}} not {{step_X.output}}",
            prompt_type="task_planner",
            tags=["template_syntax", "critical"],
            priority=10,
            input_context={
                "goal": "Research AI trends and create a summary report"
            },
            expected_output_patterns=[
                OutputPattern(
                    pattern_type="regex",
                    pattern=r"\{\{step_\d+\.outputs\.\w+\}\}",
                    description="Must use outputs.field syntax",
                    weight=2.0,
                ),
                OutputPattern(
                    pattern_type="not_contains",
                    pattern="{{step_1.output}}",
                    description="Must NOT use .output without field",
                    weight=2.0,
                ),
                OutputPattern(
                    pattern_type="not_contains",
                    pattern=".result}}",
                    description="Must NOT use .result accessor",
                    weight=1.5,
                ),
            ],
            format_requirements=FormatRequirements(
                expected_type="json",
                template_syntax_rules=template_rules,
                required_fields=["steps"],
            ),
        ),
        TestCase(
            id="dependencies_match_references",
            name="Dependencies declared for step references",
            description="Steps referencing outputs must declare dependencies",
            prompt_type="task_planner",
            tags=["template_syntax", "semantic"],
            priority=9,
            input_context={
                "goal": "Fetch data from an API and save to storage"
            },
            expected_output_patterns=[
                OutputPattern(
                    pattern_type="custom_validator",
                    pattern="",
                    description="All step references must be in dependencies",
                    validator="dependencies_match_references",
                    weight=2.0,
                ),
            ],
            format_requirements=FormatRequirements(
                expected_type="json",
                template_syntax_rules=template_rules,
            ),
        ),
        TestCase(
            id="correct_output_field_names",
            name="Uses correct agent-specific output fields",
            description="Verify agent-specific output field names are used correctly",
            prompt_type="task_planner",
            tags=["template_syntax", "field_names"],
            priority=8,
            input_context={
                "goal": "Research competitors and compose a marketing report"
            },
            expected_output_patterns=[
                OutputPattern(
                    pattern_type="contains",
                    pattern="web_research",
                    description="Should include research step",
                    weight=1.0,
                ),
                OutputPattern(
                    pattern_type="contains",
                    pattern="compose",
                    description="Should include compose step",
                    weight=1.0,
                ),
            ],
            format_requirements=FormatRequirements(
                expected_type="json",
                template_syntax_rules=template_rules,
            ),
        ),
        TestCase(
            id="multi_step_workflow",
            name="Multi-step workflow with correct chaining",
            description="Complex workflow maintains correct template syntax throughout",
            prompt_type="task_planner",
            tags=["template_syntax", "integration"],
            priority=7,
            input_context={
                "goal": "Research AI, generate an image, upload to CDN, and create a PDF report"
            },
            expected_output_patterns=[
                OutputPattern(
                    pattern_type="contains",
                    pattern="web_research",
                    description="Should include research step",
                    weight=1.0,
                ),
                OutputPattern(
                    pattern_type="contains",
                    pattern="generate_image",
                    description="Should include image generation",
                    weight=1.0,
                ),
                OutputPattern(
                    pattern_type="contains",
                    pattern="file_storage",
                    description="Should include file storage",
                    weight=1.0,
                ),
                OutputPattern(
                    pattern_type="regex",
                    pattern=r"\{\{step_\d+\.outputs\.\w+\}\}",
                    description="Must use correct template syntax",
                    weight=2.0,
                ),
            ],
            format_requirements=FormatRequirements(
                expected_type="json",
                template_syntax_rules=template_rules,
                required_fields=["steps", "plan_summary"],
            ),
        ),
        TestCase(
            id="no_singular_output",
            name="No singular .output accessor",
            description="Ensure .output (singular) is never used",
            prompt_type="task_planner",
            tags=["template_syntax", "critical"],
            priority=10,
            input_context={
                "goal": "Summarize the top 5 HackerNews stories"
            },
            expected_output_patterns=[
                OutputPattern(
                    pattern_type="not_contains",
                    pattern=".output}}",
                    description="Must NOT use singular .output",
                    weight=3.0,
                ),
                OutputPattern(
                    pattern_type="not_contains",
                    pattern=".output.",
                    description="Must NOT use .output. accessor",
                    weight=3.0,
                ),
            ],
            format_requirements=FormatRequirements(
                expected_type="json",
                template_syntax_rules=template_rules,
            ),
        ),
        TestCase(
            id="valid_agent_types_only",
            name="Only uses valid agent types",
            description="All agent_type values must be from the allowed list",
            prompt_type="task_planner",
            tags=["agent_types", "critical"],
            priority=10,
            input_context={
                "goal": "Create a marketing campaign for a new product launch"
            },
            expected_output_patterns=[
                OutputPattern(
                    pattern_type="not_contains",
                    pattern='"agent_type": "marketing_strategist"',
                    description="Must NOT invent marketing_strategist agent type",
                    weight=3.0,
                ),
                OutputPattern(
                    pattern_type="not_contains",
                    pattern='"agent_type": "content_creator"',
                    description="Must NOT invent content_creator agent type",
                    weight=3.0,
                ),
                OutputPattern(
                    pattern_type="not_contains",
                    pattern='"agent_type": "brand_analyst"',
                    description="Must NOT invent brand_analyst agent type",
                    weight=3.0,
                ),
                OutputPattern(
                    pattern_type="not_contains",
                    pattern='"agent_type": "data_scientist"',
                    description="Must NOT invent data_scientist agent type",
                    weight=3.0,
                ),
            ],
            format_requirements=FormatRequirements(
                expected_type="json",
                template_syntax_rules=template_rules,
                validate_agent_types=True,
            ),
        ),
        TestCase(
            id="complex_workflow_valid_agents",
            name="Complex workflow uses only valid agent types",
            description="Multi-step workflows must use valid agent types throughout",
            prompt_type="task_planner",
            tags=["agent_types", "integration"],
            priority=8,
            input_context={
                "goal": "Research competitors, analyze market trends, create a report with charts, convert to PDF, and email to stakeholders"
            },
            expected_output_patterns=[
                OutputPattern(
                    pattern_type="regex",
                    pattern=r'"agent_type":\s*"(web_research|summarize|compose|analyze|file_storage|generate_image|html_to_pdf|pdf_composer|notify)"',
                    description="Agent types must be from valid list",
                    weight=2.0,
                ),
                OutputPattern(
                    pattern_type="regex",
                    pattern=r"\{\{step_\d+\.outputs\.\w+\}\}",
                    description="Must use correct template syntax",
                    weight=2.0,
                ),
            ],
            format_requirements=FormatRequirements(
                expected_type="json",
                template_syntax_rules=template_rules,
                validate_agent_types=True,
                validate_output_fields=True,
            ),
        ),
    ]


# Global library instance
_library: Optional[TestCaseLibrary] = None


def get_library() -> TestCaseLibrary:
    """
    Get the global test case library instance.

    Initializes with built-in test cases if not already done.

    Returns:
        TestCaseLibrary instance
    """
    global _library
    if _library is None:
        _library = TestCaseLibrary()
        # Add built-in test cases
        for tc in get_task_planner_test_cases():
            _library.add(tc)
    return _library
