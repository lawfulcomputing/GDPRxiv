#!/usr/bin/env python3
# import argparse
# import json
# import os
# import re
# import sys
# import time
# from pathlib import Path
# from typing import Dict, Any, List

# # ========= OpenAI client =========
# try:
#     from openai import OpenAI
# except Exception:
#     print("Please install the OpenAI SDK:  pip install openai", file=sys.stderr)
#     raise

# MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
# OPENAI_KEY = os.getenv("OPENAI_API_KEY")
# if not OPENAI_KEY:
#     raise RuntimeError("Set OPENAI_API_KEY first, e.g.: export OPENAI_API_KEY='sk-...'")
# client = OpenAI(api_key=OPENAI_KEY)

# # ========= Readers (TXT preferred, PDF fallback) =========
# def read_pdf_text(pdf_path: Path) -> str:
#     try:
#         import fitz  # PyMuPDF
#     except Exception:
#         print("PyMuPDF not installed. Run: pip install PyMuPDF", file=sys.stderr)
#         return ""
#     try:
#         doc = fitz.open(str(pdf_path))
#         parts = [page.get_text("text") for page in doc]
#         doc.close()
#         return "\n".join(parts)
#     except Exception as e:
#         print(f"Failed to read PDF {pdf_path}: {e}", file=sys.stderr)
#         return ""

# def read_txt_text(txt_path: Path) -> str:
#     try:
#         return txt_path.read_text(encoding="utf-8", errors="ignore")
#     except Exception as e:
#         print(f"Failed to read TXT {txt_path}: {e}", file=sys.stderr)
#         return ""

# def load_text_from_folder(folder: Path) -> str:
#     txt_path = folder / "en.txt"
#     if txt_path.exists() and txt_path.is_file():
#         t = read_txt_text(txt_path)
#         if t.strip():
#             return t
#     pdf_path = folder / "en.pdf"
#     if pdf_path.exists() and pdf_path.is_file():
#         return read_pdf_text(pdf_path)
#     raise FileNotFoundError(f"Neither en.txt nor en.pdf found in {folder}")

# def load_text_from_file(file_path: Path) -> str:
#     if not file_path.exists() or not file_path.is_file():
#         raise FileNotFoundError(f"File not found: {file_path}")
#     suf = file_path.suffix.lower()
#     if suf == ".txt":
#         return read_txt_text(file_path)
#     elif suf == ".pdf":
#         return read_pdf_text(file_path)
#     else:
#         raise RuntimeError(f"Unsupported file type: {suf}. Use .txt or .pdf")

# # ========= metadata.json I/O =========
# def load_metadata(path: Path) -> Dict[str, Any]:
#     if not path.exists():
#         return {}
#     try:
#         return json.loads(path.read_text(encoding="utf-8"))
#     except Exception:
#         return {}

# def save_metadata_if_changed(meta_path: Path, new: Dict[str, Any]) -> bool:
#     old = load_metadata(meta_path)
#     changed = False
#     for k in ("decision", "fine", "controller", "articles"):
#         if str(old.get(k, "")).strip() != str(new.get(k, "")).strip():
#             changed = True
#             break
#     if changed:
#         meta = old
#         meta.update({
#             "decision": new.get("decision", ""),
#             "fine": new.get("fine", ""),
#             "controller": new.get("controller", ""),
#             "articles": new.get("articles", ""),
#         })
#         meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
#         print(f"[write] {meta_path}")
#         return True
#     else:
#         print("[=] metadata.json unchanged")
#         return False

# # ========= chunking =========
# def chunks(s: str, max_chars: int = 14000):
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

# # ========= prompts (OpenAI-only extraction) =========
# SYSTEM_PROMPT = """You are a precise legal information extractor for GDPR enforcement documents.

# Return STRICT JSON ONLY (no markdown, no prose) with keys exactly:
# {
#   "decision": "<string or 'unknown'>",
#   "fine": "0|<amount with optional currency>",
#   "controller": "<string or 'unknown'>",
#   "articles": "<comma-separated base GDPR article numbers only, e.g., '4, 5, 6'>"
# }

