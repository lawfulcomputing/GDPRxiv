# #!/usr/bin/env python3
# """
# meta_from_pdf_llm.py

# Read an en.pdf, ask OpenAI to extract:
#   - decision (string; "unknown" if unclear)
#   - fine (currency+amount string OR "0" if no fine)
#   - controller (string; "unknown" if unclear)
#   - articles (ONLY GDPR base article numbers, comma-separated)

# Writes/merges these into sibling metadata.json (same folder).
# """

# import argparse
# import json
# import os
# import re
# import sys
# import time
# from pathlib import Path
# from typing import Dict, Any, List

# # -------- OpenAI client --------
# try:
#     from openai import OpenAI
# except Exception:
#     print("[!] Please install the OpenAI SDK:  pip install openai", file=sys.stderr)
#     raise

# MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
# OPENAI_KEY = os.getenv("OPENAI_API_KEY")
# if not OPENAI_KEY:
#     raise RuntimeError("Set OPENAI_API_KEY before running (e.g., export OPENAI_API_KEY='sk-...').")
# client = OpenAI(api_key=OPENAI_KEY)

# # -------- PDF reading --------
# def read_pdf_text(pdf_path: Path) -> str:
#     try:
#         import fitz  # PyMuPDF
#     except Exception:
#         print("[!] PyMuPDF not installed. Run: pip install PyMuPDF", file=sys.stderr)
#         return ""
#     try:
#         doc = fitz.open(str(pdf_path))
#         parts = [page.get_text("text") for page in doc]
#         doc.close()
#         return "\n".join(parts)
#     except Exception as e:
#         print(f"[!] Failed to read PDF {pdf_path}: {e}", file=sys.stderr)
#         return ""

# # -------- file I/O --------
# def load_metadata(path: Path) -> Dict[str, Any]:
#     if not path.exists():
#         return {}
#     try:
#         return json.loads(path.read_text(encoding="utf-8"))
#     except Exception as e:
#         print(f"[!] Could not read/parse {path}: {e}", file=sys.stderr)
#         return {}

# def save_metadata(data: Dict[str, Any], path: Path):
#     path.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
#     print(f"[+] Wrote {path}")

# # -------- chunking --------
# def chunks(s: str, max_chars: int = 14000):
#     """Yield large, paragraph-aligned chunks to keep calls few & safe."""
#     s = s.strip()
#     i = 0
#     while i < len(s):
#         j = min(i + max_chars, len(s))
#         if j < len(s):
#             k = s.rfind("\n\n", i, j)
#             if k != -1 and k > i + 3000:
#                 j = k + 2
#         yield s[i:j]
#         i = j

# # -------- prompts --------
# SYSTEM_PROMPT = """You are a precise legal information extractor.
# Return STRICT JSON ONLY (no markdown, no prose) with keys:
# - decision: one of ["upheld","dismissed","rejected","partially upheld","warning","reprimand","administrative fine","unfounded","inadmissible","no violation","unknown"]. If unclear, "unknown".
# - fine: if a monetary fine is present, include a concise currency/amount string (e.g., "€ 15,000" or "15,000 EUR"); otherwise "0".
# - controller: the principal data controller / organization / entity (string). If unclear, "unknown".
# - articles: ONLY GDPR (Regulation (EU) 2016/679) articles, as a comma-separated list of BASE article numbers (e.g., "5, 6, 12"). Reduce subparagraphs (e.g., 6(1)(f) -> 6). Expand ranges (12–13 -> 12, 13). Deduplicate, keep order of first appearance. If none, "".

# CRITICAL:
# - IGNORE non-GDPR legal references entirely (e.g., national laws such as DSG, AVG, B-VG, VO-UA; criminal codes; constitutional provisions; court statutes).
# - Do NOT fabricate values; use "unknown" or "0" when information is not present.
# - JSON ONLY; no trailing commas.
# """

# USER_PROMPT_TEMPLATE = """Extract the four fields from this English legal PDF text:

# ---
# {chunk}
# ---
# """

# def _strip_json(s: str) -> str:
#     s = s.strip()
#     s = re.sub(r"^```(?:json)?\s*", "", s)
#     s = re.sub(r"\s*```$", "", s)
#     return s.strip()

