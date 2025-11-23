"""Tests for progress tracker."""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from tidal_cleanup.database.progress_tracker import (
    ConsoleProgressReporter,
    ProgressPhase,
    ProgressTracker,
    ProgressUpdate,
    TqdmProgressReporter,
)


class TestProgressUpdate:
    """Test ProgressUpdate dataclass."""

    def test_initialization(self):
        """Test ProgressUpdate initialization with defaults."""
        update = ProgressUpdate(
            phase=ProgressPhase.DOWNLOADING,
            current=5,
            total=10,
        )
        assert update.phase == ProgressPhase.DOWNLOADING
        assert update.current == 5
        assert update.total == 10
        assert update.message == ""
        assert update.metadata == {}
        assert update.elapsed_time == 0.0
        assert update.estimated_remaining is None

    def test_initialization_with_all_fields(self):
        """Test ProgressUpdate initialization with all fields."""
        metadata = {"file": "test.mp3"}
        update = ProgressUpdate(
            phase=ProgressPhase.DOWNLOADING,
            current=5,
            total=10,
            message="Downloading track",
            metadata=metadata,
            elapsed_time=2.5,
            estimated_remaining=2.5,
        )
        assert update.message == "Downloading track"
        assert update.metadata == metadata
        assert update.elapsed_time == 2.5
        assert update.estimated_remaining == 2.5

    def test_percentage_calculation(self):
        """Test percentage property calculation."""
        update = ProgressUpdate(phase=ProgressPhase.DOWNLOADING, current=5, total=10)
        assert update.percentage == 50.0

    def test_percentage_zero_total(self):
        """Test percentage with zero total."""
        update = ProgressUpdate(phase=ProgressPhase.DOWNLOADING, current=5, total=0)
        assert update.percentage == 0.0

    def test_percentage_complete(self):
        """Test percentage at 100%."""
        update = ProgressUpdate(phase=ProgressPhase.DOWNLOADING, current=10, total=10)
        assert update.percentage == 100.0

    def test_is_complete_true(self):
        """Test is_complete when current equals total."""
        update = ProgressUpdate(phase=ProgressPhase.DOWNLOADING, current=10, total=10)
        assert update.is_complete is True

    def test_is_complete_exceeds(self):
        """Test is_complete when current exceeds total."""
        update = ProgressUpdate(phase=ProgressPhase.DOWNLOADING, current=11, total=10)
        assert update.is_complete is True

    def test_is_complete_false(self):
        """Test is_complete when current less than total."""
        update = ProgressUpdate(phase=ProgressPhase.DOWNLOADING, current=5, total=10)
        assert update.is_complete is False

    def test_str_basic(self):
        """Test string representation with basic fields."""
        update = ProgressUpdate(phase=ProgressPhase.DOWNLOADING, current=5, total=10)
        result = str(update)
        assert "[downloading]" in result
        assert "5/10" in result
        assert "50.0%" in result

    def test_str_with_message(self):
        """Test string representation with message."""
        update = ProgressUpdate(
            phase=ProgressPhase.DOWNLOADING,
            current=5,
            total=10,
            message="Processing file.mp3",
        )
        result = str(update)
        assert "Processing file.mp3" in result

    def test_str_with_estimated_remaining(self):
        """Test string representation with estimated remaining time."""
        update = ProgressUpdate(
            phase=ProgressPhase.DOWNLOADING,
            current=5,
            total=10,
            estimated_remaining=5.5,
        )
        result = str(update)
        assert "5.5s remaining" in result


