"""Domain checkpoint models and enums."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class CheckpointDecision(Enum):
    """Possible checkpoint decisions."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"
    EXPIRED = "expired"


class CheckpointType(Enum):
    """Type of interactive checkpoint."""

    APPROVAL = "approval"
    INPUT = "input"
    MODIFY = "modify"
    SELECT = "select"
    QA = "qa"


@dataclass
class CheckpointResponse:
    """User response from an interactive checkpoint."""

    decision: CheckpointDecision
    feedback: Optional[str] = None
    inputs: Optional[Dict[str, Any]] = None
    modified_inputs: Optional[Dict[str, Any]] = None
    selected_alternative: Optional[int] = None
    answers: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "feedback": self.feedback,
            "inputs": self.inputs,
            "modified_inputs": self.modified_inputs,
            "selected_alternative": self.selected_alternative,
            "answers": self.answers,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointResponse":
        decision = data.get("decision")
        if isinstance(decision, str):
            decision = CheckpointDecision(decision)
        return cls(
            decision=decision,
            feedback=data.get("feedback"),
            inputs=data.get("inputs"),
            modified_inputs=data.get("modified_inputs"),
            selected_alternative=data.get("selected_alternative"),
            answers=data.get("answers"),
        )


@dataclass
class CheckpointState:
    """Read model for checkpoint API responses."""

    plan_id: str
    step_id: str
    checkpoint_name: str
    description: str
    decision: CheckpointDecision
    preview_data: Dict[str, Any]
    created_at: datetime
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    auto_approved: bool = False
    preference_used: Optional[str] = None
    feedback: Optional[str] = None
    expires_at: Optional[datetime] = None
    checkpoint_type: CheckpointType = CheckpointType.APPROVAL
    input_schema: Optional[Dict[str, Any]] = None
    questions: Optional[List[str]] = None
    alternatives: Optional[List[Dict[str, Any]]] = None
    modifiable_fields: Optional[List[str]] = None
    context_data: Optional[Dict[str, Any]] = None
    response_inputs: Optional[Dict[str, Any]] = None
    response_modified_inputs: Optional[Dict[str, Any]] = None
    response_selected_alternative: Optional[int] = None
    response_answers: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "step_id": self.step_id,
            "checkpoint_name": self.checkpoint_name,
            "description": self.description,
            "decision": self.decision.value,
            "preview_data": self.preview_data,
            "created_at": self.created_at.isoformat(),
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "decided_by": self.decided_by,
            "auto_approved": self.auto_approved,
            "preference_used": self.preference_used,
            "feedback": self.feedback,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "checkpoint_type": self.checkpoint_type.value,
            "input_schema": self.input_schema,
            "questions": self.questions,
            "alternatives": self.alternatives,
            "modifiable_fields": self.modifiable_fields,
            "context_data": self.context_data,
            "response_inputs": self.response_inputs,
            "response_modified_inputs": self.response_modified_inputs,
            "response_selected_alternative": self.response_selected_alternative,
            "response_answers": self.response_answers,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointState":
        decision = data.get("decision")
        if isinstance(decision, str):
            decision = CheckpointDecision(decision)

        checkpoint_type = data.get("checkpoint_type", "approval")
        if isinstance(checkpoint_type, str):
            checkpoint_type = CheckpointType(checkpoint_type)

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        decided_at = data.get("decided_at")
        if isinstance(decided_at, str):
            decided_at = datetime.fromisoformat(decided_at.replace("Z", "+00:00"))

        expires_at = data.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

        return cls(
            plan_id=data["plan_id"],
            step_id=data["step_id"],
            checkpoint_name=data["checkpoint_name"],
            description=data.get("description", ""),
            decision=decision,
            preview_data=data.get("preview_data", {}),
            created_at=created_at,
            decided_at=decided_at,
            decided_by=data.get("decided_by"),
            auto_approved=data.get("auto_approved", False),
            preference_used=data.get("preference_used"),
            feedback=data.get("feedback"),
            expires_at=expires_at,
            checkpoint_type=checkpoint_type,
            input_schema=data.get("input_schema"),
            questions=data.get("questions"),
            alternatives=data.get("alternatives"),
            modifiable_fields=data.get("modifiable_fields"),
            context_data=data.get("context_data"),
            response_inputs=data.get("response_inputs"),
            response_modified_inputs=data.get("response_modified_inputs"),
            response_selected_alternative=data.get("response_selected_alternative"),
            response_answers=data.get("response_answers"),
        )

    def get_response(self) -> Optional[CheckpointResponse]:
        """Get a response object once the checkpoint has been decided."""

        if self.decision == CheckpointDecision.PENDING:
            return None
        return CheckpointResponse(
            decision=self.decision,
            feedback=self.feedback,
            inputs=self.response_inputs,
            modified_inputs=self.response_modified_inputs,
            selected_alternative=self.response_selected_alternative,
            answers=self.response_answers,
        )
