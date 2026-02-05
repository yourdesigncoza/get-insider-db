"""
Streaming JSON processing for large cluster exports.

Uses ijson for memory-efficient parsing of JSON files containing
cluster data in the format: {"metadata": {...}, "rows": [...]}

Memory usage is O(1) regardless of file size - clusters are
yielded one at a time during iteration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    BinaryIO,
    Callable,
    Iterator,
    Union,
)

import ijson


class ClusterStreamReader:
    """
    Memory-efficient reader for cluster JSON files.

    Streams clusters one at a time from files with structure:
    {"metadata": {...}, "rows": [...]}

    Uses ijson to parse without loading the entire file into memory.

    Example:
        reader = ClusterStreamReader("large_export.json")
        for cluster in reader:
            process(cluster)
    """

    def __init__(self, file_path: Union[Path, str, BinaryIO]) -> None:
        """
        Initialize the reader.

        Args:
            file_path: Path to JSON file, string path, or file-like object
                      opened in binary mode ('rb').
        """
        self._file_path = file_path
        self._owns_file = not hasattr(file_path, "read")

    def __iter__(self) -> Iterator[dict]:
        """
        Iterate over clusters in the 'rows' array.

        Yields:
            Each cluster dict from the 'rows' array, one at a time.
        """
        if self._owns_file:
            # File path provided - open it
            path = Path(self._file_path) if isinstance(self._file_path, str) else self._file_path
            with open(path, "rb") as f:
                yield from self._stream_from_file(f)
        else:
            # File-like object provided
            yield from self._stream_from_file(self._file_path)

    def _stream_from_file(self, f: BinaryIO) -> Iterator[dict]:
        """
        Stream clusters from an open file handle.

        Uses ijson.items to efficiently parse only the 'rows' array
        without loading the entire JSON structure.
        """
        for cluster in ijson.items(f, "rows.item"):
            yield cluster


def stream_clusters(file_path: Union[Path, str]) -> Iterator[dict]:
    """
    Stream clusters from a JSON file one at a time.

    Convenience function wrapping ClusterStreamReader.

    Args:
        file_path: Path to JSON file with structure
                  {"metadata": {...}, "rows": [...]}

    Yields:
        Each cluster dict from the 'rows' array.

    Example:
        for cluster in stream_clusters("exports/large_export.json"):
            enriched = enrich(cluster)
            yield enriched
    """
    reader = ClusterStreamReader(file_path)
    yield from reader


def read_metadata(file_path: Union[Path, str]) -> dict:
    """
    Extract just the metadata object from a cluster JSON file.

    Reads only the metadata without loading the rows array,
    memory-efficient for large files.

    Args:
        file_path: Path to JSON file with structure
                  {"metadata": {...}, "rows": [...]}

    Returns:
        The metadata dict, or empty dict if no metadata found.

    Example:
        meta = read_metadata("exports/large_export.json")
        print(f"Generated at: {meta.get('generated_at')}")
    """
    path = Path(file_path) if isinstance(file_path, str) else file_path

    with open(path, "rb") as f:
        # Use ijson to extract just the metadata object
        for metadata in ijson.items(f, "metadata"):
            return metadata

    # No metadata found
    return {}


def write_clusters_streaming(
    clusters: Iterator[dict],
    output_path: Union[Path, str],
    metadata: dict[str, Any] | None = None,
) -> int:
    """
    Write clusters to JSON file incrementally.

    Memory-efficient: writes each cluster immediately without
    accumulating all results in memory.

    Produces output in format: {"rows": [...], "metadata": {...}}

    Args:
        clusters: Iterator yielding cluster dicts
        output_path: Path to write JSON file
        metadata: Optional metadata dict to include

    Returns:
        Number of clusters written.

    Example:
        def enrich_clusters():
            for cluster in stream_clusters("input.json"):
                yield enrich(cluster)

        count = write_clusters_streaming(
            enrich_clusters(),
            "output.json",
            metadata={"enriched_at": datetime.now().isoformat()}
        )
    """
    path = Path(output_path) if isinstance(output_path, str) else output_path
    path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with open(path, "w", encoding="utf-8") as f:
        # Start the JSON structure
        f.write('{"rows": [')

        first = True
        for cluster in clusters:
            if not first:
                f.write(",")
            first = False

            # Write cluster with proper formatting
            f.write("\n")
            f.write(json.dumps(cluster, default=str, indent=None))
            count += 1

        # Close the rows array
        f.write("\n]")

        # Add metadata if provided
        if metadata is not None:
            f.write(', "metadata": ')
            f.write(json.dumps(metadata, default=str, indent=None))

        # Close the JSON object
        f.write("}\n")

    return count


def batch_clusters(
    clusters: Iterator[dict],
    batch_size: int = 50,
) -> Iterator[list[dict]]:
    """
    Group clusters into batches for efficient processing.

    Useful for async processing where you want to process
    multiple clusters concurrently within each batch.

    Args:
        clusters: Iterator yielding cluster dicts
        batch_size: Maximum clusters per batch (default: 50)

    Yields:
        Lists of up to batch_size clusters. Final batch may be smaller.

    Example:
        for batch in batch_clusters(stream_clusters(path), batch_size=50):
            results = await asyncio.gather(*[process(c) for c in batch])
    """
    batch: list[dict] = []

    for cluster in clusters:
        batch.append(cluster)
        if len(batch) >= batch_size:
            yield batch
            batch = []

    # Yield any remaining clusters
    if batch:
        yield batch


async def process_batches(
    clusters: Iterator[dict],
    processor: Callable[[list[dict]], Any],
    batch_size: int = 50,
) -> AsyncIterator[dict]:
    """
    Process clusters in batches with an async processor.

    Batches clusters using batch_clusters(), processes each batch
    with the provided async processor, then yields individual results.

    Enables: concurrent processing within batches, sequential between batches.

    Args:
        clusters: Iterator yielding cluster dicts
        processor: Async function that takes list[dict] and returns list[dict]
        batch_size: Maximum clusters per batch (default: 50)

    Yields:
        Individual processed cluster dicts.

    Example:
        async def enrich_batch(batch: list[dict]) -> list[dict]:
            return await asyncio.gather(*[enrich(c) for c in batch])

        async for enriched in process_batches(
            stream_clusters(path),
            enrich_batch,
            batch_size=50
        ):
            yield enriched
    """
    for batch in batch_clusters(clusters, batch_size):
        # Process the batch (await if it's a coroutine)
        results = await processor(batch)

        # Yield individual results
        for result in results:
            yield result