class TestProgressTracker:
    """Test ProgressTracker class."""

    def test_initialization_with_defaults(self):
        """Test ProgressTracker initialization with defaults."""
        tracker = ProgressTracker()
        assert tracker.callback is None
        assert tracker.update_interval == 0.5
        assert tracker._current_phase is None
        assert tracker._current == 0
        assert tracker._total == 0

    def test_initialization_with_callback(self):
        """Test ProgressTracker initialization with callback."""
        callback = Mock()
        tracker = ProgressTracker(callback=callback, update_interval=1.0)
        assert tracker.callback == callback
        assert tracker.update_interval == 1.0

    def test_start_phase(self):
        """Test starting a new phase."""
        callback = Mock()
        tracker = ProgressTracker(callback=callback)

        tracker.start(ProgressPhase.DOWNLOADING, total=10, message="Starting download")

        assert tracker._current_phase == ProgressPhase.DOWNLOADING
        assert tracker._current == 0
        assert tracker._total == 10
        assert tracker._start_time > 0
        assert tracker._phase_start_time > 0

        # Verify callback was called
        callback.assert_called_once()
        update = callback.call_args[0][0]
        assert update.phase == ProgressPhase.DOWNLOADING
        assert update.current == 0
        assert update.total == 10
        assert update.message == "Starting download"

    def test_start_first_phase_sets_start_time(self):
        """Test that starting first phase sets overall start time."""
        tracker = ProgressTracker()
        tracker.start(ProgressPhase.INITIALIZING, total=5)

        start_time = tracker._start_time
        assert start_time > 0

        # Starting second phase should not change start_time
        time.sleep(0.01)
        tracker.start(ProgressPhase.DOWNLOADING, total=10)
        assert tracker._start_time == start_time

    def test_update_with_explicit_current(self):
        """Test updating progress with explicit current value."""
        callback = Mock()
        tracker = ProgressTracker(callback=callback, update_interval=0.0)

        tracker.start(ProgressPhase.DOWNLOADING, total=10)
        callback.reset_mock()

        tracker.update(current=5, message="Halfway done")

        assert tracker._current == 5
        callback.assert_called_once()
        update = callback.call_args[0][0]
        assert update.current == 5
        assert update.message == "Halfway done"

    def test_update_increment(self):
        """Test updating progress by incrementing."""
        callback = Mock()
        tracker = ProgressTracker(callback=callback, update_interval=0.0)

        tracker.start(ProgressPhase.DOWNLOADING, total=10)
        callback.reset_mock()

        # Call update without current parameter
        tracker.update(message="Step 1")
        assert tracker._current == 1

        tracker.update(message="Step 2")
        assert tracker._current == 2

    def test_update_with_metadata(self):
        """Test updating progress with metadata."""
        callback = Mock()
        tracker = ProgressTracker(callback=callback, update_interval=0.0)

        tracker.start(ProgressPhase.DOWNLOADING, total=10)
        callback.reset_mock()

        metadata = {"filename": "test.mp3", "size": 1024}
        tracker.update(current=1, metadata=metadata)

        update = callback.call_args[0][0]
        assert update.metadata == metadata

    def test_update_throttling(self):
        """Test that updates are throttled based on interval."""
        callback = Mock()
        tracker = ProgressTracker(callback=callback, update_interval=1.0)

        # start() calls _notify which updates _last_update_time
        tracker.start(ProgressPhase.DOWNLOADING, total=10)
        assert callback.call_count == 1
        callback.reset_mock()

        # Rapid updates should all be throttled because start() set _last_update_time
        tracker.update(current=1)
        tracker.update(current=2)
        tracker.update(current=3)

        # No calls should go through due to throttling
        assert callback.call_count == 0

    def test_update_throttling_respects_interval(self):
        """Test that updates go through after interval passes."""
        callback = Mock()
        tracker = ProgressTracker(callback=callback, update_interval=0.01)

        tracker.start(ProgressPhase.DOWNLOADING, total=10)
        assert callback.call_count == 1
        callback.reset_mock()

        # Wait for throttle interval to pass after start()
        time.sleep(0.02)

        # First update after interval should go through
        tracker.update(current=1)
        assert callback.call_count == 1

        # Wait again for throttle interval
        time.sleep(0.02)

        # Second update should go through after interval
        tracker.update(current=2)
        assert callback.call_count == 2

    def test_complete_marks_phase_complete(self):
        """Test completing a phase."""
        callback = Mock()
        tracker = ProgressTracker(callback=callback, update_interval=0.0)

        tracker.start(ProgressPhase.DOWNLOADING, total=10)
        callback.reset_mock()

        tracker.complete(message="Download complete")

        assert tracker._current == 10
        callback.assert_called_once()
        update = callback.call_args[0][0]
        assert update.current == 10
        assert update.is_complete is True
        assert update.message == "Download complete"

    def test_complete_records_phase_duration(self):
        """Test that completing phase records duration in history."""
        tracker = ProgressTracker()

        tracker.start(ProgressPhase.DOWNLOADING, total=10)
        time.sleep(0.01)
        tracker.complete()

        assert ProgressPhase.DOWNLOADING in tracker._phase_history
        assert tracker._phase_history[ProgressPhase.DOWNLOADING] > 0

    def test_error_reports_error_phase(self):
        """Test error reporting."""
        callback = Mock()
        tracker = ProgressTracker(callback=callback)

        tracker.start(ProgressPhase.DOWNLOADING, total=10)
        callback.reset_mock()

        tracker.error("Download failed")

        callback.assert_called_once()
        update = callback.call_args[0][0]
        assert update.phase == ProgressPhase.ERROR
        assert update.message == "Download failed"

    def test_notify_without_callback(self):
        """Test that notify without callback doesn't crash."""
        tracker = ProgressTracker(callback=None)
        tracker.start(ProgressPhase.DOWNLOADING, total=10)
        tracker.update(current=5)
        tracker.complete()
        # Should not raise exception

    def test_notify_with_callback_exception(self):
        """Test that callback exceptions are caught and logged."""
        callback = Mock(side_effect=Exception("Callback error"))
        tracker = ProgressTracker(callback=callback)

        # Should not raise exception
        tracker.start(ProgressPhase.DOWNLOADING, total=10)

    def test_estimated_remaining_time_calculation(self):
        """Test estimated remaining time calculation."""
        callback = Mock()
        tracker = ProgressTracker(callback=callback, update_interval=0.0)

        tracker.start(ProgressPhase.DOWNLOADING, total=10)
        callback.reset_mock()

        # Simulate some elapsed time and progress
        tracker._start_time = time.time() - 2.0  # 2 seconds elapsed
        tracker.update(current=5)  # 50% done

        update = callback.call_args[0][0]
        # 50% done in 2 seconds means ~2 seconds remaining
        assert update.estimated_remaining is not None
        assert 1.5 < update.estimated_remaining < 2.5

    def test_estimated_remaining_none_when_no_progress(self):
        """Test estimated remaining is None when current is 0."""
        callback = Mock()
        tracker = ProgressTracker(callback=callback)

        tracker.start(ProgressPhase.DOWNLOADING, total=10)

        update = callback.call_args[0][0]
        assert update.estimated_remaining is None

    def test_estimated_remaining_none_when_total_zero(self):
        """Test estimated remaining is None when total is 0."""
        callback = Mock()
        tracker = ProgressTracker(callback=callback)

        tracker.start(ProgressPhase.DOWNLOADING, total=0)

        update = callback.call_args[0][0]
        assert update.estimated_remaining is None

    def test_get_summary(self):
        """Test getting progress summary."""
        tracker = ProgressTracker()

        tracker.start(ProgressPhase.DOWNLOADING, total=10)
        tracker.update(current=5)
        time.sleep(0.01)
        tracker.complete()

        summary = tracker.get_summary()

        assert "total_time" in summary
        assert summary["total_time"] > 0
        assert "phase_history" in summary
        assert "downloading" in summary["phase_history"]
        assert summary["current_phase"] == "downloading"
        assert summary["progress"] == "10/10"
        assert summary["percentage"] == 100.0

    def test_get_summary_no_start_time(self):
        """Test getting summary when tracker hasn't started."""
        tracker = ProgressTracker()
        summary = tracker.get_summary()

        assert summary["total_time"] == 0
        assert summary["current_phase"] is None

    def test_get_summary_with_zero_total(self):
        """Test summary calculation with zero total."""
        tracker = ProgressTracker()
        tracker.start(ProgressPhase.DOWNLOADING, total=0)

        summary = tracker.get_summary()
        assert summary["percentage"] == 0