# Rules for "articles":
# - Include ONLY articles from Regulation (EU) 2016/679 (GDPR).
# - Reduce subparagraphs to base (e.g., 6(1)(f) -> 6). Expand ranges (e.g., 12–13 -> 12, 13).
# - Ignore ANY non-GDPR legal sources (national laws, directives, ECHR, Working Party 29, etc.).
# - If the document phrases them loosely (e.g., "GDPR article X and article Y"), infer these as GDPR articles.
# - Deduplicate and SORT ASCENDING before returning.
# - If none are clearly present, set "articles" to "".

# Controller:
# - List the controller(s) named or addressed by the decision (company, authority, or person).
# - Prefer full legal names as they appear in the text. If multiple, join with '; '.
# - If truly absent, return "unknown" (do NOT output complainant or authority unless they are the controller).

# General:
# - If a field is not present, use "unknown" for decision/controller and "0" for fine.
# - Output ONLY valid JSON with those exact keys and no trailing commas.
# """

# USER_PROMPT_TEMPLATE = """Extract the four fields from this English legal decision text:

# ---
# {chunk}
# ---
# """

# def _strip_json(s: str) -> str:
#     s = s.strip()
#     s = re.sub(r"^```(?:json)?\s*", "", s)
#     s = re.sub(r"\s*```$", "", s)
#     return s.strip()

# # ========= article list normalization (model output only) =========
# def _normalize_articles_list_from_model(raw: str) -> List[str]:
#     if not raw:
#         return []
#     s = raw.replace("–", "-").replace("—", "-")
#     tokens = re.split(r"\s*(?:,|;|and)\s*", s, flags=re.I)
#     seen = set()
#     out: List[str] = []

#     def push(n: int):
#         if 1 <= n <= 99:
#             t = str(n)
#             if t not in seen:
#                 seen.add(t)
#                 out.append(t)

#     for tok in tokens:
#         tok = tok.strip()
#         if not tok:
#             continue
#         if re.search(r"(?:-| to )", tok, flags=re.I):
#             m = re.findall(r"\d{1,2}", tok)
#             if len(m) >= 2:
#                 a, b = int(m[0]), int(m[1])
#                 lo, hi = sorted((a, b))
#                 for x in range(lo, hi + 1):
#                     push(x)
#             elif len(m) == 1:
#                 push(int(m[0]))
#             continue
#         m = re.match(r"^\s*(\d{1,2})", tok)
#         if m:
#             push(int(m.group(1)))
#     return out

# # ========= decision heuristic (after "Decision") =========
# DECISION_PATTERNS = [
#     (re.compile(r"\bpending\s+dismissal\b", re.I), "pending dismissal"),
#     (re.compile(r"\bpending\b", re.I), "pending"),
#     (re.compile(r"\bupheld\b", re.I), "upheld"),
#     (re.compile(r"\bdismiss(ed|al)\b", re.I), "dismissed"),
# ]

# def infer_decision_from_text(text: str) -> str:
#     if not text:
#         return ""
#     norm = text.replace("\r", "")
#     lines = norm.split("\n")
#     for i, line in enumerate(lines):
#         if re.search(r"\bdecision\b", line, re.I):
#             window = " ".join([line] + lines[i+1:i+4])[:600]
#             for rx, label in DECISION_PATTERNS:
#                 if rx.search(window):
#                     return label
#     for m in re.finditer(r"(?i)\bdecision\b.{0,300}", norm, re.S):
#         seg = m.group(0)
#         for rx, label in DECISION_PATTERNS:
#             if rx.search(seg):
#                 return label
#     return ""

# # ========= OpenAI extraction (union across chunks) =========
# def llm_extract_fields(text: str, retries: int = 3, backoff: float = 2.0) -> Dict[str, str]:
#     final = {"decision": "unknown", "fine": "0", "controller": "unknown", "articles": ""}
#     seen_articles = set()
#     ordered_articles: List[str] = []

#     for chunk in chunks(text):
#         prompt = USER_PROMPT_TEMPLATE.format(chunk=chunk[:200000])
#         last_err = None
#         _bo = backoff
#         for _ in range(retries):
#             try:
#                 resp = client.chat.completions.create(
#                     model=MODEL_NAME,
#                     messages=[
#                         {"role": "system", "content": SYSTEM_PROMPT},
#                         {"role": "user", "content": prompt},
#                     ],
#                     temperature=0.0,
#                 )
#                 raw = resp.choices[0].message.content or "{}"
#                 data = json.loads(_strip_json(raw))

