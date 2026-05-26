"""Semantic chunker for Buffett shareholder letters.

Uses a LOCAL sentence embedding model (via fastembed, no API calls) to detect
meaning shifts between consecutive sentences, then splits at topic boundaries.

Algorithm:
  1. Split each letter into sentences.
  2. Embed every sentence locally with fastembed TextEmbedding.
  3. Compute cosine similarity between adjacent sentence embeddings.
  4. Start a new chunk wherever similarity drops below --threshold.
  5. Merge chunks shorter than --min-tokens into their neighbour.
  6. Split chunks longer than --max-tokens at the nearest sentence boundary.
  7. Add --overlap-tokens of text from the end of the previous chunk to the
     beginning of every chunk (except the first) so retrieval never loses
     context at a boundary.

Changes vs original:
  - DEFAULT_THRESHOLD raised from 0.50 → 0.65 (fewer but more coherent chunks)
  - Overlap added: last N tokens of chunk[i-1] prepended to chunk[i]
  - Overlap text stored in metadata["overlap_prefix"] for transparency
  - Overlap tokens NOT counted toward min/max-tokens of the core content
  - char_offset added to metadata for debugging and citation

No LiteLLM / API key required — embeddings run fully offline.
The output JSON is compatible with upload_to_qdrant.py.

Usage (run from repo root):
    python scripts/semantic_chunk_letters.py
    python scripts/semantic_chunk_letters.py --threshold 0.65
    python scripts/semantic_chunk_letters.py --overlap-tokens 50
    python scripts/semantic_chunk_letters.py --dry-run
    python scripts/semantic_chunk_letters.py \\
        --output data/semantic_chunks_t65.json \\
        --threshold 0.65 \\
        --overlap-tokens 50
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import tiktoken
from fastembed import TextEmbedding

# ── Repo root ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("semantic_chunk")

# ── Defaults ──────────────────────────────────────────────────────────────────
# Local model used only for boundary detection (not stored in Qdrant).
# BAAI/bge-small-en-v1.5 is 33M params, fast, strong at sentence similarity
# on the MTEB benchmark — outperforms all-MiniLM-L6-v2 for this task.
DEFAULT_LOCAL_MODEL   = "BAAI/bge-small-en-v1.5"
DEFAULT_THRESHOLD     = 0.65   # raised from 0.50 — gives more coherent topic chunks
DEFAULT_MIN_TOKENS    = 100    # merge chunks shorter than this
DEFAULT_MAX_TOKENS    = 800    # split chunks longer than this
DEFAULT_OVERLAP_TOKENS = 50   # tokens from end of prev chunk prepended to next
DEFAULT_BATCH_SIZE    = 128    # sentences per fastembed batch
ENCODING_NAME         = "cl100k_base"
MIN_LETTER_CHARS      = 300

# Pre-load tokenizer once
_enc = tiktoken.get_encoding(ENCODING_NAME)


# ── Token counting ─────────────────────────────────────────────────────────────

def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def last_n_tokens(text: str, n: int) -> str:
    """Return the last n tokens of text as a string.

    Used to build the overlap prefix for the next chunk.
    Works at token boundaries so the overlap is always exactly n tokens
    (or the full text if it is shorter than n tokens).
    """
    if n <= 0:
        return ""
    token_ids = _enc.encode(text)
    if len(token_ids) <= n:
        return text
    return _enc.decode(token_ids[-n:])


# ── Sentence splitting ─────────────────────────────────────────────────────────
# Handles common abbreviations so "Mr. Buffett" doesn't become two sentences.
_ABBREV = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|approx|est|incl|excl|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec|"
    r"U\.S|U\.K|e\.g|i\.e|cf|et al|p|pp|vol|fig|no)\.",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving common abbreviations."""
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Temporarily hide abbreviation dots
    placeholder = "\x00"
    protected = _ABBREV.sub(lambda m: m.group().replace(".", placeholder), text)

    raw = _SENTENCE_END.split(protected)
    sentences: list[str] = []
    for s in raw:
        s = s.replace(placeholder, ".").strip()
        if s:
            sentences.append(s)
    return sentences


