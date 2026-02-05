"""Database-backed checkpointing for long-running jobs."""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


class CheckpointManager:
    """Track progress for resumable enrichment runs."""

    def __init__(self, engine: Engine):
        self._engine = engine

    def get_checkpoint(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest checkpoint for a run.

        Args:
            run_id: Unique identifier for the enrichment run.

        Returns:
            Checkpoint data dict or None if no checkpoint exists.
        """
        with self._engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT last_processed_index, processed_tickers, errors, updated_at
                    FROM enrichment_checkpoints
                    WHERE run_id = :run_id
                """),
                {"run_id": run_id},
            ).fetchone()

        if row:
            return {
                "last_index": row[0],
                "processed_tickers": row[1] or [],
                "errors": row[2] or {},
                "updated_at": row[3],
            }
        return None

    def save_checkpoint(
        self,
        run_id: str,
        last_index: int,
        processed_tickers: List[str],
        errors: Dict[str, str],
    ) -> None:
        """Save or update checkpoint using upsert.

        Args:
            run_id: Unique identifier for the enrichment run.
            last_index: Index of last successfully processed row.
            processed_tickers: List of tickers processed so far.
            errors: Dict mapping tickers to error messages.
        """
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO enrichment_checkpoints
                        (run_id, last_processed_index, processed_tickers, errors, updated_at)
                    VALUES
                        (:run_id, :idx, :tickers::jsonb, :errors::jsonb, :now)
                    ON CONFLICT (run_id) DO UPDATE SET
                        last_processed_index = EXCLUDED.last_processed_index,
                        processed_tickers = EXCLUDED.processed_tickers,
                        errors = EXCLUDED.errors,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "run_id": run_id,
                    "idx": last_index,
                    "tickers": json.dumps(processed_tickers),
                    "errors": json.dumps(errors),
                    "now": datetime.now(timezone.utc),
                },
            )

    def clear_checkpoint(self, run_id: str) -> None:
        """Clear checkpoint after successful completion.

        Args:
            run_id: Unique identifier for the enrichment run to clear.
        """
        with self._engine.begin() as conn:
            conn.execute(
                text("DELETE FROM enrichment_checkpoints WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
