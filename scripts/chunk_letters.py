"""
Buffett Letters Chunker
Reads {YEAR}.txt files and chunks each letter with RecursiveCharacterTextSplitter
(tiktoken), aligned with scripts/ingest_letters.py (1000 tokens / 150 overlap).
"""

import json
import re
from pathlib import Path
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

REPO_ROOT = Path(__file__).resolve().parent.parent
LETTERS_PATH = REPO_ROOT / "data" / "letters"
OUTPUT_JSON = REPO_ROOT / "data" / "letter_chunks.json"

CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
ENCODING_NAME = "cl100k_base"
MIN_LETTER_CHARS = 500

_SPLITTER = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    encoding_name=ENCODING_NAME,
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def extract_year_from_filename(filepath: str | Path) -> int:
    stem = Path(filepath).stem
    match = re.search(r"\b(19|20)\d{2}\b", stem)
    if not match:
        raise ValueError(f"Cannot extract year from filename: {filepath}")
    return int(match.group())


def chunk_letter(filepath: str | Path, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> list[dict[str, Any]]:
    year = extract_year_from_filename(filepath)
    raw_text = Path(filepath).read_text(encoding="utf-8", errors="replace").strip()

    if len(raw_text) < MIN_LETTER_CHARS:
        raise ValueError(f"letter too short ({len(raw_text)} chars); re-download or fix source")

    splitter = (
        _SPLITTER
        if chunk_size == CHUNK_SIZE and chunk_overlap == CHUNK_OVERLAP
        else RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=ENCODING_NAME,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
    )

    parts = [c.strip() for c in splitter.split_text(raw_text) if c.strip()]
    total = len(parts)

    return [
        {
            "text": chunk_text,
            "metadata": {
                "year": year,
                "chunk_index": idx,
                "total_chunks": total,
                "source_file": Path(filepath).name,
            },
        }
        for idx, chunk_text in enumerate(parts)
    ]


def process_directory(input_dir: str | Path, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> list[dict[str, Any]]:
    all_chunks: list[dict[str, Any]] = []
    txt_files = sorted(Path(input_dir).glob("*.txt"))

    if not txt_files:
        raise FileNotFoundError(f"No .txt files found in {input_dir}")

    for filepath in txt_files:
        try:
            chunks = chunk_letter(filepath, chunk_size, chunk_overlap)
            all_chunks.extend(chunks)
            print(f"OK {filepath.name} -> {len(chunks)} chunks")
        except Exception as exc:
            print(f"SKIP {filepath.name} -> {exc}")

    return all_chunks


chunks = process_directory(LETTERS_PATH, CHUNK_SIZE, CHUNK_OVERLAP)

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=2)

print(f"Saved {len(chunks)} chunks to {OUTPUT_JSON}")