class TestConsoleProgressReporter:
    """Test ConsoleProgressReporter class."""

    def test_initialization(self):
        """Test ConsoleProgressReporter initialization."""
        reporter = ConsoleProgressReporter(verbose=True)
        assert reporter.verbose is True
        assert reporter._last_phase is None

    def test_initialization_not_verbose(self):
        """Test ConsoleProgressReporter initialization not verbose."""
        reporter = ConsoleProgressReporter(verbose=False)
        assert reporter.verbose is False

    def test_call_prints_phase_change(self, capsys):
        """Test that phase changes are printed."""
        reporter = ConsoleProgressReporter(verbose=True)
        update = ProgressUpdate(
            phase=ProgressPhase.DOWNLOADING,
            current=0,
            total=10,
            message="Starting",
        )

        reporter(update)

        captured = capsys.readouterr()
        assert "DOWNLOADING" in captured.out
        assert "=" in captured.out

    def test_call_doesnt_repeat_phase_header(self, capsys):
        """Test that phase header is not repeated."""
        reporter = ConsoleProgressReporter(verbose=True)
        update1 = ProgressUpdate(phase=ProgressPhase.DOWNLOADING, current=1, total=10)
        update2 = ProgressUpdate(phase=ProgressPhase.DOWNLOADING, current=2, total=10)

        reporter(update1)
        capsys.readouterr()  # Clear

        reporter(update2)
        captured = capsys.readouterr()

        # Phase header should not appear again
        assert "Phase:" not in captured.out

    def test_call_verbose_prints_all_updates(self, capsys):
        """Test verbose mode prints all updates."""
        reporter = ConsoleProgressReporter(verbose=True)
        update = ProgressUpdate(
            phase=ProgressPhase.DOWNLOADING,
            current=5,
            total=10,
            message="Processing",
        )

        reporter(update)

        captured = capsys.readouterr()
        assert "5/10" in captured.out
        assert "Processing" in captured.out

    def test_call_not_verbose_only_prints_complete(self, capsys):
        """Test non-verbose mode only prints complete updates."""
        reporter = ConsoleProgressReporter(verbose=False)

        # Incomplete update
        update1 = ProgressUpdate(phase=ProgressPhase.DOWNLOADING, current=5, total=10)
        reporter(update1)
        captured = capsys.readouterr()
        # Should still print phase change
        assert "DOWNLOADING" in captured.out

        # But not progress details for incomplete
        # Mark phase as already printed
        reporter._last_phase = ProgressPhase.DOWNLOADING
        reporter(update1)
        captured = capsys.readouterr()
        assert "5/10" not in captured.out

        # Complete update should print
        update2 = ProgressUpdate(phase=ProgressPhase.DOWNLOADING, current=10, total=10)
        reporter(update2)
        captured = capsys.readouterr()
        assert "10/10" in captured.out