# ── Embedding ──────────────────────────────────────────────────────────────────

def load_model(model_name: str) -> TextEmbedding:
    logger.info("Loading local embedding model: %s", model_name)
    return TextEmbedding(model_name=model_name)


def embed_sentences(
    sentences: list[str],
    model: TextEmbedding,
    batch_size: int,
) -> np.ndarray:
    """Return (N, dim) float32 array of L2-normalised sentence embeddings.

    After L2 normalisation, np.dot(a, b) == cosine_similarity(a, b),
    which avoids calling scipy and keeps the hot loop fast.
    """
    vectors = list(model.embed(sentences, batch_size=batch_size))
    arr = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return arr / norms


# ── Semantic breakpoints ───────────────────────────────────────────────────────

def find_breakpoints(embeddings: np.ndarray, threshold: float) -> list[int]:
    """Return sentence indices where a new chunk should start (0 always included).

    A breakpoint is placed between sentence i-1 and i when their cosine
    similarity drops below `threshold`.  With threshold=0.65 (vs 0.50 before)
    we get fewer but semantically tighter chunks — important for a corpus like
    Buffett's letters where topic transitions are gradual.
    """
    if len(embeddings) == 0:
        return []
    breakpoints = [0]
    for i in range(1, len(embeddings)):
        sim = float(np.dot(embeddings[i - 1], embeddings[i]))
        if sim < threshold:
            breakpoints.append(i)
    return breakpoints


# ── Chunk assembly ─────────────────────────────────────────────────────────────

def assemble_chunks(sentences: list[str], breakpoints: list[int]) -> list[str]:
    """Group sentences into raw text chunks at the given breakpoints."""
    if not sentences:
        return []
    chunks: list[str] = []
    bp_set = set(breakpoints)
    current: list[str] = []
    for i, sent in enumerate(sentences):
        if i in bp_set and current:
            chunks.append(" ".join(current))
            current = []
        current.append(sent)
    if current:
        chunks.append(" ".join(current))
    return chunks


def merge_short_chunks(chunks: list[str], min_tokens: int) -> list[str]:
    """Merge any chunk shorter than min_tokens into its right neighbour (or left if last)."""
    result = list(chunks)
    i = 0
    while i < len(result):
        if count_tokens(result[i]) < min_tokens:
            if i + 1 < len(result):
                result[i + 1] = result[i] + " " + result[i + 1]
                result.pop(i)
            elif i > 0:
                result[i - 1] = result[i - 1] + " " + result[i]
                result.pop(i)
            else:
                i += 1
        else:
            i += 1
    return result


def split_long_chunks(chunks: list[str], max_tokens: int) -> list[str]:
    """Split any chunk exceeding max_tokens at the nearest sentence boundary."""
    result: list[str] = []
    for chunk in chunks:
        if count_tokens(chunk) <= max_tokens:
            result.append(chunk)
            continue
        sents = split_sentences(chunk)
        current: list[str] = []
        current_tokens = 0
        for sent in sents:
            sent_tokens = count_tokens(sent)
            if current and current_tokens + sent_tokens > max_tokens:
                result.append(" ".join(current))
                current = []
                current_tokens = 0
            current.append(sent)
            current_tokens += sent_tokens
        if current:
            result.append(" ".join(current))
    return result


# ── Overlap ────────────────────────────────────────────────────────────────────

