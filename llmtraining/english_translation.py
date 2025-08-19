import os
import re
import time
import subprocess
from pathlib import Path

import fitz  # PyMuPDF
from openai import OpenAI

# ReportLab for robust Unicode PDF generation
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm


# Root of the repository
REPO_ROOT = Path(__file__).resolve().parent

# Git commit number
COMMIT_REF = "4af2ab3"   

# OpenAI model
MODEL_NAME = "gpt-4o-mini"  

# API key from env
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Set OPENAI_API_KEY before running (e.g., export OPENAI_API_KEY='sk-...').")
client = OpenAI(api_key=OPENAI_KEY)


# ============== PDF TEXT EXTRACTION ==============
def extract_text_from_pdf(pdf_file: str) -> str:
    """
    Extract text from a PDF using PyMuPDF. If the PDF is scanned (no text),
    this returns an empty string.
    """
    try:
        doc = fitz.open(pdf_file)
        parts = []
        for page in doc:
            parts.append(page.get_text("text"))

        doc.close()
        return "\n".join(parts).strip()
    except Exception as e:
        print(f"[!] Failed to extract text: {e}")
        return ""


# ============== CHUNKING & TRANSLATION ==============
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
            print("[!] A chunk failed to translate; continuing.")
        out.append(t)
    return "\n".join(out).strip()


# ============== WRITE TXT ==============
def write_txt(text: str, output_path: str):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)


# ============== REPORTLAB PDF WRITER ==============
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


# ============== GIT: CHANGED FILES FOR A GIVEN COMMIT ==============
def git_changed_files_for_commit(repo_dir: Path, commit_ref: str) -> list[Path]:
    """
    Return a list of files changed in the given commit (relative to its parent),
    as absolute Paths. Works for normal commits; for merges, you may want
    --first-parent or a different strategy.
    """
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_ref],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            check=True,
        )
        rel_paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return [repo_dir / p for p in rel_paths]
    except subprocess.CalledProcessError as e:
        print(f"[!] Git error for {commit_ref}: {e}")
        return []


def is_target_documents_pdf(p: Path) -> bool:
    """
    Accept only PDFs under:
      documents/<country>/(Decisions|Decisions & Judgements|Decisions & Judgments)/<file_folder>/<file.pdf>
    and ignore en.pdf already-produced files.
    """
    # if p.suffix.lower() != ".pdf":
    #     return False
    # if p.name.lower() == "en.pdf":
    #     return False
    # name = p.name.lower()
    # if name in {"en.pdf", "en.txt"}:
    #     return False
    # if name != "se_1.pdf":
    #     return False
    # name = p.name.lower()
    # if name not in {"se_1.txt", "se_1.pdf"}:
    #     return False
    name = p.name.lower()
    if name not in {"de.pdf"}:
        return False




    parts = p.parts
    # Find "documents" segment
    try:
        i = parts.index("documents")
    except ValueError:
        return False

    # Require at least: documents / <country> / <section> / <file_folder> / <file.pdf>
    if len(parts) < i + 5:
        return False

    country = parts[i + 1]
    section = parts[i + 2]
    if not country or country.startswith("."):
        return False

    valid_sections = {
        "Decisions",
        "Decisions & judgements",
        "decisions & judgments", 
        "Decisions & Reports",
        "Decisions & Deliberations",
        "Annual Reports",
        "Injunctions",
        "Infographics",
        "Guidelines",
        "Reports",
        "Opinions",
        "Public Disclosure",
        "Publications",
        "Hearings",
        "Decisions_2",
        "Notices",
        "Interviews",
        "Newsletters",
        "Guides",
        "AnnualReports",
    }
    if section not in valid_sections:
        return False

    return True


# ============== PER-FILE PROCESSOR ==============
def process_one_pdf(pdf_path: Path):
    """
    For a given source PDF, generate en.txt and en.pdf in the same folder.
    Skip entirely if either en.txt OR en.pdf already exists.
    """
    folder = str(pdf_path.parent)
    out_txt = os.path.join(folder, "en.txt")
    out_pdf = os.path.join(folder, "en.pdf")

    # Skip if either output exists
    if os.path.exists(out_txt) or os.path.exists(out_pdf):
        print(f"Skipping (output file exists): {pdf_path.parent}")
        return

    print(f"[+] Reading from: {pdf_path}")
    src = extract_text_from_pdf(str(pdf_path))
    if not src:
        print("No text found in PDF (possibly scanned). Add OCR if needed.")
        return

    print("Translating via Chat Completions...")
    translated = translate_text_full(src)
    if not translated:
        print("No translated text returned.")
        return

    print(f"Writing: {out_txt}")
    write_txt(translated, out_txt)
    print(f"Writing: {out_pdf}")
    write_pdf(translated, out_pdf)


# ============== MAIN: SPECIFIED COMMIT ONLY, SEQUENTIAL ==============
def main():
    # 1) Changed files for the specified commit
    changed = git_changed_files_for_commit(REPO_ROOT, COMMIT_REF)
    if not changed:
        print(f"No changed files detected for commit ref {COMMIT_REF}.")
        return

    # 2) Filter to target PDFs and sort for stable order
    target_pdfs = sorted(p for p in changed if is_target_documents_pdf(p))
    total = len(target_pdfs)
    print(f"PDFs in commit {COMMIT_REF} matching structure: {total}")
    if not target_pdfs:
        print("No target PDFs to process for this commit.")
        return

    # 3) Process sequentially (one at a time)
    for idx, pdf in enumerate(target_pdfs, start=1):
        print(f"\n=== [{idx}/{total}] Processing {pdf} ===")
        try:
            process_one_pdf(pdf)
        except Exception as e:
            print(f"[!] Failed on {pdf}: {e}")
        # Optional gentle pacing to help with API limits:
        # time.sleep(1)

    print("\nDone")


if __name__ == "__main__":
    main()
