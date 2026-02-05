#!/usr/bin/env python
"""
Async enrichment CLI script for cluster exports.

Uses async HTTP client with connection pooling and streaming JSON for
memory-efficient processing of large cluster exports (500-2000 clusters).

This is the async equivalent of enrich_clusters_with_price.py.
"""

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.enrichment_service import AsyncEnricher
from src.services.streaming import (
    stream_clusters,
    read_metadata,
    write_clusters_streaming,
    batch_clusters,
)
from src.logging_config import configure_logging, get_logger
from src.checkpointing.checkpoint_manager import CheckpointManager
from src.config import get_engine
from src.audit.signal_history import SignalHistoryRecorder

# Configure logging
configure_logging()
logger = get_logger(__name__)

# Checkpoint frequency: save every N clusters processed in memory mode
CHECKPOINT_FREQUENCY = 25


@dataclass
class EnrichmentStats:
    """Track async enrichment statistics."""

    total_clusters: int = 0
    success: int = 0
    partial: int = 0
    errors: int = 0
    unsupported_ticker: int = 0
    no_price_data: int = 0
    failed_tickers: list[str] = field(default_factory=list)

    def record(self, cluster: dict) -> None:
        """Record stats from an enriched cluster."""
        self.total_clusters += 1
        status = cluster.get("enrichment_status", "ok")

        if status == "ok":
            self.success += 1
        elif status == "partial":
            self.partial += 1
        elif status == "unsupported_ticker":
            self.unsupported_ticker += 1
            self.failed_tickers.append(cluster.get("ticker", "unknown"))
        elif status == "no_price_data":
            self.no_price_data += 1
        else:
            self.errors += 1
            self.failed_tickers.append(cluster.get("ticker", "unknown"))

    def report(self) -> None:
        """Log final enrichment statistics."""
        total = self.total_clusters
        success_rate = (self.success / total * 100) if total > 0 else 0

        logger.info(
            "enrichment_complete",
            total=total,
            success=self.success,
            partial=self.partial,
            errors=self.errors,
            unsupported=self.unsupported_ticker,
            no_price_data=self.no_price_data,
            success_rate=f"{success_rate:.1f}%",
        )

        if self.failed_tickers:
            unique_failed = list(set(self.failed_tickers))[:20]
            logger.warning(
                "failed_tickers",
                count=len(self.failed_tickers),
                samples=unique_failed,
            )


class GracefulShutdown:
    """Handle graceful shutdown on SIGINT/SIGTERM."""

    def __init__(self):
        self.shutdown_requested = False
        self._enricher = None

    def register(self, enricher: AsyncEnricher) -> None:
        """Register enricher for cleanup on shutdown."""
        self._enricher = enricher

        # Register signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_signal)

    def _handle_signal(self, signum: int, frame) -> None:
        """Handle shutdown signal."""
        sig_name = signal.Signals(signum).name
        print(f"\nReceived {sig_name}, shutting down gracefully...")
        self.shutdown_requested = True

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self._enricher:
            await self._enricher.close()


async def enrich_streaming(
    file_path: Path,
    api_key: str,
    max_concurrent: int = 10,
    batch_size: int = 50,
    shutdown: GracefulShutdown | None = None,
    recorder: SignalHistoryRecorder | None = None,
) -> tuple[Path, EnrichmentStats, float]:
    """
    Enrich clusters using streaming I/O for large files.

    Reads clusters incrementally with ijson, processes in batches,
    and writes output incrementally without loading entire file.

    Args:
        file_path: Input JSON file
        api_key: Financial Datasets API key
        max_concurrent: Max concurrent API requests
        batch_size: Clusters per batch
        shutdown: Optional shutdown handler
        recorder: Optional SignalHistoryRecorder for audit trail

    Returns:
        Tuple of (output_path, stats, elapsed_seconds)
    """
    output_path = file_path.with_name(f"{file_path.stem}_enriched{file_path.suffix}")
    stats = EnrichmentStats()
    start_time = time.time()

    # Read metadata separately (streaming)
    metadata = read_metadata(file_path)
    metadata["enriched_at"] = datetime.now().isoformat()
    metadata["enrichment_mode"] = "async_streaming"

    # Count total for progress (requires one pass)
    total_clusters = sum(1 for _ in stream_clusters(file_path))
    logger.info("starting_enrichment", file=str(file_path), total_clusters=total_clusters)

    # Open output file for incremental writing
    output_path.parent.mkdir(parents=True, exist_ok=True)
    processed = 0
    first_cluster = True

    async with AsyncEnricher(api_key=api_key, max_concurrent=max_concurrent) as enricher:
        if shutdown:
            shutdown.register(enricher)

        with open(output_path, "w", encoding="utf-8") as out_file:
            # Start JSON structure
            out_file.write('{"rows": [')

            # Stream through input file in batches
            cluster_iter = stream_clusters(file_path)

            for batch in batch_clusters(cluster_iter, batch_size):
                if shutdown and shutdown.shutdown_requested:
                    logger.warning("shutdown_requested", processed=processed)
                    break

                # Process batch asynchronously
                enriched_batch = await enricher.enrich_batch(batch)

                # Write each enriched cluster
                for cluster in enriched_batch:
                    if not first_cluster:
                        out_file.write(",")
                    first_cluster = False

                    out_file.write("\n")
                    out_file.write(json.dumps(cluster, default=str, indent=None))

                    processed += 1
                    stats.record(cluster)

                    # Record enrichment event to signal history
                    if recorder and cluster.get("cluster_id"):
                        try:
                            recorder.record_event(
                                cluster_id=cluster["cluster_id"],
                                event_type="enriched",
                                changed_by="async_enrichment",
                                new_values={
                                    "enrichment_status": cluster.get("enrichment_status"),
                                    "price_at_entry": cluster.get("price_at_entry"),
                                    "adjusted_cluster_score": cluster.get("adjusted_cluster_score"),
                                },
                                reason=f"Async enriched: {cluster.get('enrichment_status', 'unknown')}",
                            )
                        except Exception as e:
                            logger.warning(
                                "signal_history_record_failed",
                                cluster_id=cluster["cluster_id"],
                                error=str(e),
                            )

                    ticker = cluster.get("ticker", "?")
                    print(f"  [{processed}/{total_clusters}] Enriched {ticker}")

            # Close rows array and add metadata
            out_file.write("\n]")
            if metadata:
                out_file.write(', "metadata": ')
                out_file.write(json.dumps(metadata, default=str, indent=None))
            out_file.write("}\n")

    elapsed = time.time() - start_time
    return output_path, stats, elapsed


