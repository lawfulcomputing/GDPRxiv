#!/usr/bin/env python3
import os
import time
from pathlib import Path
from typing import Iterable, List

import fitz  # PyMuPDF  (kept in case you later also want PDF sources)
from openai import OpenAI
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm

# ======== CONFIG ========
REPO_ROOT = Path(__file__).resolve().parent
COUNTRY = "croatia"     
FILENAMES = ["hr.txt"]               
MODEL_NAME = "gpt-4o-mini"
# =========================

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Set OPENAI_API_KEY before running (e.g., export OPENAI_API_KEY='sk-...').")
client = OpenAI(api_key=OPENAI_KEY)

# --- allowed sections ---
SECTION_ALLOWLIST = {
    "Decisions", "Decisions & judgements", "decisions & judgments",
    "Decisions & Reports", "Decisions & Deliberations", "Hearings", "Decisions_2"
}

# ============== HELPERS ==============
def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception as e:
        print(f"[!] Failed to read TXT {path}: {e}")
        return ""

def chunks(s: str, max_chars: int = 6000) -> Iterable[str]:
    s = s.strip()
    start = 0
    while start < len(s):
        end = min(start + max_chars, len(s))
        if end < len(s):
            nl = s.rfind("\n\n", start, end)
            if nl != -1 and nl > start + 2000:
                end = nl + 2
        yield s[start:end]
        start = end

# ============== TRANSLATION ==============
def translate_chunk(text_chunk: str) -> str:
    prompt = (
        "Translate the following legal document text into English.\n"
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
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"[!] Translation error (attempt {attempt+1}): {e}")
            time.sleep(backoff)
            backoff = min(backoff * 2, 16)
    return ""

def translate_text_full(text: str) -> str:
    if not text:
        return ""
    out = []
    for i, ch in enumerate(chunks(text), start=1):
        print(f"[*] Translating chunk {i}...")
        t = translate_chunk(ch)
        if not t:
            print("[!] A chunk failed to translate; continuing.")
        out.append(t)
    return "\n".join(out).strip()

# ============== WRITE TXT/PDF ==============
def write_txt(text: str, output_path: str):
    Path(output_path).write_text(text, encoding="utf-8")

def _find_unicode_font_path() -> str:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "C:/Windows/Fonts/arialuni.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Unicode font not found. Install DejaVu Sans or provide a TTF path.")

def write_pdf(text: str, output_path: str, font_path: str | None = None):
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
        "LegalBody", parent=base_style, fontName="Unicode", fontSize=11, leading=14,
        splitLongWords=True, wordWrap="LTR",
    )
    story = []
    for para in text.splitlines():
        if not para.strip():
            story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(para, style))
    doc.build(story)

# ============== FIND TARGET FILES (TXT) ==============
def find_target_txts(repo_root: Path, country: str, filenames: List[str]) -> List[Path]:
    """
    Find .txt files with basenames matching FILENAMES inside:
      documents/<country>/<allowed SECTION>/**/<filename>.txt
    Skips 'en.txt' if included by mistake.
    """
    docs_root = repo_root / "documents" / country
    if not docs_root.exists():
        print(f"[!] Country folder not found: {docs_root}")
        return []

    filenames_lc = {f.lower() for f in filenames if f.lower() != "en.txt"}
    results: List[Path] = []

    allowed = {s.lower() for s in SECTION_ALLOWLIST}
    for section_dir in docs_root.iterdir():
        if not section_dir.is_dir() or section_dir.name.lower() not in allowed:
            continue
        for sub in section_dir.rglob("*.txt"):
            name = sub.name.lower()
            if name == "en.txt":
                continue
            if name in filenames_lc:
                results.append(sub)

    results.sort()
    return results

# ============== PROCESSOR (TXT -> en.txt + en.pdf) ==============
def process_one_txt(txt_path: Path):
    folder = str(txt_path.parent)
    out_txt = os.path.join(folder, "en.txt")
    out_pdf = os.path.join(folder, "en.pdf")

    # Skip if either output already exists
    if os.path.exists(out_txt) or os.path.exists(out_pdf):
        print(f"Skipping (already exists): {txt_path.parent}")
        return

    print(f"[+] Reading from: {txt_path}")
    src = read_text_file(txt_path)
    if not src:
        print("No text found in source .txt.")
        return

    print("Translating via OpenAI...")
    translated = translate_text_full(src)
    if not translated:
        print("No translated text returned.")
        return

    print(f"Writing: {out_txt}")
    write_txt(translated, out_txt)
    print(f"Writing: {out_pdf}")
    write_pdf(translated, out_pdf)
    print(f"[✓] Finished {txt_path.parent}")

# ============== MAIN ==============
def main():
    print(f"[*] Searching for TXT in country: {COUNTRY}")
    targets = find_target_txts(REPO_ROOT, COUNTRY, FILENAMES)
    if not targets:
        print("No matching .txt files found.")
        return

    print(f"Found {len(targets)} file(s):")
    for t in targets:
        print(f"  - {t}")

    for idx, path in enumerate(targets, 1):
        print(f"\n=== [{idx}/{len(targets)}] Processing {path} ===")
        process_one_txt(path)

    print("\nAll done.")

if __name__ == "__main__":
    main()
