# REVIEW: Exposes a large surface but doesn't manage shared lifecycle; consumers
# REVIEW: often instantiate their own services.
"""
Task services module.

Provides high-level services for autonomous task execution:
- CheckpointManager: Handles checkpoint approvals
- PreferenceLearningService: Learns user preferences
- RiskDetectorService: Detects risky operations
"""

from src.domain.tasks.risk_detector import (
    RiskDetectorService,
    RiskLevel,
    RiskAssessment,
)
from src.infrastructure.tasks.checkpoint_manager import CheckpointManager
from src.domain.checkpoints.models import (
    CheckpointState,
    CheckpointDecision,
)
from src.infrastructure.tasks.preference_learning import (
    PreferenceLearningService,
    PatternMatch,
    PatternType,
    LearningResult,
)
__all__ = [
    # Risk Detection
    "RiskDetectorService",
    "RiskLevel",
    "RiskAssessment",
    # Checkpoint Management
    "CheckpointManager",
    "CheckpointState",
    "CheckpointDecision",
    # Preference Learning
    "PreferenceLearningService",
    "PatternMatch",
    "PatternType",
    "LearningResult",
]
