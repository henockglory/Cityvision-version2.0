"""Tâche 3 — abort_stats terminal reconciliation."""
from __future__ import annotations

from citevision_ai.evidence import abort_stats


def test_abort_stats_50_attempts_reconcile():
    abort_stats.reset()
    et = "red_light_violation"
    # 50 deliberate attempts: 20 complete, 15 scene_green, 10 align, 5 no_correlation
    for i in range(50):
        abort_stats.record_attempt(camera_id="camtest01", event_type=et)
        if i < 20:
            abort_stats.record_complete(camera_id="camtest01", event_type=et, event_id=f"e{i}")
        elif i < 35:
            abort_stats.record_abort(abort_stats.ABORT_SCENE_GREEN, camera_id="camtest01", event_type=et)
        elif i < 45:
            abort_stats.record_abort(abort_stats.ABORT_ALIGN_TOO_WIDE, camera_id="camtest01", event_type=et)
        else:
            abort_stats.record_abort(abort_stats.ABORT_NO_CORRELATION, camera_id="camtest01", event_type=et)
        # Probe rejects must NOT break terminal balance
        if i % 3 == 0:
            abort_stats.record_probe_reject(
                abort_stats.ABORT_IOU_REJECT, camera_id="camtest01", event_type=et
            )

    snap = abort_stats.snapshot()
    assert snap["attempts"][et] == 50
    assert snap["completes"][et] == 20
    assert snap["terminal_aborts"][et] == 30
    assert snap["by_event_type"][et][abort_stats.ABORT_SCENE_GREEN] == 15
    assert snap["by_event_type"][et][abort_stats.ABORT_ALIGN_TOO_WIDE] == 10
    assert snap["by_event_type"][et][abort_stats.ABORT_NO_CORRELATION] == 5
    assert snap["probe_rejects"][et][abort_stats.ABORT_IOU_REJECT] >= 1
    assert snap["reconciliation"]["ok"] is True
    assert snap["reconciliation"]["by_event_type"][et]["balanced"] is True
    # Formal sum of abort causes == terminal_aborts
    assert sum(snap["by_event_type"][et].values()) == snap["terminal_aborts"][et]
    # attempts == completes + terminal_aborts
    assert snap["attempts"][et] == snap["completes"][et] + snap["terminal_aborts"][et]