class TestTqdmProgressReporter:
    """Test TqdmProgressReporter class."""

    def test_initialization_with_tqdm(self):
        """Test TqdmProgressReporter initialization when tqdm is available."""
        pytest.importorskip("tqdm")
        reporter = TqdmProgressReporter()
        assert reporter.tqdm is not None
        assert reporter._bars == {}

    def test_initialization_without_tqdm(self):
        """Test TqdmProgressReporter initialization when tqdm not available."""

        # Mock the import inside __init__ by patching builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == "tqdm":
                raise ImportError("tqdm not available")
            return __import__(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            reporter = TqdmProgressReporter()
            assert reporter.tqdm is None

    def test_call_creates_progress_bar(self):
        """Test that calling reporter creates progress bar."""
        mock_tqdm_class = MagicMock()
        mock_bar = MagicMock()
        mock_tqdm_class.return_value = mock_bar

        with patch.dict("sys.modules", {"tqdm": MagicMock(tqdm=mock_tqdm_class)}):
            reporter = TqdmProgressReporter()
            update = ProgressUpdate(
                phase=ProgressPhase.DOWNLOADING, current=5, total=10
            )

            reporter(update)

            # Verify tqdm was called to create bar
            mock_tqdm_class.assert_called_once()
            assert ProgressPhase.DOWNLOADING in reporter._bars

    def test_call_updates_existing_bar(self):
        """Test that subsequent calls update existing bar."""
        mock_tqdm_class = MagicMock()
        mock_bar = MagicMock()
        mock_tqdm_class.return_value = mock_bar

        with patch.dict("sys.modules", {"tqdm": MagicMock(tqdm=mock_tqdm_class)}):
            reporter = TqdmProgressReporter()
            update1 = ProgressUpdate(
                phase=ProgressPhase.DOWNLOADING, current=5, total=10
            )
            update2 = ProgressUpdate(
                phase=ProgressPhase.DOWNLOADING, current=7, total=10
            )

            reporter(update1)
            reporter(update2)

            # Should only create one bar
            assert mock_tqdm_class.call_count == 1
            # Bar should be updated
            assert mock_bar.n == 7

    def test_call_closes_bar_when_complete(self):
        """Test that progress bar is closed when complete."""
        mock_tqdm_class = MagicMock()
        mock_bar = MagicMock()
        mock_tqdm_class.return_value = mock_bar

        with patch.dict("sys.modules", {"tqdm": MagicMock(tqdm=mock_tqdm_class)}):
            reporter = TqdmProgressReporter()
            update = ProgressUpdate(
                phase=ProgressPhase.DOWNLOADING, current=10, total=10
            )

            reporter(update)

            mock_bar.close.assert_called_once()

    def test_call_closes_bar_on_error(self):
        """Test that progress bar is closed on error phase."""
        mock_tqdm_class = MagicMock()
        mock_bar = MagicMock()
        mock_tqdm_class.return_value = mock_bar

        with patch.dict("sys.modules", {"tqdm": MagicMock(tqdm=mock_tqdm_class)}):
            reporter = TqdmProgressReporter()
            update = ProgressUpdate(phase=ProgressPhase.ERROR, current=5, total=10)

            reporter(update)

            mock_bar.close.assert_called_once()

    def test_call_fallback_without_tqdm(self, capsys):
        """Test fallback to console output when tqdm not available."""

        # Mock the import inside __init__ by patching builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == "tqdm":
                raise ImportError("tqdm not available")
            return __import__(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            reporter = TqdmProgressReporter()
            update = ProgressUpdate(
                phase=ProgressPhase.DOWNLOADING,
                current=5,
                total=10,
                message="Downloading",
            )

            reporter(update)

            captured = capsys.readouterr()
            assert "downloading" in captured.out
            assert "5/10" in captured.out

    def test_close_all(self):
        """Test closing all progress bars."""
        mock_tqdm_class = MagicMock()
        mock_bar1 = MagicMock(disable=False)
        mock_bar2 = MagicMock(disable=False)
        mock_tqdm_class.side_effect = [mock_bar1, mock_bar2]

        with patch.dict("sys.modules", {"tqdm": MagicMock(tqdm=mock_tqdm_class)}):
            reporter = TqdmProgressReporter()

            update1 = ProgressUpdate(
                phase=ProgressPhase.DOWNLOADING, current=5, total=10
            )
            update2 = ProgressUpdate(
                phase=ProgressPhase.CREATING_SYMLINKS, current=3, total=5
            )

            reporter(update1)
            reporter(update2)

            reporter.close_all()

            mock_bar1.close.assert_called()
            mock_bar2.close.assert_called()

    def test_close_all_skips_disabled_bars(self):
        """Test close_all skips disabled bars."""
        mock_tqdm_class = MagicMock()
        mock_bar = MagicMock(disable=True)
        mock_tqdm_class.return_value = mock_bar

        with patch.dict("sys.modules", {"tqdm": MagicMock(tqdm=mock_tqdm_class)}):
            reporter = TqdmProgressReporter()

            update = ProgressUpdate(
                phase=ProgressPhase.DOWNLOADING, current=5, total=10
            )
            reporter(update)

            reporter.close_all()

            # Should not call close on disabled bar
            mock_bar.close.assert_not_called()

    def test_close_all_without_tqdm(self):
        """Test close_all when tqdm not available."""

        # Mock the import inside __init__ by patching builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == "tqdm":
                raise ImportError("tqdm not available")
            return __import__(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            reporter = TqdmProgressReporter()
            # Should not raise exception
            reporter.close_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
