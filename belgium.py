#!/usr/bin/env python3
"""
spain_translate.py

Scan the Spain folders and, for every case folder that contains **es.pdf** but
does NOT already have **en.txt** or **en.pdf**, generate BOTH files (English
translation) in-place.

Structure expected (case-insensitive for 'spain' and section names):
  documents/<spain|Spain>/<section>/<case_id>/es.pdf

Where <section> is one of:
  Blogs, Decisions, Guides, Infographics, Reports
(accepts common case variants like 'blogs', 'INFOrgraphics', etc.)

Usage:
  python3 spain_translate.py
  python3 spain_translate.py --force           # re-generate even if en.txt/en.pdf exist
  python3 spain_translate.py --root /path/to/repo
  python3 spain_translate.py --limit 10        # process at most 10 files

Requires:
  - OPENAI_API_KEY env var
  - PyMuPDF (fitz) and reportlab installed
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import List

import fitz  # PyMuPDF
from openai import OpenAI

# ReportLab for robust Unicode PDF generation
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm

# ===== Root & OpenAI =====
REPO_ROOT = Path(__file__).resolve().parent
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Set OPENAI_API_KEY before running (e.g., export OPENAI_API_KEY='sk-...').")
client = OpenAI(api_key=OPENAI_KEY)

# ===== Spain scanning config =====
SPAIN_DIR_NAMES = {"bulgaria"}  # accept both
VALID_SECTIONS = {"Annual Reports"}

# ---------- PDF TEXT EXTRACTION ----------
def extract_text_from_pdf(pdf_file: str) -> str:
    """
    Extract text from a PDF using PyMuPDF. If the PDF is scanned (no text),
    this returns an empty string.
    """
    try:
        doc = fitz.open(pdf_file)
        parts = [page.get_text("text") for page in doc]
        doc.close()
        return "\n".join(parts).strip()
    except Exception as e:
        print(f"[!] Failed to extract text from {pdf_file}: {e}", file=sys.stderr)
        return ""

# ---------- CHUNKING & TRANSLATION ----------
def chunks(s: str, max_chars: int = 6000):
    """
    Yield chunks <= max_chars. Try to break on paragraph boundaries to keep context neat.
    """
    s = s.strip()
    start = 0
    while start < len(s):
        end = min(start + max_chars, len(s))
        if end < len(s):
            nl = s.rfind("\n\n", start, end)
            if nl != -1 and nl > start + 2000:  # avoid tiny tail chunks
                end = nl + 2
        yield s[start:end]
        start = end

def translate_chunk(text_chunk: str) -> str:
    """
    Translate a single chunk via Chat Completions, with simple retry/backoff.
    """
    prompt = (
        "Translate the following legal document text from Spanish into English.\n"
        "Preserve meaning and important formatting cues (headings, numbered items), "
        "and do not summarize or omit content.\n\n"
        f"{text_chunk}"
    )
    backoff = 2
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a professional legal translator."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                seed=42,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"[!] Translation error (attempt {attempt+1}): {e}", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 16)
    return ""

def translate_text_full(text: str) -> str:
    """
    Translate the full document by chunking to respect token limits.
    """
    if not text:
        return ""
    out = []
    for i, ch in enumerate(chunks(text), start=1):
        print(f"[*] Translating chunk {i}...")
        t = translate_chunk(ch)
        if not t:
            print("[!] A chunk failed to translate; continuing.", file=sys.stderr)
        out.append(t)
    return "\n".join(out).strip()

# ---------- WRITE TXT ----------
def write_txt(text: str, output_path: str):
    Path(output_path).write_text(text, encoding="utf-8")

# ---------- REPORTLAB PDF WRITER ----------
def _find_unicode_font_path() -> str:
    """
    Find a good Unicode TTF font on common systems.
    If none is found, install DejaVu Sans or point to an available TTF.
    """
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",                  # Linux
        "/Library/Fonts/Arial Unicode.ttf",                                 # macOS
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",             # macOS
        "C:/Windows/Fonts/arialuni.ttf",                                    # Windows
        "C:/Windows/Fonts/seguisym.ttf",                                    # Windows
        "C:/Windows/Fonts/SegoeUI.ttf",                                     # Windows
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Unicode font not found. Install DejaVu Sans or provide a TTF path.")

def write_pdf(text: str, output_path: str, font_path: str | None = None):
    """
    Write a Unicode PDF using ReportLab.
    Uses Platypus Paragraph with splitLongWords=True to avoid line-wrap crashes on long tokens/URLs.
    """
    if font_path is None:
        font_path = _find_unicode_font_path()

    pdfmetrics.registerFont(TTFont("Unicode", font_path))

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    base_style = getSampleStyleSheet()["Normal"]
    style = ParagraphStyle(
        "LegalBody",
        parent=base_style,
        fontName="Unicode",
        fontSize=11,
        leading=14,
        allowWidows=1,
        allowOrphans=1,
        splitLongWords=True,
        wordWrap="LTR",
    )

    story = []
    for para in text.splitlines():
        if not para.strip():
            story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(para, style))

    doc.build(story)

# ---------- SPAIN DISCOVERY ----------
def is_spain_case_es_pdf(p: Path) -> bool:
    """
    True if path looks like: documents/<spain|Spain>/<section>/<case_id>/es.pdf
    (case-insensitive filename 'es.pdf'; section must be in VALID_SECTIONS)
    """
    if p.suffix.lower() != ".pdf":
        return False
    if p.name.lower() != "bg.pdf":
        return False

    parts = list(p.parts)
    # Must contain 'documents' and 'spain' segment just after
    try:
        i = parts.index("documents")
    except ValueError:
        return False

    # Expect at least: documents / spain / <section> / <case_id> / es.pdf
    # i      i+1    i+2        i+3                 end
    if len(parts) < i + 5:
        return False

    spain_seg = parts[i + 1]
    if spain_seg not in SPAIN_DIR_NAMES:
        return False

    section = parts[i + 2]
    # match section ignoring case & extra spaces
    normalized_section = re.sub(r"\s+", " ", section).strip().lower()
    valid_norm = {s.lower() for s in VALID_SECTIONS}
    if normalized_section not in valid_norm:
        return False

    return True

def find_spain_es_pdfs(repo_root: Path) -> List[Path]:
    """
    Recursively search under documents/spain (both cases) for es.pdf files
    in allowed sections.
    """
    hits = []
    docs_dir = repo_root / "documents"
    if not docs_dir.exists():
        return hits

    # Scan both 'spain' and 'Spain' if they exist
    for spain_dir_name in SPAIN_DIR_NAMES:
        base = docs_dir / spain_dir_name
        if not base.exists():
            continue
        # rglob for any es.pdf
        for p in base.rglob("fr.pdf"):
            if is_spain_case_es_pdf(p):
                hits.append(p.resolve())

    # de-dup and sort for stable order
    hits = sorted(set(hits))
    return hits

# ---------- PER-FILE PROCESSOR ----------
def process_one_pdf(pdf_path: Path, force: bool = False):
    """
    For a given source PDF (es.pdf), generate en.txt and en.pdf in the same folder.

    If --force is False:
      - If BOTH outputs already exist, skip.
      - If one or both are missing, (re)translate once and generate BOTH fresh.

    If --force is True:
      - Always (re)translate and overwrite BOTH outputs.
    """
    folder = pdf_path.parent
    out_txt = folder / "en.txt"
    out_pdf = folder / "en.pdf"

    already_txt = out_txt.exists()
    already_pdf = out_pdf.exists()

    if not force and already_txt and already_pdf:
        print(f"[=] Skip (already have en.txt/en.pdf): {folder}")
        return

    print(f"[+] Translating: {pdf_path}")
    src = extract_text_from_pdf(str(pdf_path))
    if not src:
        print("[!] No text found in es.pdf (possibly scanned). Add OCR if needed.", file=sys.stderr)
        return

    translated = translate_text_full(src)
    if not translated:
        print("[!] Translation returned empty text.", file=sys.stderr)
        return

    print(f"[write] {out_txt}")
    write_txt(translated, str(out_txt))
    print(f"[write] {out_pdf}")
    write_pdf(translated, str(out_pdf))

# ---------- CLI / MAIN ----------
def main():
    ap = argparse.ArgumentParser(
        description="Scan Spain folders and generate en.txt/en.pdf from es.pdf where missing."
    )
    ap.add_argument("--root", type=Path, default=REPO_ROOT, help="Repo root (default: script dir)")
    ap.add_argument("--force", action="store_true", help="Re-generate even if en.txt/en.pdf exist")
    ap.add_argument("--limit", type=int, default=0, help="Process at most N files (0 = all)")
    args = ap.parse_args()

    repo_root = args.root.resolve()
    targets = find_spain_es_pdfs(repo_root)

    if not targets:
        print("No Spain es.pdf files found in the expected structure.")
        return

    print(f"Found {len(targets)} es.pdf files under Spain sections: {sorted(VALID_SECTIONS)}")

    count = 0
    for idx, pdf in enumerate(targets, start=1):
        if args.limit and count >= args.limit:
            break
        print(f"\n=== [{idx}/{len(targets)}] Processing {pdf} ===")
        try:
            process_one_pdf(pdf, force=args.force)
            count += 1
        except Exception as e:
            print(f"[!] Failed on {pdf}: {e}", file=sys.stderr)

    print("\nDone.")

if __name__ == "__main__":
    main()