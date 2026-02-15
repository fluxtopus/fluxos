# REVIEW: Preference learning is a large block of heuristic logic and
# REVIEW: storage access in one class, with many hard-coded thresholds and
# REVIEW: weights. This makes tuning and A/B testing difficult. Consider
# REVIEW: moving thresholds/weights to config and separating matching,
# REVIEW: scoring, and storage into focused components. Also note it’s Redis-only
# REVIEW: and ignores org scoping here, which may not align with multi-tenant needs.
"""
Preference Learning Service

Learns user preferences from checkpoint approval decisions.
Extracts generalizable patterns and matches future contexts.

Key concepts:
- Pattern extraction: Identifies reusable patterns from decisions
- Context matching: Finds similar past decisions for new contexts
- Confidence scoring: Increases confidence with repeated use
- Preference decay: Reduces confidence over time without use
"""

from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import structlog
import hashlib
import json

from src.interfaces.preference_store import (
    UserPreference,
    PreferenceStoreInterface,
    PreferencePattern,
)
from src.infrastructure.tasks.stores.redis_preference_store import RedisPreferenceStore


logger = structlog.get_logger(__name__)


class PatternType(Enum):
    """Types of preference patterns."""
    EXACT = "exact"  # Exact match required
    SIMILAR = "similar"  # Similar context
    CATEGORY = "category"  # Same category/type
    WILDCARD = "wildcard"  # Any in category


@dataclass
class PatternMatch:
    """Result of pattern matching."""
    preference_id: str
    preference_key: str
    decision: str
    confidence: float
    pattern_type: PatternType
    matched_fields: List[str]
    mismatched_fields: List[str]
    usage_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preference_id": self.preference_id,
            "preference_key": self.preference_key,
            "decision": self.decision,
            "confidence": self.confidence,
            "pattern_type": self.pattern_type.value,
            "matched_fields": self.matched_fields,
            "mismatched_fields": self.mismatched_fields,
            "usage_count": self.usage_count,
        }


@dataclass
class LearningResult:
    """Result of learning from a decision."""
    preference_id: str
    pattern_extracted: PreferencePattern
    is_new: bool
    merged_with: Optional[str] = None
    confidence_change: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preference_id": self.preference_id,
            "pattern_extracted": self.pattern_extracted.to_dict(),
            "is_new": self.is_new,
            "merged_with": self.merged_with,
            "confidence_change": self.confidence_change,
        }


