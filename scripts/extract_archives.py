#!/usr/bin/env python
"""
Extract all .zip files in DATA_DIR into DATA_DIR/extracted, skipping ones already extracted.

Keeps a simple log file (extracted.txt) in DATA_DIR listing processed zip filenames.
"""

import zipfile
from pathlib import Path

from src.config import DATA_DIR


def load_extracted_log(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    return {line.strip() for line in log_path.read_text().splitlines() if line.strip()}


def save_extracted_log(log_path: Path, entries: set[str]) -> None:
    log_path.write_text("\n".join(sorted(entries)) + "\n")


def main() -> None:
    data_dir = Path(DATA_DIR)
    extracted_dir = data_dir / "extracted"
    log_path = data_dir / "extracted.txt"

    extracted_dir.mkdir(parents=True, exist_ok=True)
    seen = load_extracted_log(log_path)

    zip_files = sorted(data_dir.glob("*.zip"))
    if not zip_files:
        print(f"No .zip files found in {data_dir}")
        return

    new_extractions = 0
    for zip_path in zip_files:
        name = zip_path.name
        if name in seen:
            print(f"Skipping already extracted: {name}")
            continue

        target = extracted_dir / zip_path.stem
        target.mkdir(parents=True, exist_ok=True)
        print(f"Extracting {name} to {target} ...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target)

        seen.add(name)
        new_extractions += 1

    save_extracted_log(log_path, seen)
    print(f"Done. New extractions: {new_extractions}, total logged: {len(seen)}")


if __name__ == "__main__":
    main()