# # -------- post-process (articles & coercions) --------
# def _expand_article_tokens(s: str) -> List[str]:
#     """Expand '12, 13 and 6-7' → ['12','13','6','7']; keep digits only."""
#     if not s:
#         return []
#     s = s.replace("–", "-").replace("—", "-")
#     parts = re.split(r"\s*(?:,|and)\s*", s, flags=re.I)
#     out: List[str] = []
#     for part in parts:
#         part = part.strip()
#         if not part:
#             continue
#         # reduce "6(1)(f)" → "6" before handling ranges
#         m_sub = re.match(r"^(\d+)", part)
#         if "-" in part:
#             nums = re.findall(r"\d+", part)
#             if len(nums) == 2:
#                 a, b = int(nums[0]), int(nums[1])
#                 if a <= b:
#                     out.extend(str(x) for x in range(a, b + 1))
#                 else:
#                     out.extend([str(a), str(b)])
#             elif len(nums) >= 1:
#                 out.append(nums[0])
#         elif m_sub:
#             out.append(m_sub.group(1))
#     return out

# def _normalize_articles(raw_articles: str) -> str:
#     """Keep only 1..99, dedupe, preserve order."""
#     seen = set()
#     ordered: List[str] = []
#     for tok in _expand_article_tokens(raw_articles):
#         if tok.isdigit():
#             n = int(tok)
#             if 1 <= n <= 99 and tok not in seen:
#                 seen.add(tok)
#                 ordered.append(tok)
#     return ", ".join(ordered)

# def _coerce_fields(obj: Dict[str, Any]) -> Dict[str, str]:
#     decision = str(obj.get("decision", "unknown")).strip().lower() or "unknown"
#     fine = str(obj.get("fine", "0")).strip() or "0"
#     controller = str(obj.get("controller", "unknown")).strip() or "unknown"
#     articles_raw = str(obj.get("articles", "")).strip()
#     # fine "none" -> "0"
#     if re.search(r"(?i)\bnone\b", fine) or fine == "":
#         fine = "0"
#     articles = _normalize_articles(articles_raw)
#     return {
#         "decision": decision,
#         "fine": fine,
#         "controller": controller,
#         "articles": articles,
#     }

# # -------- LLM extraction (chunk-union) --------
# def llm_extract_fields(text: str, retries: int = 3, backoff: float = 2.0) -> Dict[str, str]:
#     """
#     For long docs, query per chunk and union:
#       - decision/controller: first non-"unknown" seen
#       - fine: first non-"0" seen (else "0")
#       - articles: union across chunks, preserving global order
#     """
#     final = {"decision": "unknown", "fine": "0", "controller": "unknown", "articles": ""}
#     seen_articles = set()
#     ordered_articles: List[str] = []

#     for chunk in chunks(text):
#         prompt = USER_PROMPT_TEMPLATE.format(chunk=chunk[:200000])
#         last_err = None
#         for attempt in range(1, retries + 1):
#             try:
#                 resp = client.chat.completions.create(
#                     model=MODEL_NAME,
#                     messages=[
#                         {"role": "system", "content": SYSTEM_PROMPT},
#                         {"role": "user", "content": prompt},
#                     ],
#                     temperature=0.0,
#                 )
#                 content = _strip_json(resp.choices[0].message.content or "")
#                 data = json.loads(content)
#                 coerced = _coerce_fields(data)

#                 # decision/controller/fine selection
#                 if final["decision"] == "unknown" and coerced["decision"] != "unknown":
#                     final["decision"] = coerced["decision"]
#                 if final["controller"] == "unknown" and coerced["controller"] != "unknown":
#                     final["controller"] = coerced["controller"]
#                 if final["fine"] == "0" and coerced["fine"] != "0":
#                     final["fine"] = coerced["fine"]

#                 # merge articles
#                 if coerced["articles"]:
#                     for a in coerced["articles"].split(", "):
#                         if a and a not in seen_articles:
#                             seen_articles.add(a)
#                             ordered_articles.append(a)
#                 break
#             except Exception as e:
#                 last_err = e
#                 time.sleep(min(backoff, 16))
#                 backoff *= 2
#         if last_err:
#             print(f"[!] LLM extract error on a chunk: {last_err}", file=sys.stderr)