#                 decision = str(data.get("decision", "unknown")).strip() or "unknown"
#                 fine = str(data.get("fine", "0")).strip() or "0"
#                 controller = str(data.get("controller", "unknown")).strip() or "unknown"
#                 arts = _normalize_articles_list_from_model(str(data.get("articles", "")).strip())

#                 # prefer the most informative non-unknown controller (longest text)
#                 if controller.lower() != "unknown":
#                     if final["controller"] == "unknown" or len(controller) > len(final["controller"]):
#                         final["controller"] = controller

#                 if final["decision"] == "unknown" and decision.lower() != "unknown":
#                     final["decision"] = decision
#                 if final["fine"] == "0" and fine != "0":
#                     final["fine"] = fine

#                 for a in arts:
#                     if a not in seen_articles:
#                         seen_articles.add(a)
#                         ordered_articles.append(a)
#                 break
#             except Exception as e:
#                 last_err = e
#                 time.sleep(min(_bo, 16))
#                 _bo *= 2
#         if last_err:
#             print(f"[warn] OpenAI extract error on a chunk: {last_err}", file=sys.stderr)

#     final["articles"] = ", ".join(sorted(ordered_articles, key=lambda x: int(x)))
#     return final

# # ========= Controller recovery (OpenAI-only) =========
# CONTROLLER_RECOVERY_SYSTEM = """Return STRICT JSON ONLY with:
# {"controller": "<controller(s) named in the document or 'unknown'>"}
# Rules:
# - Return only the data controller(s) addressed by the decision (company/authority/person), not the complainant or supervisory authority.
# - Prefer full legal names as they appear. If multiple controllers, join with '; '.
# - If none exist, return "unknown".
# - JSON only; no comments, no markdown.
# """

# CONTROLLER_RECOVERY_USER = """Your ONLY task: from the following text, return the controller(s).
# Text:
# ---
# {body}
# ---"""

# def recover_controller(text: str) -> str:
#     body = text[:180000]  # safety cap
#     try:
#         resp = client.chat.completions.create(
#             model=MODEL_NAME,
#             messages=[
#                 {"role": "system", "content": CONTROLLER_RECOVERY_SYSTEM},
#                 {"role": "user", "content": CONTROLLER_RECOVERY_USER.format(body=body)},
#             ],
#             temperature=0.0,
#         )
#         raw = resp.choices[0].message.content or "{}"
#         data = json.loads(_strip_json(raw))
#         ctrl = str(data.get("controller", "")).strip()
#         return ctrl if ctrl else "unknown"
#     except Exception as e:
#         print(f"[warn] controller recovery failed: {e}", file=sys.stderr)
#         return "unknown"

# # ========= pipeline =========
# def run_case_and_write(target: Path, is_file: bool) -> Dict[str, str]:
#     text = load_text_from_file(target) if is_file else load_text_from_folder(target)
#     if not text.strip():
#         raise RuntimeError("No text content found (empty/failed read).")

#     found = llm_extract_fields(text)

#     # Heuristic override for decision
#     heur = infer_decision_from_text(text)
#     if heur:
#         found["decision"] = heur

#     # Controller recovery pass (OpenAI-only) if needed
#     if not found.get("controller") or found["controller"].strip().lower() == "unknown":
#         ctrl = recover_controller(text)
#         if ctrl.lower() != "unknown":
#             found["controller"] = ctrl

#     # Ensure keys
#     for k in ("decision", "fine", "controller", "articles"):
#         if k not in found:
#             found[k] = "unknown" if k in ("decision", "controller") else ("0" if k == "fine" else "")

#     # Write metadata.json in the same folder if changed
#     folder = target.parent if is_file else target
#     meta_path = folder / "metadata.json"
#     print(f"[path] metadata.json -> {meta_path}")
#     save_metadata_if_changed(meta_path, found)

#     return found

# # ========= CLI =========
# def main():
#     ap = argparse.ArgumentParser(
#         description="Use ONLY OpenAI to extract decision, fine, controller, and GDPR-only base articles (ascending). Writes metadata.json in the same folder only if changed."
#     )
#     g = ap.add_mutually_exclusive_group(required=True)
#     g.add_argument("--dir", type=Path, help="Folder with en.txt/en.pdf (en.txt preferred)")
#     g.add_argument("--file", type=Path, help="Path to a single en.txt or en.pdf")

