"""Event-sourced audit trail for cluster signals."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json

from sqlalchemy import text
from sqlalchemy.engine import Engine


# Valid event types (enforced at application level)
EVENT_TYPES = frozenset({
    "created",
    "status_changed",
    "score_updated",
    "enriched",
    "invalidated",
})

# Valid actors
ACTORS = frozenset({
    "system",
    "enrichment",
    "async_enrichment",
    "manual",
    "decay_job",
    "backtest",
})


class SignalHistoryRecorder:
    """Record immutable events for signal audit trail."""

    def __init__(self, engine: Engine):
        self._engine = engine

    def record_event(
        self,
        cluster_id: int,
        event_type: str,
        changed_by: str,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> int:
        """
        Record an event in the signal history.

        Args:
            cluster_id: The cluster event ID
            event_type: One of: created, status_changed, score_updated, enriched, invalidated
            changed_by: Actor: system, enrichment, manual, decay_job, backtest
            old_values: Previous state (optional, null for 'created')
            new_values: New state (optional)
            reason: Explanation for the change (optional)

        Returns:
            The ID of the created history record

        Raises:
            ValueError: If event_type or changed_by is invalid
        """
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Invalid event_type: {event_type}. Must be one of {EVENT_TYPES}")
        if changed_by not in ACTORS:
            raise ValueError(f"Invalid changed_by: {changed_by}. Must be one of {ACTORS}")

        with self._engine.begin() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO signal_history
                        (cluster_id, event_type, changed_by, old_values, new_values, reason, created_at)
                    VALUES
                        (:cid, :event, :by, :old::jsonb, :new::jsonb, :reason, :now)
                    RETURNING id
                """),
                {
                    "cid": cluster_id,
                    "event": event_type,
                    "by": changed_by,
                    "old": json.dumps(old_values) if old_values else None,
                    "new": json.dumps(new_values) if new_values else None,
                    "reason": reason,
                    "now": datetime.now(timezone.utc),
                },
            )
            return result.fetchone()[0]

    def get_history(self, cluster_id: int) -> List[Dict[str, Any]]:
        """
        Get full history for a signal, ordered chronologically.

        Args:
            cluster_id: The cluster event ID

        Returns:
            List of history records as dicts
        """
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, event_type, changed_by, old_values, new_values, reason, created_at
                    FROM signal_history
                    WHERE cluster_id = :cid
                    ORDER BY created_at ASC, id ASC
                """),
                {"cid": cluster_id},
            ).fetchall()

        return [
            {
                "id": r[0],
                "event_type": r[1],
                "changed_by": r[2],
                "old_values": r[3],
                "new_values": r[4],
                "reason": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]

    def get_recent_events(
        self,
        event_type: Optional[str] = None,
        changed_by: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get recent events, optionally filtered by type or actor.

        Args:
            event_type: Filter by event type (optional)
            changed_by: Filter by actor (optional)
            limit: Maximum records to return (default 100)

        Returns:
            List of history records as dicts, most recent first
        """
        conditions = []
        params: Dict[str, Any] = {"limit": limit}

        if event_type:
            if event_type not in EVENT_TYPES:
                raise ValueError(f"Invalid event_type filter: {event_type}")
            conditions.append("event_type = :event_type")
            params["event_type"] = event_type

        if changed_by:
            if changed_by not in ACTORS:
                raise ValueError(f"Invalid changed_by filter: {changed_by}")
            conditions.append("changed_by = :changed_by")
            params["changed_by"] = changed_by

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self._engine.connect() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT id, cluster_id, event_type, changed_by, old_values, new_values, reason, created_at
                    FROM signal_history
                    {where_clause}
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                """),
                params,
            ).fetchall()

        return [
            {
                "id": r[0],
                "cluster_id": r[1],
                "event_type": r[2],
                "changed_by": r[3],
                "old_values": r[4],
                "new_values": r[5],
                "reason": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]
