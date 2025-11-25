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
    PrimaryFileDecision,
)
from .download_orchestrator import DownloadOrchestrator, ExecutionResult
from .orchestrator import SyncOrchestrator, SyncResult
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
    "PrimaryFileDecision",
    # Orchestration
    "DownloadOrchestrator",
    "ExecutionResult",
    "SyncOrchestrator",
    "SyncResult",
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