#     args = ap.parse_args()
#     target = args.file.resolve() if args.file else args.dir.resolve()

#     data = run_case_and_write(target, is_file=bool(args.file))
#     print(json.dumps(data, ensure_ascii=False, indent=2))

# if __name__ == "__main__":
#     main()
#!/usr/bin/env python3
"""
metadata.py

- Reads en.txt (preferred) or en.pdf from a case folder
- Uses ONLY OpenAI to extract: decision, fine, controller, GDPR-only articles
- Sorts articles ascending (base numbers only)
- Canonicalizes decision to simple labels (e.g., 'dismissed', 'upheld', 'pending dismissal', 'pending', etc.)
- Does NOT truncate controller or decision text beyond canonical decision labeling
- Recognizes EU-language GDPR abbreviations (DSGVO, RGPD, RODO, AVG, BDAR, etc.) as GDPR
- Writes metadata.json in the SAME folder (only if changed)
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

# ========= OpenAI client =========
try:
    from openai import OpenAI
except Exception:
    print("Please install the OpenAI SDK:  pip install openai", file=sys.stderr)
    raise

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Set OPENAI_API_KEY first, e.g.: export OPENAI_API_KEY='sk-...'")
client = OpenAI(api_key=OPENAI_KEY)

# ========= Readers (TXT preferred, PDF fallback) =========
def read_pdf_text(pdf_path: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except Exception:
        print("PyMuPDF not installed. Run: pip install PyMuPDF", file=sys.stderr)
        return ""
    try:
        doc = fitz.open(str(pdf_path))
        parts = [page.get_text("text") for page in doc]
        doc.close()
        return "\n".join(parts)
    except Exception as e:
        print(f"Failed to read PDF {pdf_path}: {e}", file=sys.stderr)
        return ""

def read_txt_text(txt_path: Path) -> str:
    try:
        return txt_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"Failed to read TXT {txt_path}: {e}", file=sys.stderr)
        return ""

def load_text_from_folder(folder: Path) -> str:
    txt_path = folder / "en.txt"
    if txt_path.exists() and txt_path.is_file():
        t = read_txt_text(txt_path)
        if t.strip():
            return t
    pdf_path = folder / "en.pdf"
    if pdf_path.exists() and pdf_path.is_file():
        return read_pdf_text(pdf_path)
    raise FileNotFoundError(f"Neither en.txt nor en.pdf found in {folder}")

def load_text_from_file(file_path: Path) -> str:
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    suf = file_path.suffix.lower()
    if suf == ".txt":
        return read_txt_text(file_path)
    elif suf == ".pdf":
        return read_pdf_text(file_path)
    else:
        raise RuntimeError(f"Unsupported file type: {suf}. Use .txt or .pdf")

# ========= metadata.json I/O (write only if changed) =========
def load_metadata(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_metadata_if_changed(meta_path: Path, new: Dict[str, Any]) -> bool:
    old = load_metadata(meta_path)
    changed = False
    for k in ("decision", "fine", "controller", "articles"):
        if str(old.get(k, "")).strip() != str(new.get(k, "")).strip():
            changed = True
            break
    if changed:
        meta = old
        meta.update({
            "decision": new.get("decision", ""),
            "fine": new.get("fine", ""),
            "controller": new.get("controller", ""),
            "articles": new.get("articles", ""),
        })
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[write] {meta_path}")
        return True
    else:
        print("[=] metadata.json unchanged")
        return False

# ========= chunking =========
def chunks(s: str, max_chars: int = 14000):
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

# ========= prompts (OpenAI-only extraction) =========
DECISION_LABELS = [
    "upheld",
    "dismissed",
    "pending dismissal",
    "pending",
    "rejected",
    "inadmissible",
    "unfounded",
    "no violation",
    "reprimand",
    "warning",
    "administrative fine",
    "partially upheld",
    "unknown"
]

# Widely used EU-language acronyms/translations for GDPR recognition
GDPR_SYNONYMS = [
    # English baseline
    "GDPR", "General Data Protection Regulation", "Regulation (EU) 2016/679",
    # German
    "DSGVO", "Datenschutz-Grundverordnung",
    # French / Spanish / Portuguese / Romanian
    "RGPD", "Règlement général sur la protection des données",
    "Reglamento general de protección de datos",
    "Regulamento geral sobre a proteção de dados",
    "Regulamentul general privind protecția datelor",
    # Dutch
    "AVG", "Algemene verordening gegevensbescherming",
    # Polish
    "RODO", "Rozporządzenie o ochronie danych osobowych",
    # Baltic languages
    "BDAR", "Bendrasis duomenų apsaugos reglamentas",   # LT
    "VDAR", "Vispārīgā datu aizsardzības regula",       # LV
    "IKÜM", "Isikuandmete kaitse üldmäärus",            # ET
    # Nordic
    "Dataskyddsförordningen",  # SE
    "Databeskyttelsesforordningen",  # DK
    "Tietosuoja-asetus",  # FI
    # Greek
    "ΓΚΠ", "Γενικός Κανονισμός Προστασίας Δεδομένων",
    # Bulgarian
    "ОРЗД", "Общ регламент относно защитата на данните",
    # South/central Europe (full names often used)
    "Opća uredba o zaštiti podataka",     # HR
    "Splošna uredba o varstvu podatkov",  # SI
    "Obecné nařízení o ochraně osobních údajů",  # CZ
    "Všeobecné nariadenie o ochrane údajov",     # SK
    "Általános adatvédelmi rendelet"            # HU
]

SYSTEM_PROMPT = f"""You are a precise legal information extractor for GDPR enforcement documents.

