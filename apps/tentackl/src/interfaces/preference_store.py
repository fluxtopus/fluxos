"""
Preference Store Interface and Data Models

This module defines the interface for learning and storing user preferences
for checkpoint auto-approval in the autonomous task delegation system.

Key concepts:
- UserPreference: A learned pattern from user approval decisions
- Pattern matching: Generalizes from specific contexts to reusable patterns
- Confidence scoring: Higher confidence = more likely to auto-approve
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
import uuid


@dataclass
class PreferencePattern:
    """
    Extracted pattern from a decision context.

    Used for matching similar future contexts.
    """
    fields: Dict[str, Any] = field(default_factory=dict)
    signature: str = ""  # Hash of fields for quick comparison
    confidence_weight: float = 1.0  # Importance weight of this pattern

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fields": self.fields,
            "signature": self.signature,
            "confidence_weight": self.confidence_weight,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PreferencePattern':
        if isinstance(data, dict) and "fields" in data:
            return cls(
                fields=data.get("fields", {}),
                signature=data.get("signature", ""),
                confidence_weight=data.get("confidence_weight", 1.0),
            )
        # Handle legacy format where pattern was just a dict
        return cls(fields=data if isinstance(data, dict) else {})


@dataclass
class UserPreference:
    """
    A learned user preference for checkpoint auto-approval.

    Preferences are learned from user approval decisions and used to
    auto-approve similar future checkpoints when confidence is high enough.

    Example:
        If user always approves email digests, the system learns:
        - preference_key: "email_digest_send"
        - pattern: {"task_type": "notify", "channel": "email", "content_type": "digest"}
        - decision: "approved"
        - confidence: 0.95 (increases with each similar approval)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    preference_key: str = ""  # e.g., "email_digest_send", "api_call_github"
    pattern: 'PreferencePattern' = field(default_factory=PreferencePattern)  # Generalizable pattern
    decision: str = ""  # "approved" or "rejected"
    confidence: float = 1.0  # 0.0 to 1.0, increases with usage
    usage_count: int = 1
    last_used: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate preference"""
        if not self.user_id:
            raise ValueError("user_id is required")
        if not self.preference_key:
            raise ValueError("preference_key is required")
        if not self.decision:
            raise ValueError("decision is required")

    def matches(self, context: Dict[str, Any], threshold: float = 0.8) -> bool:
        """
        Check if this preference matches a given context.

        A preference matches if all pattern keys are present in context
        with matching values.

        Args:
            context: The context to match against
            threshold: Minimum confidence required for match

        Returns:
            bool: True if pattern matches and confidence >= threshold
        """
        if self.confidence < threshold:
            return False

        pattern_fields = self.pattern.fields if isinstance(self.pattern, PreferencePattern) else self.pattern
        for key, value in pattern_fields.items():
            if key not in context or context[key] != value:
                return False

        return True

    def increment_usage(self) -> 'UserPreference':
        """
        Increment usage count and update confidence.

        Confidence increases with usage up to a maximum of 0.99.
        """
        self.usage_count += 1
        self.last_used = datetime.utcnow()
        # Confidence grows with usage: 1.0 - 0.1^usage_count
        # After 1 use: 0.9, 2 uses: 0.99, 3+ uses: ~0.999
        self.confidence = min(0.99, 1.0 - (0.1 ** self.usage_count))
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "preference_key": self.preference_key,
            "pattern": self.pattern.to_dict() if isinstance(self.pattern, PreferencePattern) else self.pattern,
            "decision": self.decision,
            "confidence": self.confidence,
            "usage_count": self.usage_count,
            "last_used": self.last_used.isoformat(),
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserPreference':
        """Create from dictionary"""
        pattern_data = data.get("pattern", {})
        if isinstance(pattern_data, dict):
            pattern = PreferencePattern.from_dict(pattern_data)
        else:
            pattern = PreferencePattern()

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            user_id=data["user_id"],
            preference_key=data["preference_key"],
            pattern=pattern,
            decision=data["decision"],
            confidence=data.get("confidence", 1.0),
            usage_count=data.get("usage_count", 1),
            last_used=datetime.fromisoformat(data["last_used"]) if data.get("last_used") else datetime.utcnow(),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PreferenceMatch:
    """
    Result of a preference matching operation.

    Contains the matched preference (if any) and metadata about the match.
    """
    matched: bool = False
    preference: Optional[UserPreference] = None
    confidence: float = 0.0
    pattern_match_score: float = 0.0  # How well the pattern matched (0-1)
    auto_approve: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched": self.matched,
            "preference_id": self.preference.id if self.preference else None,
            "confidence": self.confidence,
            "pattern_match_score": self.pattern_match_score,
            "auto_approve": self.auto_approve,
            "reason": self.reason,
        }


class PreferenceStoreInterface(ABC):
    """
    Abstract interface for user preference operations.

    Handles learning and retrieving user preferences for checkpoint auto-approval.
    """

    @abstractmethod
    async def record_decision(
        self,
        user_id: str,
        preference_key: str,
        context: Dict[str, Any],
        decision: str
    ) -> UserPreference:
        """
        Record a user decision and learn from it.

        If a similar preference exists, reinforce it.
        Otherwise, create a new preference.

        Args:
            user_id: The user identifier
            preference_key: Key identifying the type of checkpoint
            context: Full context of the decision
            decision: "approved" or "rejected"

        Returns:
            UserPreference: The created or updated preference
        """
        pass

    @abstractmethod
    async def find_matching_preference(
        self,
        user_id: str,
        preference_key: str,
        context: Dict[str, Any],
        confidence_threshold: float = 0.9
    ) -> Optional[PreferenceMatch]:
        """
        Find a preference that matches the given context.

        Used to determine if a checkpoint can be auto-approved.

        Args:
            user_id: The user identifier
            preference_key: Key identifying the type of checkpoint
            context: Context to match against
            confidence_threshold: Minimum confidence for auto-approval

        Returns:
            Optional[PreferenceMatch]: Match result with preference and metadata
        """
        pass

    @abstractmethod
    async def get_user_preferences(
        self,
        user_id: str,
        preference_key: Optional[str] = None,
        limit: int = 100
    ) -> List[UserPreference]:
        """
        Get all preferences for a user.

        Args:
            user_id: The user identifier
            preference_key: Optional filter by preference key
            limit: Maximum number of preferences to return

        Returns:
            List[UserPreference]: List of user preferences
        """
        pass

    @abstractmethod
    async def get_preference(self, preference_id: str) -> Optional[UserPreference]:
        """
        Get a specific preference by ID.

        Args:
            preference_id: The preference identifier

        Returns:
            Optional[UserPreference]: The preference or None
        """
        pass

    @abstractmethod
    async def update_preference(
        self,
        preference_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update a preference.

        Args:
            preference_id: The preference identifier
            updates: Dictionary of fields to update

        Returns:
            bool: True if update successful
        """
        pass

    @abstractmethod
    async def delete_preference(self, preference_id: str) -> bool:
        """
        Delete a preference.

        Args:
            preference_id: The preference identifier

        Returns:
            bool: True if deletion successful
        """
        pass

    @abstractmethod
    async def increment_usage(self, preference_id: str) -> bool:
        """
        Increment the usage count of a preference.

        Called when a preference is used for auto-approval.

        Args:
            preference_id: The preference identifier

        Returns:
            bool: True if successful
        """
        pass

    @abstractmethod
    async def cleanup_unused_preferences(
        self,
        user_id: str,
        unused_days: int = 90
    ) -> int:
        """
        Clean up preferences that haven't been used recently.

        Args:
            user_id: The user identifier
            unused_days: Days since last use to consider unused

        Returns:
            int: Number of preferences cleaned up
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the preference store is healthy.

        Returns:
            bool: True if healthy
        """
        pass