#     final["articles"] = ", ".join(ordered_articles)
#     return final

# # -------- updater --------
# def update_from_pdf(pdf_path: Path, force: bool = False) -> bool:
#     """
#     Given a specific en.pdf path, extract fields via LLM and update metadata.json in the same folder.
#     Writes ALL FOUR keys (never missing), honoring --force.
#     """
#     if not pdf_path.exists():
#         print(f"[!] File not found: {pdf_path}", file=sys.stderr)
#         return False
#     if pdf_path.suffix.lower() != ".pdf":
#         print(f"[!] Not a PDF: {pdf_path}", file=sys.stderr)
#         return False

#     folder = pdf_path.parent
#     meta_path = folder / "metadata.json"

#     text = read_pdf_text(pdf_path)
#     if not text.strip():
#         print(f"[!] No text in {pdf_path} (scanned? no OCR).")
#         return False

#     found = llm_extract_fields(text)
#     # ensure all four keys exist
#     for k in ("decision", "fine", "controller", "articles"):
#         found.setdefault(k, "unknown" if k in ("decision", "controller") else "0" if k == "fine" else "")

#     meta = load_metadata(meta_path)
#     changed = False
#     for k, val in found.items():
#         if force or (k not in meta or not str(meta.get(k)).strip()):
#             meta[k] = val
#             print(f"[+] Set {k}: {val!r}")
#             changed = True
#         else:
#             print(f"[=] {k} exists; not overwriting")

#     if changed:
#         save_metadata(meta, meta_path)
#     else:
#         print("[=] Nothing to update.")
#     return changed

# def update_folder(folder: Path, force: bool = False) -> bool:
#     """
#     Folder mode: expects folder/en.pdf.
#     """
#     pdf_path = folder / "en.pdf"
#     if not pdf_path.exists():
#         print(f"[!] No en.pdf in {folder}")
#         return False
#     return update_from_pdf(pdf_path, force=force)

# # -------- CLI --------
# def main():
#     ap = argparse.ArgumentParser(
#         description="Extract decision, fine, controller, and GDPR-only articles from en.pdf via OpenAI and update metadata.json."
#     )
#     g = ap.add_mutually_exclusive_group(required=True)
#     g.add_argument("--dir", type=Path, help="Folder that contains en.pdf")
#     g.add_argument("--file", type=Path, help="Path to a single en.pdf")
#     ap.add_argument("--force", action="store_true", help="Overwrite existing values.")
#     args = ap.parse_args()

#     if args.file:
#         update_from_pdf(args.file.resolve(), force=args.force)
#     else:
#         update_folder(args.dir.resolve(), force=args.force)

# if __name__ == "__main__":
#     main()
#!/usr/bin/env python3
"""
meta_from_pdf_llm.py

Read an en.pdf, ask OpenAI to extract:
  - decision (string; "unknown" if unclear)
  - fine (currency+amount string OR "0" if no fine)
  - controller (string; "unknown" if unclear)
  - articles (ONLY GDPR base article numbers, comma-separated)

Writes/merges these into sibling metadata.json (same folder).
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

# -------- OpenAI client --------
try:
    from openai import OpenAI
except Exception:
    print("[!] Please install the OpenAI SDK:  pip install openai", file=sys.stderr)
    raise

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Set OPENAI_API_KEY before running (e.g., export OPENAI_API_KEY='sk-...').")
client = OpenAI(api_key=OPENAI_KEY)

# -------- PDF reading --------
def read_pdf_text(pdf_path: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except Exception:
        print("[!] PyMuPDF not installed. Run: pip install PyMuPDF", file=sys.stderr)
        return ""
    try:
        doc = fitz.open(str(pdf_path))
        parts = [page.get_text("text") for page in doc]
        doc.close()
        return "\n".join(parts)
    except Exception as e:
        print(f"[!] Failed to read PDF {pdf_path}: {e}", file=sys.stderr)
        return ""

# -------- file I/O --------
def load_metadata(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[!] Could not read/parse {path}: {e}", file=sys.stderr)
        return {}

def save_metadata(data: Dict[str, Any], path: Path):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    print(f"[+] Wrote {path}")

# -------- chunking --------
def chunks(s: str, max_chars: int = 14000):
    """Yield large, paragraph-aligned chunks to keep calls few & safe."""
    s = s.strip()
    i = 0
    while i < len(s):
        j = min(i + max_chars, len(s))
        if j < len(s):
            k = s.rfind("\n\n", i, j)
            if k != -1 and k > i + 3000:
                j = k + 2
        yield s[i:j]
        i = j

# -------- prompts (AI-only extraction) --------
SYSTEM_PROMPT = """You are a precise legal information extractor for GDPR enforcement documents.