Return STRICT JSON ONLY (no markdown, no prose) with keys exactly:
{{
  "decision": "<one of {', '.join(DECISION_LABELS)}> ",
  "fine": "0|<amount with optional currency>",
  "controller": "<string or 'unknown'>",
  "articles": "<comma-separated base GDPR article numbers only, e.g., '4, 5, 6'>"
}}

Rules for "decision":
- Output exactly one of: {', '.join(DECISION_LABELS)}.
- If the text states 'dismissed as unfounded', use 'dismissed'.
- If unsure, output 'unknown'.

Rules for "articles":
- Include ONLY articles from Regulation (EU) 2016/679 (GDPR).
- Treat ANY citation that clearly refers to GDPR — including its acronyms/translations used across EU countries — as GDPR.
  Recognize the following as equivalent to GDPR: {', '.join(GDPR_SYNONYMS)}.
  Examples: "Article 6 DSGVO", "artículo 6 RGPD", "čl. 6 RODO", "art. 13 AVG", "čl. 5 BDAR" → all map to GDPR Article 6.
- Reduce subparagraphs to the base article (e.g., 6(1)(f) -> 6).
- Expand ranges (e.g., 12–13 -> 12, 13).
- Ignore ANY non-GDPR legal sources (national laws, directives, ECHR, etc.).
- Deduplicate and SORT ASCENDING before returning.
- If none are clearly present, set "articles" to "".

Controller:
- Return the controller(s) named or addressed by the decision (company/authority/person) WITHOUT truncation.
- Prefer full legal names as they appear. If multiple, join with '; '.
- If truly absent, return "unknown".

General:
- If a field is not present, use "unknown" for decision/controller and "0" for fine.
- Output ONLY valid JSON with those exact keys and no trailing commas.
"""

USER_PROMPT_TEMPLATE = """Extract the four fields from this English/legal decision text (may contain multilingual citations/acronyms for GDPR):