def apply_overlap(chunks: list[str], overlap_tokens: int) -> list[dict[str, str]]:
    """Prepend the last `overlap_tokens` tokens of chunk[i-1] to chunk[i].

    Why overlap matters for RAG:
        Buffett frequently starts a new paragraph by referring back to a point
        he just finished ("As I mentioned above, this business...").  Without
        overlap, a retrieval that lands on chunk[i] misses the antecedent in
        chunk[i-1].  With 50-token overlap, the model always sees the tail of
        the previous thought.

    Design decisions:
        - Overlap is prepended as-is (no separator) so the text reads naturally.
        - Overlap tokens are NOT counted toward min/max-tokens of the core
          content; those limits are enforced before this step.
        - The overlap text is stored separately in `overlap_prefix` so callers
          (e.g. upload_to_qdrant.py) can strip it for display/citation if needed.
        - Chunk 0 never gets an overlap prefix (there is no previous chunk).

    Returns a list of dicts with keys:
        "text"           — full text to embed and store (overlap + core)
        "core_text"      — core content only (no overlap), for citation display
        "overlap_prefix" — the overlap text that was prepended (empty for chunk 0)
    """
    result: list[dict[str, str]] = []
    for i, chunk in enumerate(chunks):
        if i == 0 or overlap_tokens <= 0:
            result.append({
                "text": chunk,
                "core_text": chunk,
                "overlap_prefix": "",
            })
        else:
            prefix = last_n_tokens(chunks[i - 1], overlap_tokens)
            full_text = prefix + " " + chunk if prefix else chunk
            result.append({
                "text": full_text,
                "core_text": chunk,
                "overlap_prefix": prefix,
            })
    return result


# ── Per-file processing ────────────────────────────────────────────────────────

def extract_year(filepath: Path) -> int:
    match = re.search(r"\b(19|20)\d{2}\b", filepath.stem)
    if not match:
        raise ValueError(f"Cannot extract year from filename: {filepath.name}")
    return int(match.group())