Return STRICT JSON ONLY (no markdown, no prose) with keys exactly:
{
  "decision": "upheld|dismissed|rejected|partially upheld|warning|reprimand|administrative fine|unfounded|inadmissible|no violation|unknown",
  "fine": "0|<currency+amount like '€ 15,000' or '15,000 EUR'>",
  "controller": "<string or 'unknown'>",
  "articles": "<comma-separated GDPR base article numbers only, e.g., '5, 6, 12'>"
}

Rules:
- "articles": ONLY Regulation (EU) 2016/679 (GDPR) articles. If a subparagraph is cited (e.g., 6(1)(f)), reduce to its base article (6). Expand ranges (e.g., 12–13 -> 12, 13). Deduplicate and keep order of first appearance. If none, set to "".
- Ignore all non-GDPR laws (national statutes, directives, constitutions, criminal codes, etc.) when filling "articles".
- If a field is not clearly present, use "unknown" for decision/controller and "0" for fine.
- JSON only; no trailing commas; do not include explanations.
"""

USER_PROMPT_TEMPLATE = """Extract the four fields from this English legal PDF text:

---
{chunk}
---
"""

def _strip_json(s: str) -> str:
    """Remove accidental Markdown fences from model output."""
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()

# -------- articles normalization --------
def _normalize_articles(raw_articles: str) -> str:
    """Keep only integers 1..99, expand ranges, dedupe, preserve order."""
    if not raw_articles:
        return ""
    s = raw_articles.replace("–", "-").replace("—", "-")
    tokens = re.split(r"\s*(?:,|and)\s*", s, flags=re.I)
    seen = set()
    ordered: List[str] = []

    def push(n: int):
        if 1 <= n <= 99:
            t = str(n)
            if t not in seen:
                seen.add(t)
                ordered.append(t)

    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        # ranges like "5-7" or "5 to 7"
        if re.search(r"(?:-| to )", tok, flags=re.I):
            m = re.findall(r"\d{1,2}", tok)
            if len(m) >= 2:
                a, b = int(m[0]), int(m[1])
                lo, hi = sorted((a, b))
                for x in range(lo, hi + 1):
                    push(x)
            elif len(m) == 1:
                push(int(m[0]))
            continue
        # base number possibly with subparagraphs like "6(1)(f)"
        m = re.match(r"^\s*(\d{1,2})", tok)
        if m:
            push(int(m.group(1)))

    return ", ".join(ordered)

def _coerce_fields(obj: Dict[str, Any]) -> Dict[str, str]:
    """Coerce and sanitize model output."""
    decision = str(obj.get("decision", "unknown")).strip().lower() or "unknown"
    fine = str(obj.get("fine", "0")).strip()
    controller = str(obj.get("controller", "unknown")).strip() or "unknown"
    articles = _normalize_articles(str(obj.get("articles", "")).strip())

    # Accept synonyms like "none" for fine
    if fine.lower() in {"", "none", "no fine", "n/a"}:
        fine = "0"

    # Strictly constrain decision to known set; otherwise 'unknown'
    _allowed = {
        "upheld","dismissed","rejected","partially upheld","warning",
        "reprimand","administrative fine","unfounded","inadmissible",
        "no violation","unknown"
    }
    if decision not in _allowed:
        decision = "unknown"

    return {
        "decision": decision,
        "fine": fine or "0",
        "controller": controller or "unknown",
        "articles": articles,  # already GDPR-only & base numbers
    }

# -------- LLM extraction (AI unions across chunks) --------
def llm_extract_fields(text: str, retries: int = 3, backoff: float = 2.0) -> Dict[str, str]:
    """
    Chunk the document, let the model extract per-chunk, then union:
      - decision/controller: first non-default seen
      - fine: first non-"0"
      - articles: union in global order
    """
    final = {"decision": "unknown", "fine": "0", "controller": "unknown", "articles": ""}
    seen_articles = set()
    ordered_articles: List[str] = []

    for chunk in chunks(text):
        prompt = USER_PROMPT_TEMPLATE.format(chunk=chunk[:200000])
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                )
                raw = resp.choices[0].message.content or "{}"
                raw = _strip_json(raw)
                data = json.loads(raw)
                coerced = _coerce_fields(data)

                # decision/controller/fine selection
                if final["decision"] == "unknown" and coerced["decision"] != "unknown":
                    final["decision"] = coerced["decision"]
                if final["controller"] == "unknown" and coerced["controller"] != "unknown":
                    final["controller"] = coerced["controller"]
                if final["fine"] == "0" and coerced["fine"] != "0":
                    final["fine"] = coerced["fine"]

                # articles union (already base GDPR numbers only)
                if coerced["articles"]:
                    for a in coerced["articles"].split(", "):
                        if a and a not in seen_articles:
                            seen_articles.add(a)
                            ordered_articles.append(a)
                break
            except Exception as e:
                last_err = e
                time.sleep(min(backoff, 16))
                backoff *= 2
        if last_err:
            print(f"[!] LLM extract error on a chunk: {last_err}", file=sys.stderr)

    final["articles"] = ", ".join(ordered_articles)
    return final

# -------- updater --------
def update_from_pdf(pdf_path: Path, force: bool = False) -> bool:
    """
    Given a specific en.pdf path, extract fields via LLM and update metadata.json in the same folder.
    Writes ALL FOUR keys (never missing), honoring --force.
    """
    if not pdf_path.exists():
        print(f"[!] File not found: {pdf_path}", file=sys.stderr)
        return False
    if pdf_path.suffix.lower() != ".pdf":
        print(f"[!] Not a PDF: {pdf_path}", file=sys.stderr)
        return False

    folder = pdf_path.parent
    meta_path = folder / "metadata.json"

    text = read_pdf_text(pdf_path)
    if not text.strip():
        print(f"[!] No text in {pdf_path} (scanned? no OCR).")
        return False

    found = llm_extract_fields(text)
    # ensure all four keys exist
    for k in ("decision", "fine", "controller", "articles"):
        found.setdefault(k, "unknown" if k in ("decision", "controller") else "0" if k == "fine" else "")

    meta = load_metadata(meta_path)
    changed = False
    for k, val in found.items():
        if force or (k not in meta or not str(meta.get(k)).strip()):
            meta[k] = val
            print(f"[+] Set {k}: {val!r}")
            changed = True
        else:
            print(f"[=] {k} exists; not overwriting")

    if changed:
        save_metadata(meta, meta_path)
    else:
        print("[=] Nothing to update.")
    return changed

def update_folder(folder: Path, force: bool = False) -> bool:
    """
    Folder mode: expects folder/en.pdf.
    """
    pdf_path = folder / "en.pdf"
    if not pdf_path.exists():
        print(f"[!] No en.pdf in {folder}")
        return False
    return update_from_pdf(pdf_path, force=force)

# -------- CLI --------
def main():
    ap = argparse.ArgumentParser(
        description="Extract decision, fine, controller, and GDPR-only articles from en.pdf via OpenAI and update metadata.json."
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dir", type=Path, help="Folder that contains en.pdf")
    g.add_argument("--file", type=Path, help="Path to a single en.pdf")
    ap.add_argument("--force", action="store_true", help="Overwrite existing values.")
    args = ap.parse_args()

    if args.file:
        update_from_pdf(args.file.resolve(), force=args.force)
    else:
        update_folder(args.dir.resolve(), force=args.force)

if __name__ == "__main__":
    main()