---
{chunk}
---
"""

def _strip_json(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()

# ========= normalize model's articles list (no document mining) =========
def _normalize_articles_list_from_model(raw: str) -> List[str]:
    """
    Normalize the *model's* 'articles' field to base numbers 1..99.
    (Does not scan the original document; only cleans/expands the model's own output.)
    """
    if not raw:
        return []
    s = raw.replace("–", "-").replace("—", "-")
    tokens = re.split(r"\s*(?:,|;|and)\s*", s, flags=re.I)
    seen = set()
    out: List[str] = []

    def push(n: int):
        if 1 <= n <= 99:
            t = str(n)
            if t not in seen:
                seen.add(t)
                out.append(t)

    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        # expand ranges like "5-7" or "5 to 7"
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
        # base number, possibly with subparagraphs "6(1)(f)"
        m = re.match(r"^\s*(\d{1,2})", tok)
        if m:
            push(int(m.group(1)))
    return out

# ========= decision helpers =========
DECISION_HEURISTICS = [
    (re.compile(r"\bdismiss(ed|al)\s+as\s+unfounded\b", re.I), "dismissed"),
    (re.compile(r"\b(application|complaint|appeal)\s+is\s+dismissed\b", re.I), "dismissed"),
    (re.compile(r"\bdismiss(ed|al)\b", re.I), "dismissed"),
    (re.compile(r"\bpending\s+dismissal\b", re.I), "pending dismissal"),
    (re.compile(r"\bpending\b", re.I), "pending"),
    (re.compile(r"\bupheld\b", re.I), "upheld"),
    (re.compile(r"\brejected\b", re.I), "rejected"),
    (re.compile(r"\binadmissible\b", re.I), "inadmissible"),
    (re.compile(r"\bunfounded\b", re.I), "dismissed"),
    (re.compile(r"\bno\s+violation\b", re.I), "no violation"),
    (re.compile(r"\breprimand\b", re.I), "reprimand"),
    (re.compile(r"\bwarning\b", re.I), "warning"),
    (re.compile(r"\badministrative\s+fine\b", re.I), "administrative fine"),
    (re.compile(r"\bpartially\s+upheld\b", re.I), "partially upheld"),
]

def infer_decision_from_text(text: str) -> str:
    if not text:
        return ""
    norm = text.replace("\r", "")
    lines = norm.split("\n")
    for i, line in enumerate(lines):
        if re.search(r"\bdecision\b", line, re.I):
            window = " ".join([line] + lines[i+1:i+4])[:600]
            for rx, label in DECISION_HEURISTICS:
                if rx.search(window):
                    return label
    for m in re.finditer(r"(?i)\bdecision\b.{0,300}", norm, re.S):
        seg = m.group(0)
        for rx, label in DECISION_HEURISTICS:
            if rx.search(seg):
                return label
    return ""

def canonicalize_decision(raw_decision: str, full_text: str) -> str:
    text = re.sub(r"\s+", " ", (full_text or "")).lower()
    PRIORITY = [
        (r"\bdismiss(ed|al)\s+as\s+unfounded\b", "dismissed"),
        (r"\b(application|complaint|appeal)\s+is\s+dismissed\b", "dismissed"),
        (r"\bdismiss(ed|al)\b", "dismissed"),
        (r"\bpending\s+dismissal\b", "pending dismissal"),
        (r"\bupheld\b", "upheld"),
        (r"\brejected\b", "rejected"),
        (r"\binadmissible\b", "inadmissible"),
        (r"\bunfounded\b", "dismissed"),
        (r"\bno\s+violation\b", "no violation"),
        (r"\breprimand\b", "reprimand"),
        (r"\bwarning\b", "warning"),
        (r"\badministrative\s+fine\b", "administrative fine"),
        (r"\bpartially\s+upheld\b", "partially upheld"),
    ]
    for rx, label in PRIORITY:
        if re.search(rx, text):
            return label

    raw = (raw_decision or "").strip().lower()
    ALIASES = {
        "pending": "pending dismissal",
        "dismissal": "dismissed",
        "reject": "rejected",
        "rejection": "rejected",
        "no breach": "no violation",
        "partially-upheld": "partially upheld",
    }
    for k, v in ALIASES.items():
        if k in raw:
            return v

    if raw in DECISION_LABELS:
        return raw
    return "unknown"

# ========= OpenAI extraction (union across chunks) =========
def llm_extract_fields(text: str, retries: int = 3, backoff: float = 2.0) -> Dict[str, str]:
    """
    Calls OpenAI on chunks and unions the results.
    - decision: first non-'unknown'
    - controller: first non-'unknown' (prefer longer string if multiple)
    - fine: first non-'0'
    - articles: union of model-reported base numbers only (sorted at the end)
    """
    final = {"decision": "unknown", "fine": "0", "controller": "unknown", "articles": ""}
    seen_articles = set()
    ordered_articles: List[str] = []

    for chunk in chunks(text):
        prompt = USER_PROMPT_TEMPLATE.format(chunk=chunk[:200000])
        last_err = None
        _bo = backoff
        for _ in range(retries):
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
                data = json.loads(_strip_json(raw))

                decision = str(data.get("decision", "unknown")).strip() or "unknown"
                fine = str(data.get("fine", "0")).strip() or "0"
                controller = str(data.get("controller", "unknown")).strip() or "unknown"
                arts = _normalize_articles_list_from_model(str(data.get("articles", "")).strip())

                if final["decision"] == "unknown" and decision.lower() != "unknown":
                    final["decision"] = decision
                if controller.lower() != "unknown":
                    if final["controller"] == "unknown" or len(controller) > len(final["controller"]):
                        final["controller"] = controller
                if final["fine"] == "0" and fine != "0":
                    final["fine"] = fine

                for a in arts:
                    if a not in seen_articles:
                        seen_articles.add(a)
                        ordered_articles.append(a)
                break
            except Exception as e:
                last_err = e
                time.sleep(min(_bo, 16))
                _bo *= 2
        if last_err:
            print(f"[warn] OpenAI extract error on a chunk: {last_err}", file=sys.stderr)

    final["articles"] = ", ".join(sorted(ordered_articles, key=lambda x: int(x)))
    return final

# ========= Controller recovery (OpenAI-only) =========
CONTROLLER_RECOVERY_SYSTEM = """Return STRICT JSON ONLY with:
{"controller": "<controller(s) named in the document or 'unknown'>"}
Rules:
- Return only the data controller(s) addressed by the decision (company/authority/person), not the complainant or supervisory authority.
- Prefer full legal names as they appear. If multiple controllers, join with '; '.
- If none exist, return "unknown".
- JSON only; no comments, no markdown.
"""

CONTROLLER_RECOVERY_USER = """Your ONLY task: from the following text, return the controller(s).
Text:
---
{body}
---"""

def recover_controller(text: str) -> str:
    body = text[:180000]  # safety cap
    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": CONTROLLER_RECOVERY_SYSTEM},
                {"role": "user", "content": CONTROLLER_RECOVERY_USER.format(body=body)},
            ],
            temperature=0.0,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(_strip_json(raw))
        ctrl = str(data.get("controller", "")).strip()
        return ctrl if ctrl else "unknown"
    except Exception as e:
        print(f"[warn] controller recovery failed: {e}", file=sys.stderr)
        return "unknown"

# ========= pipeline =========
def run_case_and_write(target: Path, is_file: bool) -> Dict[str, str]:
    # Read document
    text = load_text_from_file(target) if is_file else load_text_from_folder(target)
    if not text.strip():
        raise RuntimeError("No text content found (empty/failed read).")

    # Extract (OpenAI only)
    found = llm_extract_fields(text)

    # Prefer explicit outcome near "Decision"
    heur = infer_decision_from_text(text)
    if heur:
        found["decision"] = heur

    # Canonicalize based on full document (e.g., 'dismissed as unfounded' -> 'dismissed')
    found["decision"] = canonicalize_decision(found.get("decision", ""), text)

    # If controller still unknown, try a focused recovery pass (OpenAI-only)
    if not found.get("controller") or found["controller"].strip().lower() == "unknown":
        ctrl = recover_controller(text)
        if ctrl.lower() != "unknown":
            found["controller"] = ctrl

    # Ensure keys
    for k in ("decision", "fine", "controller", "articles"):
        if k not in found:
            found[k] = "unknown" if k in ("decision", "controller") else ("0" if k == "fine" else "")

    # Write metadata.json (only if changed)
    folder = target.parent if is_file else target
    meta_path = folder / "metadata.json"
    print(f"[path] metadata.json -> {meta_path}")
    save_metadata_if_changed(meta_path, found)

    return found

# ========= CLI =========
def main():
    ap = argparse.ArgumentParser(
        description="Use ONLY OpenAI to extract decision, fine, controller, and GDPR-only base articles (ascending). Canonicalizes decision to simple labels. Recognizes GDPR synonyms/acronyms across EU languages. Writes metadata.json in the same folder if changed."
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dir", type=Path, help="Folder with en.txt/en.pdf (en.txt preferred)")
    g.add_argument("--file", type=Path, help="Path to a single en.txt or en.pdf")

    args = ap.parse_args()
    target = args.file.resolve() if args.file else args.dir.resolve()

    data = run_case_and_write(target, is_file=bool(args.file))
    print(json.dumps(data, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
