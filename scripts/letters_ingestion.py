"""Download Berkshire shareholder letters and save one cleaned .txt per year.

Usage (from repo root):
    python test.py
    python test.py --start-year 1977 --end-year 2024
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

import fitz
import nltk
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("test_letters")

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "letters"

BASE_URL = "https://www.berkshirehathaway.com/letters/"
FIRST_HTML_YEAR = 1977
FIRST_LTR_PDF_YEAR = 2003

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

LETTER_START = re.compile(
    r"To the Shareholders|To the Stockholders|Dear Shareholder|Fellow Shareholders",
    re.IGNORECASE,
)
LETTER_END = re.compile(
    r"Warren E\.?\s*Buffett|Warren E\.?\s*Buff\s*ett",
    re.IGNORECASE,
)

CONTRACTION_FIXES = (
    (" s ", "'s "),
    (" ve ", "'ve "),
    (" re ", "'re "),
    (" m ", "'m "),
    (" ll ", "'ll "),
    (" t ", "'t "),
    (" d ", "'d "),
)


def probe_url(year: int) -> tuple[str, str] | None:
    """Return (url, kind) where kind is html or pdf."""
    if year < FIRST_HTML_YEAR:
        return None
    html = f"{BASE_URL}{year}.html"
    ltr = f"{BASE_URL}{year}ltr.pdf"
    plain = f"{BASE_URL}{year}.pdf"
    if year < FIRST_LTR_PDF_YEAR:
        candidates = [(html, "html"), (plain, "pdf"), (ltr, "pdf")]
    else:
        candidates = [(ltr, "pdf"), (html, "html"), (plain, "pdf")]
    for url, kind in candidates:
        try:
            resp = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code == 200:
                return url, kind
            if resp.status_code == 405:
                resp = requests.get(url, headers=HEADERS, timeout=15, stream=True)
                if resp.status_code == 200:
                    return url, kind
        except requests.RequestException as exc:
            logger.debug("%s probe failed: %s", url, exc)
    return None


def fetch_html_text(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    body = soup.body or soup
    return body.get_text(separator="\n")


def fetch_pdf_text(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    doc = fitz.open(stream=resp.content, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def trim_letter_body(text: str) -> str:
    start = 0
    m_start = LETTER_START.search(text)
    if m_start:
        start = m_start.start()
    else:
        logger.warning("Letter start marker not found; keeping full text from beginning")

    end = len(text)
    m_end = LETTER_END.search(text)
    if m_end:
        end = m_end.end()
    else:
        logger.warning("Letter end marker not found; keeping text to end")

    return text[start:end].strip()


def clean_letter(text: str) -> str:
    text = trim_letter_body(text)
    text = re.sub(r"[^a-zA-Z0-9\n.]", " ", text)
    text = " ".join(nltk.word_tokenize(text))
    for old, new in CONTRACTION_FIXES:
        text = re.sub(old, new, text)
    return text.strip()


def save_letter(year: int, text: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{year}.txt"
    out_path.write_text(text + "\n", encoding="utf-8")
    return out_path


def download_year(year: int, output_dir: Path) -> bool:
    found = probe_url(year)
    if not found:
        logger.warning("No letter URL for %d", year)
        return False

    url, kind = found
    logger.info("Fetching %d from %s (%s)", year, url, kind)
    raw = fetch_pdf_text(url) if kind == "pdf" else fetch_html_text(url)
    if len(raw.strip()) < 100:
        logger.error("Text too short for %d", year)
        return False

    cleaned = clean_letter(raw)
    if len(cleaned) < 100:
        logger.error("Cleaned text too short for %d", year)
        return False

    path = save_letter(year, cleaned, output_dir)
    logger.info("Saved %s (%d chars)", path.name, len(cleaned))
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Download letters as one .txt per year")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-year", type=int, default=FIRST_HTML_YEAR)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    if args.start_year > args.end_year:
        parser.error("--start-year must be <= --end-year")

    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt", quiet=True)
    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab", quiet=True)

    ok, skipped, failed = 0, 0, 0
    for year in range(args.start_year, args.end_year + 1):
        out_path = args.output_dir / f"{year}.txt"
        if args.skip_existing and out_path.exists() and out_path.stat().st_size > 0:
            skipped += 1
            continue
        if download_year(year, args.output_dir):
            ok += 1
        else:
            failed += 1

    logger.info("Done: saved=%d skipped=%d failed=%d dir=%s", ok, skipped, failed, args.output_dir)


if __name__ == "__main__":
    main()
