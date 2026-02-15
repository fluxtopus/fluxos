# REVIEW: Risk detection is entirely heuristic with hard-coded allowlists,
# REVIEW: regexes, and thresholds; the logic is duplicated in code rather than
# REVIEW: configuration or policy. This makes auditability and tenant-specific
# REVIEW: policies difficult. Consider externalizing policies (per org/user)
# REVIEW: and providing a structured rules engine instead of ad-hoc checks.
"""
Risk Detector Service

Automatically identifies operations that require human approval checkpoints.

Risk categories:
- External API calls: Non-allowlisted domains
- Data mutations: Writes, deletes, state changes
- Notifications: Sending emails, SMS, push
- Cost thresholds: Expensive operations
- Sensitive data: PII, credentials, payment info
"""

from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse
import re
import structlog

from src.domain.tasks.models import ApprovalType, CheckpointConfig, TaskStep


logger = structlog.get_logger(__name__)


class RiskLevel(Enum):
    """Risk level classification."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskAssessment:
    """Result of risk assessment for a step."""
    step_id: str
    risk_level: RiskLevel
    risks: List[Dict[str, Any]] = field(default_factory=list)
    requires_checkpoint: bool = False
    checkpoint_config: Optional[CheckpointConfig] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "risk_level": self.risk_level.value,
            "risks": self.risks,
            "requires_checkpoint": self.requires_checkpoint,
            "checkpoint_config": self.checkpoint_config.to_dict() if self.checkpoint_config else None,
            "reason": self.reason,
        }


class RiskDetectorService:
    """
    Service that automatically detects risky operations in plan steps.

    Analyzes steps and determines if they require human approval checkpoints.
    """

    # Default allowed hosts (can be customized per user/org)
    DEFAULT_ALLOWED_HOSTS: Set[str] = {
        # Public APIs
        "api.github.com",
        "hacker-news.firebaseio.com",
        "api.openweathermap.org",
        "wttr.in",
        "pokeapi.co",
        # Internal services
        "localhost",
        "127.0.0.1",
    }

    # Sensitive data patterns
    SENSITIVE_PATTERNS = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "api_key": r"(sk-|api[_-]?key|apikey|secret[_-]?key)[\w\-]{20,}",
        "credit_card": r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}",
        "ssn": r"\d{3}-\d{2}-\d{4}",
        "phone": r"\+?1?\d{10,14}",
        "password": r"(password|passwd|pwd)\s*[:=]\s*\S+",
    }

    # Agent types that typically require checkpoints
    RISKY_AGENT_TYPES = {"notify", "email", "sms", "push", "payment", "delete"}

    def __init__(
        self,
        allowed_hosts: Optional[Set[str]] = None,
        cost_threshold: float = 1.0,
        enable_sensitive_scan: bool = True,
    ):
        """
        Initialize risk detector.

        Args:
            allowed_hosts: Set of allowed API hosts (domains)
            cost_threshold: Dollar amount above which to flag costs
            enable_sensitive_scan: Whether to scan for sensitive data
        """
        self.allowed_hosts = allowed_hosts or self.DEFAULT_ALLOWED_HOSTS.copy()
        self.cost_threshold = cost_threshold
        self.enable_sensitive_scan = enable_sensitive_scan

    def assess_step(self, step: TaskStep) -> RiskAssessment:
        """
        Assess the risk level of a step.

        Args:
            step: The plan step to assess

        Returns:
            RiskAssessment with risk level and checkpoint recommendation
        """
        risks = []
        max_risk = RiskLevel.NONE

        # Check for external API calls
        api_risk = self._check_external_api(step)
        if api_risk:
            risks.append(api_risk)
            max_risk = max(max_risk, RiskLevel(api_risk["level"]), key=lambda r: list(RiskLevel).index(r))

        # Check for notification/communication
        notify_risk = self._check_notification(step)
        if notify_risk:
            risks.append(notify_risk)
            max_risk = max(max_risk, RiskLevel(notify_risk["level"]), key=lambda r: list(RiskLevel).index(r))

        # Check for data mutations
        mutation_risk = self._check_data_mutation(step)
        if mutation_risk:
            risks.append(mutation_risk)
            max_risk = max(max_risk, RiskLevel(mutation_risk["level"]), key=lambda r: list(RiskLevel).index(r))

        # Check for sensitive data
        if self.enable_sensitive_scan:
            sensitive_risk = self._check_sensitive_data(step)
            if sensitive_risk:
                risks.append(sensitive_risk)
                max_risk = max(max_risk, RiskLevel(sensitive_risk["level"]), key=lambda r: list(RiskLevel).index(r))

        # Check for cost
        cost_risk = self._check_cost(step)
        if cost_risk:
            risks.append(cost_risk)
            max_risk = max(max_risk, RiskLevel(cost_risk["level"]), key=lambda r: list(RiskLevel).index(r))

        # Determine if checkpoint is needed
        requires_checkpoint = max_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)

        # Build checkpoint config if needed
        checkpoint_config = None
        if requires_checkpoint:
            checkpoint_config = self._build_checkpoint_config(step, risks)

        reason = self._build_reason(risks) if risks else "No risks detected"

        logger.info(
            "Risk assessment complete",
            step_id=step.id,
            risk_level=max_risk.value,
            risk_count=len(risks),
            requires_checkpoint=requires_checkpoint,
        )

        return RiskAssessment(
            step_id=step.id,
            risk_level=max_risk,
            risks=risks,
            requires_checkpoint=requires_checkpoint,
            checkpoint_config=checkpoint_config,
            reason=reason,
        )

    def assess_plan(self, steps: List[TaskStep]) -> Dict[str, RiskAssessment]:
        """
        Assess all steps in a plan.

        Single Responsibility: This method only ASSESSES risk and returns results.
        The task runtime/use cases are responsible for applying checkpoint requirements.

        Args:
            steps: List of plan steps

        Returns:
            Dict mapping step_id to RiskAssessment
        """
        assessments = {}
        for step in steps:
            assessment = self.assess_step(step)
            assessments[step.id] = assessment
            # Note: We no longer mutate step properties here
            # Runtime application respects the results using this priority chain:
            # subagent metadata → planner → risk detector (additive only)

        return assessments

    def _check_external_api(self, step: TaskStep) -> Optional[Dict[str, Any]]:
        """Check for external API calls to non-allowed hosts."""
        if step.agent_type != "http_fetch":
            return None

        url = step.inputs.get("url", "")
        if not url:
            return None

        try:
            parsed = urlparse(url)
            host = parsed.netloc.lower()

            # Remove port if present
            if ":" in host:
                host = host.split(":")[0]

            if host and host not in self.allowed_hosts:
                return {
                    "type": "external_api",
                    "level": RiskLevel.HIGH.value,
                    "description": f"HTTP request to non-allowed host: {host}",
                    "host": host,
                    "url": url,
                }

        except Exception as e:
            logger.warning("Failed to parse URL for risk check", url=url, error=str(e))

        return None

    def _check_notification(self, step: TaskStep) -> Optional[Dict[str, Any]]:
        """Check for notification/communication operations."""
        if step.agent_type not in self.RISKY_AGENT_TYPES:
            return None

        # Notifications always require approval
        recipient = step.inputs.get("to") or step.inputs.get("recipient")
        channel = step.inputs.get("channel", step.agent_type)

        return {
            "type": "notification",
            "level": RiskLevel.HIGH.value,
            "description": f"Sending {channel} notification to {recipient}",
            "channel": channel,
            "recipient": recipient,
        }

    def _check_data_mutation(self, step: TaskStep) -> Optional[Dict[str, Any]]:
        """Check for data mutation operations."""
        # Check HTTP methods
        method = step.inputs.get("method", "GET").upper()
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            return {
                "type": "data_mutation",
                "level": RiskLevel.MEDIUM.value if method != "DELETE" else RiskLevel.HIGH.value,
                "description": f"Data mutation via HTTP {method}",
                "method": method,
            }

        # Check for database operations
        if step.agent_type in ("database", "db_write", "db_delete"):
            return {
                "type": "data_mutation",
                "level": RiskLevel.HIGH.value,
                "description": f"Database mutation: {step.agent_type}",
            }

        return None

    def _check_sensitive_data(self, step: TaskStep) -> Optional[Dict[str, Any]]:
        """Check for sensitive data in step inputs.

        Note: Email addresses are only flagged for external-facing operations
        (http_fetch, notify, etc.) where they could be leaked. Internal domain
        subagents (support:*, etc.) are expected to handle customer data.
        """
        inputs_str = str(step.inputs)

        # Agent types where email addresses are EXPECTED (internal processing)
        # These are domain subagents that legitimately process customer data
        email_safe_agent_types = {
            "support:get_customer_context",
            "support:send_support_email",
            "analyze",
            "compose",
            "transform",
        }

        detected = []
        for pattern_name, pattern in self.SENSITIVE_PATTERNS.items():
            if re.search(pattern, inputs_str, re.IGNORECASE):
                # Skip email detection for internal processing agents
                if pattern_name == "email" and step.agent_type in email_safe_agent_types:
                    continue
                detected.append(pattern_name)

        if detected:
            return {
                "type": "sensitive_data",
                "level": RiskLevel.HIGH.value,
                "description": f"Sensitive data detected: {', '.join(detected)}",
                "patterns": detected,
            }

        return None

    def _check_cost(self, step: TaskStep) -> Optional[Dict[str, Any]]:
        """Check for high-cost operations."""
        estimated_cost = step.inputs.get("estimated_cost", 0)

        if estimated_cost > self.cost_threshold:
            return {
                "type": "cost",
                "level": RiskLevel.MEDIUM.value if estimated_cost < self.cost_threshold * 5 else RiskLevel.HIGH.value,
                "description": f"Estimated cost ${estimated_cost:.2f} exceeds threshold ${self.cost_threshold:.2f}",
                "estimated_cost": estimated_cost,
                "threshold": self.cost_threshold,
            }

        return None

    def _build_checkpoint_config(
        self, step: TaskStep, risks: List[Dict[str, Any]]
    ) -> CheckpointConfig:
        """Build checkpoint configuration from risks."""
        # Determine primary risk
        primary_risk = max(risks, key=lambda r: list(RiskLevel).index(RiskLevel(r["level"])))
        risk_type = primary_risk["type"]

        # Build name and description
        if risk_type == "notification":
            name = f"{step.agent_type}_send_approval"
            description = f"Approve sending {primary_risk.get('channel', 'notification')} to {primary_risk.get('recipient', 'recipient')}"
            preference_key = f"{step.agent_type}_send"
            preview_fields = ["to", "subject", "body"]
        elif risk_type == "external_api":
            name = f"api_call_{primary_risk.get('host', 'external')}"
            description = f"Approve API call to {primary_risk.get('host', 'external host')}"
            preference_key = f"api_call_{primary_risk.get('host', 'external')}"
            preview_fields = ["url", "method"]
        elif risk_type == "data_mutation":
            name = f"data_mutation_{primary_risk.get('method', 'write')}"
            description = f"Approve data {primary_risk.get('method', 'mutation')}"
            preference_key = f"data_{primary_risk.get('method', 'mutation').lower()}"
            preview_fields = ["url", "method", "body"]
        elif risk_type == "cost":
            name = "cost_approval"
            description = f"Approve operation costing ${primary_risk.get('estimated_cost', 0):.2f}"
            preference_key = "high_cost_operation"
            preview_fields = ["estimated_cost"]
        else:
            name = f"step_{step.id}_approval"
            description = f"Approve step: {step.name}"
            preference_key = f"step_{step.agent_type}"
            preview_fields = list(step.inputs.keys())[:3]

        return CheckpointConfig(
            name=name,
            description=description,
            approval_type=ApprovalType.AUTO,  # Allow auto-approval via preference learning
            timeout_minutes=2880,  # 48 hours
            preference_key=preference_key,
            preview_fields=preview_fields,
        )

    def _build_reason(self, risks: List[Dict[str, Any]]) -> str:
        """Build human-readable reason from risks."""
        if not risks:
            return "No risks detected"

        reasons = [r["description"] for r in risks]
        return "; ".join(reasons)

    def add_allowed_host(self, host: str) -> None:
        """Add a host to the allowed list."""
        self.allowed_hosts.add(host.lower())

    def remove_allowed_host(self, host: str) -> None:
        """Remove a host from the allowed list."""
        self.allowed_hosts.discard(host.lower())

    def set_cost_threshold(self, threshold: float) -> None:
        """Update the cost threshold."""
        self.cost_threshold = threshold
