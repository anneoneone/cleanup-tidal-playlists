"""Synchronization module.

Handles sync decisions, orchestration, conflict resolution, and deduplication.
"""

from .conflict_resolver import (
    Conflict,
    ConflictResolution,
    ConflictResolutionResult,
    ConflictResolver,
    ConflictType,
)
from .decision_engine import (
    DecisionResult,
    SyncAction,
    SyncDecisionEngine,
    SyncDecisions,
)
from .deduplication import (
    DeduplicationLogic,
    DeduplicationResult,
    TrackDistribution,
)
from .download_orchestrator import DownloadOrchestrator, ExecutionResult
from .orchestrator import SyncOrchestrator, SyncResult, SyncStage
from .state import Change, ChangeType, SyncState, SyncStateComparator

__all__ = [
    # Decision engine
    "DecisionResult",
    "SyncAction",
    "SyncDecisionEngine",
    "SyncDecisions",
    # Deduplication
    "DeduplicationLogic",
    "DeduplicationResult",
    "TrackDistribution",
    # Orchestration
    "DownloadOrchestrator",
    "ExecutionResult",
    "SyncOrchestrator",
    "SyncResult",
    "SyncStage",
    # Conflict resolution
    "Conflict",
    "ConflictType",
    "ConflictResolution",
    "ConflictResolver",
    "ConflictResolutionResult",
    # Sync state
    "Change",
    "ChangeType",
    "SyncState",
    "SyncStateComparator",
]