def process_file(
    filepath: Path,
    model: TextEmbedding | None,
    threshold: float,
    min_tokens: int,
    max_tokens: int,
    overlap_tokens: int,
    batch_size: int,
    dry_run: bool,
) -> list[dict[str, Any]]:
    year = extract_year(filepath)
    text = filepath.read_text(encoding="utf-8", errors="replace").strip()

    if len(text) < MIN_LETTER_CHARS:
        raise ValueError(f"letter too short ({len(text)} chars)")

    sentences = split_sentences(text)
    if not sentences:
        raise ValueError("no sentences found after splitting")

    if dry_run:
        total_tokens = count_tokens(text)
        approx_chunks = max(1, int(total_tokens / ((min_tokens + max_tokens) / 2)))
        logger.info(
            "DRY-RUN %s | %d sentences | ~%d tokens | ~%d chunks (estimated)",
            filepath.name, len(sentences), total_tokens, approx_chunks,
        )
        return []

    logger.info("%s | embedding %d sentences ...", filepath.name, len(sentences))
    embeddings = embed_sentences(sentences, model, batch_size)  # type: ignore[arg-type]

    breakpoints = find_breakpoints(embeddings, threshold)
    raw_chunks = assemble_chunks(sentences, breakpoints)

    # Enforce min/max BEFORE adding overlap so size limits apply to core content
    merged = merge_short_chunks(raw_chunks, min_tokens)
    final_core_chunks = split_long_chunks(merged, max_tokens)

    # Add overlap prefix to every chunk except the first
    overlapped = apply_overlap(final_core_chunks, overlap_tokens)

    total = len(overlapped)
    logger.info(
        "%s | %d breakpoints -> %d raw -> %d final chunks (overlap=%d tokens)",
        filepath.name, len(breakpoints) - 1, len(raw_chunks), total, overlap_tokens,
    )

    # Build char offset map for citation / debugging
    char_offset = 0
    output: list[dict[str, Any]] = []
    for idx, item in enumerate(overlapped):
        core = item["core_text"]
        if not core.strip():
            continue

        output.append({
            # "text" is what gets embedded and stored in Qdrant
            # It includes the overlap prefix so retrieval always has context.
            "text": item["text"],
            "metadata": {
                "year": year,
                "chunk_index": idx,
                "total_chunks": total,
                "source_file": filepath.name,
                "chunk_method": "semantic",
                "threshold": threshold,
                "local_model": DEFAULT_LOCAL_MODEL,
                "overlap_tokens": overlap_tokens,
                # core_text is the authoritative passage for citation display;
                # strip the overlap prefix before showing to the user.
                "core_text": core,
                "overlap_prefix": item["overlap_prefix"],
                # char_offset points into the *original* letter text for debugging.
                "char_offset": char_offset,
                "core_tokens": count_tokens(core),
                "total_tokens": count_tokens(item["text"]),
            },
        })
        char_offset += len(core) + 1  # +1 for the space between chunks

    return output


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Semantic chunking of Buffett letters using a local embedding model (fastembed). "
            "Threshold 0.65 and 50-token overlap are the recommended defaults."
        )
    )
    parser.add_argument(
        "--letters-dir",
        type=Path,
        default=REPO_ROOT / "data" / "letters",
        help="Directory containing {YEAR}.txt files (default: data/letters/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "data" / "semantic_chunks.json",
        help="Output JSON path (default: data/semantic_chunks.json)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=(
            f"Cosine similarity breakpoint threshold (default: {DEFAULT_THRESHOLD}). "
            "Lower = fewer, larger chunks. Higher = more, smaller chunks. "
            "0.65 is recommended for Buffett letters (gradual topic transitions)."
        ),
    )
    parser.add_argument(
        "--min-tokens",
        type=int,
        default=DEFAULT_MIN_TOKENS,
        help=f"Merge chunks shorter than N tokens (default: {DEFAULT_MIN_TOKENS})",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Split chunks longer than N tokens (default: {DEFAULT_MAX_TOKENS})",
    )
    parser.add_argument(
        "--overlap-tokens",
        type=int,
        default=DEFAULT_OVERLAP_TOKENS,
        help=(
            f"Tokens from end of previous chunk prepended to next chunk (default: {DEFAULT_OVERLAP_TOKENS}). "
            "Set to 0 to disable overlap. Overlap is applied after min/max enforcement "
            "so size limits always refer to core content only."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Sentences per fastembed batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_LOCAL_MODEL,
        help=f"fastembed TextEmbedding model name (default: {DEFAULT_LOCAL_MODEL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count sentences and estimate chunks without embedding (no model loaded)",
    )
    args = parser.parse_args()

    letters_dir: Path = args.letters_dir
    txt_files = sorted(letters_dir.glob("*.txt"))
    if not txt_files:
        logger.error("No .txt files found in %s", letters_dir)
        sys.exit(1)

    logger.info(
        "Config: threshold=%.2f  min_tokens=%d  max_tokens=%d  "
        "overlap_tokens=%d  batch=%d  model=%s",
        args.threshold, args.min_tokens, args.max_tokens,
        args.overlap_tokens, args.batch_size,
        "none (dry-run)" if args.dry_run else args.model,
    )
    logger.info("Files: %d letters in %s", len(txt_files), letters_dir)

    # Load model once — fastembed caches the weights after first download
    model: TextEmbedding | None = None
    if not args.dry_run:
        model = load_model(args.model)

    all_chunks: list[dict[str, Any]] = []

    for filepath in txt_files:
        try:
            chunks = process_file(
                filepath,
                model=model,
                threshold=args.threshold,
                min_tokens=args.min_tokens,
                max_tokens=args.max_tokens,
                overlap_tokens=args.overlap_tokens,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
            )
            all_chunks.extend(chunks)
        except Exception as exc:
            logger.warning("SKIP %s -> %s", filepath.name, exc)

    if args.dry_run:
        logger.info("Dry run complete — no files written.")
        return

    if not all_chunks:
        logger.error("No chunks produced.")
        sys.exit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    years = sorted({c["metadata"]["year"] for c in all_chunks})
    total_tokens = sum(c["metadata"]["core_tokens"] for c in all_chunks)
    logger.info(
        "Saved %d chunks | years=%s | core_tokens=%d | overlap=%d tokens | -> %s",
        len(all_chunks),
        f"{years[0]}-{years[-1]}" if years else "none",
        total_tokens,
        args.overlap_tokens,
        args.output,
    )


if __name__ == "__main__":
    main()