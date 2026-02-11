"""Tests for window span validation in cluster merge logic."""
from datetime import date
import pytest


def merge_intervals_with_span_check(
    intervals: list[tuple[date, date]],
    window_interval: int,
) -> list[tuple[date, date]]:
    """
    Replicate the merge logic from find_cluster_buys() for testability.

    Merges overlapping intervals only if the merged span does not exceed
    window_interval days.
    """
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged: list[tuple[date, date]] = []
    for start, end in sorted_intervals:
        if not merged:
            merged.append((start, end))
            continue
        last_start, last_end = merged[-1]
        if start <= last_end:  # overlap detected
            proposed_end = max(last_end, end)
            if (proposed_end - last_start).days <= window_interval:
                merged[-1] = (last_start, proposed_end)
            else:
                merged.append((start, end))
        else:
            merged.append((start, end))
    return merged


class TestMergeSpanValidation:
    """Verify merged windows never exceed window_interval days."""

    def test_non_overlapping_windows_kept_separate(self):
        """Two windows with no overlap remain separate."""
        intervals = [
            (date(2024, 1, 1), date(2024, 1, 10)),
            (date(2024, 1, 15), date(2024, 1, 24)),
        ]
        result = merge_intervals_with_span_check(intervals, window_interval=9)
        assert len(result) == 2
        assert result[0] == (date(2024, 1, 1), date(2024, 1, 10))
        assert result[1] == (date(2024, 1, 15), date(2024, 1, 24))

    def test_overlapping_windows_merged_when_within_span(self):
        """Two overlapping windows merge when combined span <= window_interval."""
        intervals = [
            (date(2024, 1, 1), date(2024, 1, 5)),
            (date(2024, 1, 3), date(2024, 1, 8)),
        ]
        result = merge_intervals_with_span_check(intervals, window_interval=9)
        assert len(result) == 1
        assert result[0] == (date(2024, 1, 1), date(2024, 1, 8))

    def test_overlapping_windows_kept_separate_when_exceeding_span(self):
        """Two overlapping windows stay separate when merged span > window_interval."""
        intervals = [
            (date(2024, 1, 1), date(2024, 1, 10)),
            (date(2024, 1, 5), date(2024, 1, 18)),
        ]
        result = merge_intervals_with_span_check(intervals, window_interval=9)
        assert len(result) == 2
        assert result[0] == (date(2024, 1, 1), date(2024, 1, 10))
        assert result[1] == (date(2024, 1, 5), date(2024, 1, 18))

    def test_boundary_merge_at_exact_window_interval(self):
        """Merge allowed when merged span == window_interval exactly."""
        intervals = [
            (date(2024, 1, 1), date(2024, 1, 5)),
            (date(2024, 1, 4), date(2024, 1, 10)),
        ]
        result = merge_intervals_with_span_check(intervals, window_interval=9)
        assert len(result) == 1
        assert result[0] == (date(2024, 1, 1), date(2024, 1, 10))

    def test_boundary_reject_at_one_over_window_interval(self):
        """Merge rejected when merged span == window_interval + 1."""
        intervals = [
            (date(2024, 1, 1), date(2024, 1, 5)),
            (date(2024, 1, 4), date(2024, 1, 11)),
        ]
        result = merge_intervals_with_span_check(intervals, window_interval=9)
        assert len(result) == 2

    def test_three_windows_partial_merge(self):
        """Three windows: first two merge, third stays separate."""
        intervals = [
            (date(2024, 1, 1), date(2024, 1, 5)),
            (date(2024, 1, 3), date(2024, 1, 8)),
            (date(2024, 1, 7), date(2024, 1, 20)),
        ]
        result = merge_intervals_with_span_check(intervals, window_interval=9)
        assert len(result) == 2
        assert result[0] == (date(2024, 1, 1), date(2024, 1, 8))
        assert result[1] == (date(2024, 1, 7), date(2024, 1, 20))

    def test_all_spans_valid_after_merge(self):
        """Verify output invariant: every merged interval span <= window_interval."""
        intervals = [
            (date(2024, 1, 1), date(2024, 1, 10)),
            (date(2024, 1, 5), date(2024, 1, 14)),
            (date(2024, 1, 9), date(2024, 1, 18)),
            (date(2024, 1, 13), date(2024, 1, 22)),
        ]
        window_interval = 9
        result = merge_intervals_with_span_check(intervals, window_interval=window_interval)
        for start, end in result:
            span = (end - start).days
            assert span <= window_interval, (
                f"Span {span} days ({start} to {end}) exceeds window_interval={window_interval}"
            )

    def test_single_window_passes_through(self):
        """A single window is returned unchanged."""
        intervals = [(date(2024, 1, 1), date(2024, 1, 10))]
        result = merge_intervals_with_span_check(intervals, window_interval=9)
        assert len(result) == 1
        assert result[0] == (date(2024, 1, 1), date(2024, 1, 10))

    def test_empty_input(self):
        """Empty input returns empty output."""
        result = merge_intervals_with_span_check([], window_interval=9)
        assert result == []

    def test_identical_windows_merge(self):
        """Two identical windows merge to one (span = 0 <= any interval)."""
        intervals = [
            (date(2024, 1, 5), date(2024, 1, 10)),
            (date(2024, 1, 5), date(2024, 1, 10)),
        ]
        result = merge_intervals_with_span_check(intervals, window_interval=9)
        assert len(result) == 1

    def test_adjacent_windows_no_overlap(self):
        """Adjacent windows (start == last_end + 1 day) are not merged."""
        intervals = [
            (date(2024, 1, 1), date(2024, 1, 10)),
            (date(2024, 1, 11), date(2024, 1, 20)),
        ]
        result = merge_intervals_with_span_check(intervals, window_interval=9)
        assert len(result) == 2