def extract_pattern(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract a generalizable pattern from a specific context.

    This function identifies key features that can match future contexts.
    Only includes fields that are useful for pattern matching.

    Args:
        context: Full context from a checkpoint

    Returns:
        Dict[str, Any]: Extracted pattern with key features
    """
    # Keys that are useful for pattern matching
    PATTERN_KEYS = [
        "task_type",        # http_fetch, summarize, notify, etc.
        "agent_type",       # Type of agent executing
        "channel",          # email, sms, push, etc.
        "content_type",     # digest, alert, report, etc.
        "data_source",      # Where data comes from
        "output_type",      # What kind of output
        "api_domain",       # Which API domain
        "risk_level",       # low, medium, high
    ]

    pattern = {}
    for key in PATTERN_KEYS:
        if key in context:
            pattern[key] = context[key]

    return pattern


def calculate_match_score(pattern, context) -> float:
    """
    Calculate how well a pattern matches a context.

    Returns a score from 0.0 (no match) to 1.0 (perfect match).

    Args:
        pattern: The stored pattern (PreferencePattern or Dict)
        context: The context to match against (PreferencePattern or Dict)

    Returns:
        float: Match score from 0.0 to 1.0
    """
    if not pattern:
        return 0.0

    # Handle PreferencePattern objects
    pattern_fields = pattern.fields if hasattr(pattern, 'fields') else pattern
    context_fields = context.fields if hasattr(context, 'fields') else context

    if not pattern_fields:
        return 0.0

    matches = 0
    total = len(pattern_fields)

    for key, value in pattern_fields.items():
        if key in context_fields and context_fields[key] == value:
            matches += 1

    return matches / total if total > 0 else 0.0


# Exceptions

class PreferenceStoreException(Exception):
    """Base exception for preference store operations"""
    pass


class PreferenceNotFoundError(PreferenceStoreException):
    """Raised when requested preference is not found"""
    pass


class PreferenceValidationError(PreferenceStoreException):
    """Raised when preference data is invalid"""
    pass
