"""Progress tracking for long-running sync operations.

This module provides callback-based progress tracking for downloads, sync operations,
and other long-running tasks.
"""

import logging
import time
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ProgressPhase(str, Enum):
    """Phases of a sync operation."""

    INITIALIZING = "initializing"
    FETCHING_TIDAL = "fetching_tidal"
    SCANNING_FILESYSTEM = "scanning_filesystem"
    ANALYZING_DEDUPLICATION = "analyzing_deduplication"
    GENERATING_DECISIONS = "generating_decisions"
    EXECUTING_DECISIONS = "executing_decisions"
    DOWNLOADING = "downloading"
    CREATING_SYMLINKS = "creating_symlinks"
    UPDATING_METADATA = "updating_metadata"
    CLEANING_UP = "cleaning_up"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class ProgressUpdate:
    """Progress update information."""

    phase: ProgressPhase
    current: int
    total: int
    message: str = ""
    metadata: Dict[str, Any] = dataclass_field(default_factory=dict)
    elapsed_time: float = 0.0
    estimated_remaining: Optional[float] = None

    @property
    def percentage(self) -> float:
        """Calculate progress percentage."""
        if self.total == 0:
            return 0.0
        return (self.current / self.total) * 100.0

    @property
    def is_complete(self) -> bool:
        """Check if phase is complete."""
        return self.current >= self.total

    def __str__(self) -> str:
        """String representation of progress."""
        parts = [
            f"[{self.phase.value}]",
            f"{self.current}/{self.total}",
            f"({self.percentage:.1f}%)",
        ]
        if self.message:
            parts.append(f"- {self.message}")
        if self.estimated_remaining:
            parts.append(f"(~{self.estimated_remaining:.1f}s remaining)")
        return " ".join(parts)


# Type alias for progress callback function
ProgressCallback = Callable[[ProgressUpdate], None]


class ProgressTracker:
    """Tracks progress of long-running operations."""

    def __init__(
        self,
        callback: Optional[ProgressCallback] = None,
        update_interval: float = 0.5,
    ):
        """Initialize progress tracker.

        Args:
            callback: Function to call with progress updates
            update_interval: Minimum time between updates (seconds)
        """
        self.callback = callback
        self.update_interval = update_interval
        self._last_update_time = 0.0
        self._start_time = 0.0
        self._current_phase: Optional[ProgressPhase] = None
        self._phase_start_time = 0.0
        self._current = 0
        self._total = 0
        self._phase_history: Dict[ProgressPhase, float] = {}

    def start(self, phase: ProgressPhase, total: int, message: str = "") -> None:
        """Start tracking a new phase.

        Args:
            phase: Phase being started
            total: Total items to process
            message: Optional descriptive message
        """
        self._current_phase = phase
        self._phase_start_time = time.time()
        self._current = 0
        self._total = total

        if self._start_time == 0.0:
            self._start_time = self._phase_start_time

        self._notify(message)

    def update(
        self,
        current: Optional[int] = None,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update progress.

        Args:
            current: Current progress (if None, increments by 1)
            message: Optional progress message
            metadata: Optional metadata dictionary
        """
        if current is not None:
            self._current = current
        else:
            self._current += 1

        # Throttle updates based on interval
        current_time = time.time()
        if current_time - self._last_update_time < self.update_interval:
            return

        self._notify(message, metadata)

    def complete(self, message: str = "") -> None:
        """Mark current phase as complete.

        Args:
            message: Optional completion message
        """
        if self._current_phase:
            # Record phase duration
            phase_duration = time.time() - self._phase_start_time
            self._phase_history[self._current_phase] = phase_duration

        self._current = self._total
        self._notify(message)

    def error(self, message: str) -> None:
        """Report an error.

        Args:
            message: Error message
        """
        if self._current_phase:
            self._notify(message, phase=ProgressPhase.ERROR)

    def _notify(
        self,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        phase: Optional[ProgressPhase] = None,
    ) -> None:
        """Send progress update to callback.

        Args:
            message: Progress message
            metadata: Optional metadata
            phase: Optional phase override
        """
        if not self.callback:
            return

        current_time = time.time()
        self._last_update_time = current_time

        # Calculate elapsed time
        elapsed = current_time - self._start_time

        # Estimate remaining time
        estimated_remaining = None
        if self._total > 0 and self._current > 0 and elapsed > 0:
            progress_rate = self._current / elapsed
            remaining_items = self._total - self._current
            estimated_remaining = remaining_items / progress_rate

        update = ProgressUpdate(
            phase=phase or self._current_phase or ProgressPhase.INITIALIZING,
            current=self._current,
            total=self._total,
            message=message,
            metadata=metadata or {},
            elapsed_time=elapsed,
            estimated_remaining=estimated_remaining,
        )

        try:
            self.callback(update)
        except Exception as e:
            logger.error("Error in progress callback: %s", e)

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of progress tracking.

        Returns:
            Dictionary with tracking summary
        """
        total_time = time.time() - self._start_time if self._start_time > 0 else 0
        return {
            "total_time": total_time,
            "phase_history": {
                phase.value: duration for phase, duration in self._phase_history.items()
            },
            "current_phase": (
                self._current_phase.value if self._current_phase else None
            ),
            "progress": f"{self._current}/{self._total}",
            "percentage": (
                (self._current / self._total * 100) if self._total > 0 else 0
            ),
        }


class ConsoleProgressReporter:
    """Simple console progress reporter."""

    def __init__(self, verbose: bool = True):
        """Initialize console reporter.

        Args:
            verbose: Whether to print detailed progress
        """
        self.verbose = verbose
        self._last_phase: Optional[ProgressPhase] = None

    def __call__(self, update: ProgressUpdate) -> None:
        """Handle progress update.

        Args:
            update: Progress update
        """
        # Print phase change
        if update.phase != self._last_phase:
            print(f"\n{'='*60}")
            print(f"Phase: {update.phase.value.upper()}")
            print(f"{'='*60}")
            self._last_phase = update.phase

        # Print progress
        if self.verbose or update.is_complete:
            print(f"  {update}")


class TqdmProgressReporter:
    """Progress reporter using tqdm library."""

    def __init__(self) -> None:
        """Initialize tqdm reporter."""
        try:
            from tqdm import tqdm  # type: ignore[import-untyped]

            self.tqdm = tqdm
            self._bars: Dict[ProgressPhase, Any] = {}
        except ImportError:
            logger.warning("tqdm not installed, falling back to console reporter")
            self.tqdm = None

    def __call__(self, update: ProgressUpdate) -> None:
        """Handle progress update.

        Args:
            update: Progress update
        """
        if not self.tqdm:
            # Fallback to simple console output
            print(f"{update}")
            return

        # Get or create progress bar for this phase
        if update.phase not in self._bars:
            self._bars[update.phase] = self.tqdm(
                total=update.total,
                desc=update.phase.value,
                unit="item",
            )

        bar = self._bars[update.phase]
        bar.n = update.current
        bar.set_postfix_str(update.message if update.message else "")
        bar.refresh()

        # Close bar when complete
        if update.is_complete or update.phase == ProgressPhase.ERROR:
            bar.close()

    def close_all(self) -> None:
        """Close all progress bars."""
        if self.tqdm:
            for bar in self._bars.values():
                if not bar.disable:
                    bar.close()