async def enrich_small_file(
    file_path: Path,
    api_key: str,
    max_concurrent: int = 10,
    shutdown: GracefulShutdown | None = None,
    resume: bool = True,
    checkpoint_mgr: CheckpointManager | None = None,
    recorder: SignalHistoryRecorder | None = None,
) -> tuple[Path, EnrichmentStats, float]:
    """
    Enrich small files by loading entire JSON into memory.

    More efficient for files with <100 clusters since it avoids
    streaming overhead. Supports crash recovery via checkpointing.

    Args:
        file_path: Input JSON file
        api_key: Financial Datasets API key
        max_concurrent: Max concurrent API requests
        shutdown: Optional shutdown handler
        resume: Whether to resume from checkpoint if exists
        checkpoint_mgr: Optional checkpoint manager for crash recovery
        recorder: Optional SignalHistoryRecorder for audit trail

    Returns:
        Tuple of (output_path, stats, elapsed_seconds)
    """
    output_path = file_path.with_name(f"{file_path.stem}_enriched{file_path.suffix}")
    stats = EnrichmentStats()
    start_time = time.time()

    # Load entire file
    with open(file_path) as f:
        data = json.load(f)

    clusters = data.get("rows", [])
    total = len(clusters)

    # Checkpoint setup
    run_id = f"async_enrich_{file_path.stem}"
    start_index = 0
    processed_tickers: list[str] = []
    errors: dict[str, str] = {}

    # Check for existing checkpoint to resume from
    if resume and checkpoint_mgr:
        checkpoint = checkpoint_mgr.get_checkpoint(run_id)
        if checkpoint:
            start_index = checkpoint["last_index"] + 1
            processed_tickers = list(checkpoint["processed_tickers"])
            errors = dict(checkpoint["errors"])
            logger.info(
                "resuming_from_checkpoint",
                run_id=run_id,
                start_index=start_index,
                total=total,
            )

    logger.info(
        "starting_enrichment",
        file=str(file_path),
        total_clusters=total,
        mode="memory",
        start_index=start_index,
    )

    async with AsyncEnricher(api_key=api_key, max_concurrent=max_concurrent) as enricher:
        if shutdown:
            shutdown.register(enricher)

        # Keep already processed clusters as-is from original data
        enriched_rows = clusters[:start_index]
        # Account for already processed in stats
        stats.total_clusters = start_index

        for i, cluster in enumerate(clusters[start_index:], start_index):
            if shutdown and shutdown.shutdown_requested:
                logger.warning("shutdown_requested", processed=i)
                break

            ticker = cluster.get("ticker", f"row_{i}")

            try:
                enriched = await enricher.enrich_cluster(cluster)
                enriched_rows.append(enriched)
                stats.record(enriched)
                processed_tickers.append(ticker)

                # Record enrichment event to signal history
                if recorder and enriched.get("cluster_id"):
                    try:
                        recorder.record_event(
                            cluster_id=enriched["cluster_id"],
                            event_type="enriched",
                            changed_by="async_enrichment",
                            new_values={
                                "enrichment_status": enriched.get("enrichment_status"),
                                "price_at_entry": enriched.get("price_at_entry"),
                                "adjusted_cluster_score": enriched.get("adjusted_cluster_score"),
                            },
                            reason=f"Async enriched: {enriched.get('enrichment_status', 'unknown')}",
                        )
                    except Exception as rec_err:
                        logger.warning(
                            "signal_history_record_failed",
                            cluster_id=enriched["cluster_id"],
                            error=str(rec_err),
                        )
            except Exception as e:
                logger.error(
                    "enrichment_error",
                    ticker=ticker,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                errors[ticker] = str(e)
                enriched_rows.append(cluster)  # Keep original on error
                stats.errors += 1
                stats.total_clusters += 1

            print(f"  [{i + 1}/{total}] Enriched {ticker}")

            # Save checkpoint periodically
            if checkpoint_mgr and (i + 1) % CHECKPOINT_FREQUENCY == 0:
                checkpoint_mgr.save_checkpoint(
                    run_id=run_id,
                    last_index=i,
                    processed_tickers=processed_tickers,
                    errors=errors,
                )
                logger.info("checkpoint_saved", index=i + 1, total=total)

    data["rows"] = enriched_rows
    if "metadata" in data:
        data["metadata"]["enriched_at"] = datetime.now().isoformat()
        data["metadata"]["enrichment_mode"] = "async_memory"

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    # Clear checkpoint on successful completion
    if checkpoint_mgr:
        checkpoint_mgr.clear_checkpoint(run_id)
        logger.info("checkpoint_cleared", run_id=run_id)

    elapsed = time.time() - start_time
    return output_path, stats, elapsed


async def process_file(
    file_path: Path,
    api_key: str,
    max_concurrent: int = 10,
    batch_size: int = 50,
    use_streaming: bool = True,
    resume: bool = True,
) -> None:
    """
    Process cluster export file with async enrichment.

    Args:
        file_path: Input JSON file
        api_key: Financial Datasets API key
        max_concurrent: Max concurrent API requests
        batch_size: Clusters per batch
        use_streaming: Use ijson streaming for large files
        resume: Whether to resume from checkpoint (memory mode only)
    """
    if not file_path.exists():
        logger.error("file_not_found", file=str(file_path))
        sys.exit(1)

    shutdown = GracefulShutdown()

    # Initialize checkpoint manager for memory mode and signal history recorder
    engine = get_engine()
    checkpoint_mgr = CheckpointManager(engine)
    recorder = SignalHistoryRecorder(engine)

    # Decide streaming vs memory based on file size
    # Streaming is better for large files (>100 clusters typically)
    # Note: Checkpointing only supported in memory mode (streaming has no resume capability)
    if use_streaming:
        # Quick check: count clusters to decide
        cluster_count = sum(1 for _ in stream_clusters(file_path))

        if cluster_count < 50:
            logger.info("using_memory_mode", reason="small_file", clusters=cluster_count)
            output_path, stats, elapsed = await enrich_small_file(
                file_path,
                api_key,
                max_concurrent,
                shutdown,
                resume=resume,
                checkpoint_mgr=checkpoint_mgr,
                recorder=recorder,
            )
        else:
            # Streaming mode: no checkpointing support
            logger.info("using_streaming_mode", clusters=cluster_count, checkpointing="disabled")
            output_path, stats, elapsed = await enrich_streaming(
                file_path, api_key, max_concurrent, batch_size, shutdown, recorder
            )
    else:
        output_path, stats, elapsed = await enrich_small_file(
            file_path,
            api_key,
            max_concurrent,
            shutdown,
            resume=resume,
            checkpoint_mgr=checkpoint_mgr,
            recorder=recorder,
        )

    # Report results
    stats.report()
    logger.info(
        "enrichment_done",
        output=str(output_path),
        elapsed_seconds=round(elapsed, 2),
        clusters_per_second=round(stats.total_clusters / elapsed, 2) if elapsed > 0 else 0,
    )
    print(f"\nDone! Enriched data written to: {output_path}")
    print(f"Time: {elapsed:.2f}s ({stats.total_clusters / elapsed:.1f} clusters/sec)")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Async enrichment for cluster exports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (auto-detects streaming mode)
  python scripts/enrich_clusters_async.py exports/cluster_runs/export.json

  # With custom concurrency
  python scripts/enrich_clusters_async.py export.json --max-concurrent 20

  # Force memory mode for small files
  python scripts/enrich_clusters_async.py export.json --no-streaming
        """,
    )
    parser.add_argument(
        "file_path",
        type=str,
        help="Path to JSON file to enrich",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=10,
        help="Maximum concurrent API requests (default: 10)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Clusters per batch for streaming mode (default: 50)",
    )
    parser.add_argument(
        "--no-streaming",
        action="store_true",
        help="Load entire file into memory instead of streaming",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Start fresh run, ignoring any existing checkpoint",
    )
    args = parser.parse_args()

    # Get API key from environment
    api_key = os.getenv("FINANCIAL_DATASETS_API_KEY")
    if not api_key:
        print("Error: FINANCIAL_DATASETS_API_KEY environment variable not set")
        print("Please add it to your .env file or export it")
        sys.exit(1)

    file_path = Path(args.file_path)

    asyncio.run(
        process_file(
            file_path=file_path,
            api_key=api_key,
            max_concurrent=args.max_concurrent,
            batch_size=args.batch_size,
            use_streaming=not args.no_streaming,
            resume=not args.no_resume,
        )
    )


if __name__ == "__main__":
    main()