class PreferenceLearningService:
    """
    Service that learns user preferences from approval decisions.

    Features:
    - Pattern extraction from decision context
    - Similarity-based matching
    - Confidence scoring and decay
    - Pattern merging for similar decisions
    """

    # Configuration
    AUTO_APPROVAL_THRESHOLD = 0.9
    INITIAL_CONFIDENCE = 1.0
    CONFIDENCE_DECAY_DAYS = 30
    DECAY_RATE = 0.1
    MIN_CONFIDENCE = 0.5
    SIMILARITY_THRESHOLD = 0.7

    # Fields that are important for pattern matching
    PATTERN_FIELDS = {
        "agent_type": 1.0,  # Weight
        "checkpoint_name": 0.8,
        "step_name": 0.5,
        "url": 0.7,
        "to": 0.9,  # Email recipient
        "method": 0.6,
        "channel": 0.8,
        "content_type": 0.6,
    }

    def __init__(
        self,
        preference_store: Optional[PreferenceStoreInterface] = None,
        auto_approval_threshold: float = None,
    ):
        """
        Initialize preference learning service.

        Args:
            preference_store: Storage backend for preferences
            auto_approval_threshold: Confidence threshold for auto-approval
        """
        self._preference_store = preference_store
        self.auto_approval_threshold = auto_approval_threshold or self.AUTO_APPROVAL_THRESHOLD

    async def _get_store(self) -> PreferenceStoreInterface:
        """Get or create preference store."""
        if not self._preference_store:
            self._preference_store = RedisPreferenceStore()
            await self._preference_store._connect()
        return self._preference_store

    async def learn_from_decision(
        self,
        user_id: str,
        preference_key: str,
        context: Dict[str, Any],
        decision: str,
        feedback: Optional[str] = None,
    ) -> LearningResult:
        """
        Learn from a user's approval/rejection decision.

        Extracts patterns from the context and stores as preference.
        May merge with existing similar preferences.

        Args:
            user_id: User making the decision
            preference_key: Key for this preference type
            context: Full context of the decision
            decision: "approved" or "rejected"
            feedback: Optional user feedback

        Returns:
            LearningResult with details of what was learned
        """
        logger.info(
            "Learning from decision",
            user_id=user_id,
            preference_key=preference_key,
            decision=decision,
        )

        store = await self._get_store()

        # Extract pattern from context
        pattern = self._extract_pattern(context)

        # Check for existing similar preference
        existing = await self._find_similar_preference(user_id, preference_key, pattern)

        if existing:
            # Merge with existing preference
            merged = await self._merge_preference(existing, decision, pattern, feedback)
            return LearningResult(
                preference_id=existing.id,
                pattern_extracted=pattern,
                is_new=False,
                merged_with=existing.id,
                confidence_change=merged["confidence_change"],
            )

        # Create new preference
        pref_id = await store.record_decision(
            user_id=user_id,
            preference_key=preference_key,
            context=context,
            decision=decision,
            feedback=feedback,
        )

        return LearningResult(
            preference_id=pref_id,
            pattern_extracted=pattern,
            is_new=True,
            confidence_change=self.INITIAL_CONFIDENCE,
        )

    async def find_matching_preference(
        self,
        user_id: str,
        preference_key: str,
        context: Dict[str, Any],
    ) -> Optional[PatternMatch]:
        """
        Find a preference that matches the given context.

        Args:
            user_id: User to match preferences for
            preference_key: Type of preference
            context: Context to match against

        Returns:
            PatternMatch if found with sufficient confidence, None otherwise
        """
        store = await self._get_store()

        # Get user preferences for this key
        preferences = await store.get_user_preferences(user_id)
        preferences = [p for p in preferences if p.preference_key == preference_key]

        if not preferences:
            return None

        # Extract pattern from current context
        current_pattern = self._extract_pattern(context)

        # Find best match
        best_match = None
        best_score = 0.0

        for pref in preferences:
            match_result = self._match_pattern(current_pattern, pref.pattern, pref)

            if match_result and match_result.confidence > best_score:
                best_score = match_result.confidence
                best_match = match_result

        return best_match

    async def should_auto_approve(
        self,
        user_id: str,
        preference_key: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Determine if a checkpoint should be auto-approved.

        Args:
            user_id: User to check preferences for
            preference_key: Type of preference
            context: Context to evaluate

        Returns:
            Dict with 'auto_approve' bool and details
        """
        match = await self.find_matching_preference(user_id, preference_key, context)

        if not match:
            return {
                "auto_approve": False,
                "reason": "no_matching_preference",
            }

        if match.confidence < self.auto_approval_threshold:
            return {
                "auto_approve": False,
                "reason": "confidence_below_threshold",
                "confidence": match.confidence,
                "threshold": self.auto_approval_threshold,
            }

        if match.decision != "approved":
            return {
                "auto_approve": False,
                "reason": "previous_rejection",
                "decision": match.decision,
            }

        # Auto-approve!
        return {
            "auto_approve": True,
            "preference_id": match.preference_id,
            "confidence": match.confidence,
            "usage_count": match.usage_count,
            "pattern_type": match.pattern_type.value,
        }

    async def decay_old_preferences(self, user_id: Optional[str] = None) -> int:
        """
        Apply confidence decay to old unused preferences.

        Args:
            user_id: Optional user to decay for (all users if None)

        Returns:
            Number of preferences updated
        """
        store = await self._get_store()

        if user_id:
            preferences = await store.get_user_preferences(user_id)
        else:
            # Would need to iterate all users - not implemented
            logger.warning("Decay for all users not implemented")
            return 0

        updated = 0
        now = datetime.utcnow()

        for pref in preferences:
            days_since_use = (now - pref.last_used).days

            if days_since_use > self.CONFIDENCE_DECAY_DAYS:
                # Apply decay
                decay_periods = (days_since_use - self.CONFIDENCE_DECAY_DAYS) // self.CONFIDENCE_DECAY_DAYS
                new_confidence = max(
                    self.MIN_CONFIDENCE,
                    pref.confidence * ((1 - self.DECAY_RATE) ** decay_periods)
                )

                if new_confidence != pref.confidence:
                    await store.update_preference(pref.id, {"confidence": new_confidence})
                    updated += 1

        logger.info("Preference decay applied", user_id=user_id, updated=updated)
        return updated

    async def get_preference_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get statistics about user's preferences.

        Args:
            user_id: User to get stats for

        Returns:
            Dict with preference statistics
        """
        store = await self._get_store()
        preferences = await store.get_user_preferences(user_id)

        if not preferences:
            return {
                "total_preferences": 0,
                "high_confidence": 0,
                "approvals": 0,
                "rejections": 0,
            }

        approvals = [p for p in preferences if p.decision == "approved"]
        rejections = [p for p in preferences if p.decision == "rejected"]
        high_conf = [p for p in preferences if p.confidence >= self.auto_approval_threshold]

        return {
            "total_preferences": len(preferences),
            "high_confidence": len(high_conf),
            "approvals": len(approvals),
            "rejections": len(rejections),
            "by_key": self._group_by_key(preferences),
            "avg_confidence": sum(p.confidence for p in preferences) / len(preferences),
            "total_usage": sum(p.usage_count for p in preferences),
        }

    def _extract_pattern(self, context: Dict[str, Any]) -> PreferencePattern:
        """Extract a generalizable pattern from context."""
        # Get relevant fields with values
        fields = {}
        for field, weight in self.PATTERN_FIELDS.items():
            if field in context and context[field]:
                fields[field] = context[field]

        # Generate pattern signature
        signature_data = json.dumps(fields, sort_keys=True)
        signature = hashlib.sha256(signature_data.encode()).hexdigest()[:16]

        return PreferencePattern(
            fields=fields,
            signature=signature,
            confidence_weight=self._calculate_pattern_weight(fields),
        )

    def _match_pattern(
        self,
        current: PreferencePattern,
        stored: PreferencePattern,
        preference: UserPreference,
    ) -> Optional[PatternMatch]:
        """
        Match current pattern against stored pattern.

        Returns PatternMatch if similar enough.
        """
        matched_fields = []
        mismatched_fields = []
        total_weight = 0.0
        matched_weight = 0.0

        # Check each field
        all_fields = set(current.fields.keys()) | set(stored.fields.keys())

        for field in all_fields:
            weight = self.PATTERN_FIELDS.get(field, 0.5)
            total_weight += weight

            current_val = current.fields.get(field)
            stored_val = stored.fields.get(field)

            if current_val == stored_val:
                matched_fields.append(field)
                matched_weight += weight
            elif self._values_similar(current_val, stored_val):
                matched_fields.append(field)
                matched_weight += weight * 0.7  # Partial match
            else:
                mismatched_fields.append(field)

        if total_weight == 0:
            return None

        # Calculate similarity score
        similarity = matched_weight / total_weight

        if similarity < self.SIMILARITY_THRESHOLD:
            return None

        # Determine pattern type
        if current.signature == stored.signature:
            pattern_type = PatternType.EXACT
        elif similarity >= 0.9:
            pattern_type = PatternType.SIMILAR
        else:
            pattern_type = PatternType.CATEGORY

        # Adjust confidence based on similarity and usage
        base_confidence = preference.confidence * similarity
        usage_boost = min(0.1, preference.usage_count * 0.01)
        final_confidence = min(1.0, base_confidence + usage_boost)

        return PatternMatch(
            preference_id=preference.id,
            preference_key=preference.preference_key,
            decision=preference.decision,
            confidence=final_confidence,
            pattern_type=pattern_type,
            matched_fields=matched_fields,
            mismatched_fields=mismatched_fields,
            usage_count=preference.usage_count,
        )

    def _values_similar(self, val1: Any, val2: Any) -> bool:
        """Check if two values are similar (not exact match)."""
        if val1 is None or val2 is None:
            return False

        if isinstance(val1, str) and isinstance(val2, str):
            # Domain matching for URLs
            if "://" in val1 and "://" in val2:
                domain1 = val1.split("://")[1].split("/")[0]
                domain2 = val2.split("://")[1].split("/")[0]
                return domain1 == domain2

            # Email domain matching
            if "@" in val1 and "@" in val2:
                domain1 = val1.split("@")[1]
                domain2 = val2.split("@")[1]
                return domain1 == domain2

        return False

    async def _find_similar_preference(
        self,
        user_id: str,
        preference_key: str,
        pattern: PreferencePattern,
    ) -> Optional[UserPreference]:
        """Find an existing similar preference to merge with."""
        store = await self._get_store()
        preferences = await store.get_user_preferences(user_id)

        for pref in preferences:
            if pref.preference_key != preference_key:
                continue

            # Check signature match
            if pref.pattern.signature == pattern.signature:
                return pref

            # Check high similarity
            match = self._match_pattern(pattern, pref.pattern, pref)
            if match and match.confidence >= 0.95:
                return pref

        return None

    async def _merge_preference(
        self,
        existing: UserPreference,
        new_decision: str,
        new_pattern: PreferencePattern,
        feedback: Optional[str],
    ) -> Dict[str, Any]:
        """Merge new decision into existing preference."""
        store = await self._get_store()

        old_confidence = existing.confidence

        # If same decision, increase confidence
        if new_decision == existing.decision:
            new_confidence = min(1.0, existing.confidence + 0.1)
        else:
            # Conflicting decision - decrease confidence
            new_confidence = max(0.0, existing.confidence - 0.3)

        await store.update_preference(existing.id, {
            "confidence": new_confidence,
            "usage_count": existing.usage_count + 1,
            "last_used": datetime.utcnow(),
            "feedback": feedback or existing.feedback,
        })

        return {
            "confidence_change": new_confidence - old_confidence,
            "new_confidence": new_confidence,
        }

    def _calculate_pattern_weight(self, fields: Dict[str, Any]) -> float:
        """Calculate the importance weight of a pattern."""
        total = 0.0
        for field in fields:
            total += self.PATTERN_FIELDS.get(field, 0.5)
        return total

    def _group_by_key(self, preferences: List[UserPreference]) -> Dict[str, int]:
        """Group preferences by key."""
        groups = {}
        for pref in preferences:
            key = pref.preference_key
            groups[key] = groups.get(key, 0) + 1
        return groups

    async def cleanup(self) -> None:
        """Cleanup service resources."""
        if self._preference_store:
            await self._preference_store._disconnect()

    async def learn_from_replan(
        self,
        user_id: str,
        plan_id: str,
        diagnosis: str,
        approved: bool,
    ) -> Optional[LearningResult]:
        """
        Learn from a replan approval/rejection.

        This helps the system learn when replans are appropriate
        based on certain diagnoses (e.g., invalid agent types).

        Args:
            user_id: User who made the decision
            plan_id: Plan that was replanned
            diagnosis: The diagnosis that led to the replan
            approved: Whether the replan was approved

        Returns:
            LearningResult if a preference was recorded
        """
        logger.info(
            "Learning from replan decision",
            user_id=user_id,
            plan_id=plan_id,
            diagnosis=diagnosis[:100],
            approved=approved,
        )

        # Extract key information from the diagnosis
        context = {
            "plan_id": plan_id,
            "diagnosis": diagnosis,
            "replan_type": self._classify_replan(diagnosis),
        }

        decision = "approved" if approved else "rejected"

        try:
            return await self.learn_from_decision(
                user_id=user_id,
                preference_key="replan",
                context=context,
                decision=decision,
                feedback=None,
            )
        except Exception as e:
            logger.warning(
                "Failed to learn from replan",
                error=str(e),
                user_id=user_id,
                plan_id=plan_id,
            )
            return None

    def _classify_replan(self, diagnosis: str) -> str:
        """Classify the type of replan based on diagnosis."""
        diagnosis_lower = diagnosis.lower()

        if "invalid agent type" in diagnosis_lower or "unknown subagent" in diagnosis_lower:
            return "invalid_agent_type"
        elif "template" in diagnosis_lower or "syntax" in diagnosis_lower:
            return "template_error"
        elif "blocked" in diagnosis_lower or "dependency" in diagnosis_lower:
            return "blocked_steps"
        elif "failed" in diagnosis_lower:
            return "step_failure"
        else:
            return "other"
