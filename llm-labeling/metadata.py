#!/usr/bin/env python3
"""
metadata.py

- Reads en.txt (preferred) or en.pdf from a case folder
- Uses ONLY OpenAI to extract: decision, fine, controller, GDPR-only articles
- Robust GDPR article extraction that:
  * Works even when "GDPR/RGPD/DSGVO" isn't repeated (uses context + old/alternate names)
  * Handles dotted/subparagraph forms (6.1 -> 6, 58(2)(b) -> 58), ranges, enumerations
  * Expands ranges, reduces to base numbers, dedupes, sorts ascending
  * Excludes NON-GDPR instruments even if the same article number appears elsewhere as GDPR
    (classification is local to the sentence/clause context; only GDPR-classified mentions remain)
- Writes metadata.json in the SAME folder (only if changed)

NOTE: This file uses a safe _chat_complete() wrapper that avoids
"Unsupported value: 'temperature'..." errors by omitting temperature when needed.
"""            

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Iterable, Tuple

# ========= OpenAI client =========
try:
    from openai import OpenAI
except Exception:
    print("Please install the OpenAI SDK:  pip install openai", file=sys.stderr)
    raise

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5")  # default to gpt-5 if available
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Set OPENAI_API_KEY first, e.g.: export OPENAI_API_KEY='sk-...'")
client = OpenAI(api_key=OPENAI_KEY)

# ---- Safe chat completion wrapper (avoids temperature=0 errors) ----
RAW_TEMP = os.getenv("OPENAI_TEMPERATURE", "").strip()
TEMPERATURE = None if RAW_TEMP == "" else float(RAW_TEMP)

def _chat_complete(messages, model=MODEL_NAME, temperature=TEMPERATURE):
    """
    Safe chat completion that works with models which disallow explicit temperature.
    - Tries with provided temperature if not None
    - On 400 'unsupported_value' for 'temperature', retries WITHOUT the temperature field
    """
    kwargs = dict(model=model, messages=messages)
    if temperature is not None:
        kwargs["temperature"] = temperature
    try:
        try:
            return client.chat.completions.create(**kwargs)
        except AttributeError:
            # for older SDK variants
            return client.chat_completions.create(**kwargs)
    except Exception as e:
        msg = str(e)
        if "unsupported_value" in msg and "temperature" in msg:
            kwargs.pop("temperature", None)
            try:
                try:
                    return client.chat.completions.create(**kwargs)
                except AttributeError:
                    return client.chat_completions.create(**kwargs)
            except Exception:
                raise
        raise

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
        meta.update(
            {
                "decision": new.get("decision", ""),
                "fine": new.get("fine", ""),
                "controller": new.get("controller", ""),
                "articles": new.get("articles", ""),
            }
        )
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
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
    "upheld","dismissed","pending dismissal","pending","rejected","inadmissible",
    "unfounded","no violation","reprimand","warning","administrative fine",
    "partially upheld","unknown","administrative penalty fine","infringement",
    "notice","administrative sanction fine","no infraction","instructions",
    "file the procedure","criticism","serious criticism","closed",
    "discontinue the action","in accordance with the rules","notify an order",
    "groundless","gives an order","rejecting the application","official warning",
    "condemns","baseless and unproven","termination of procedure",
    "partially granting the request","violation of the law","expressed serious criticism",
    "ORDER THE FILE","reprimand and injunction","partial violation","admonish",
    "Address","complete assessment","impose corrective measures","re-assess the fine",
    "issues a reminder","reject the cassation appeal","violated GDPR","monetary penalties",
    "illegality of data protection","change the fine amount","satisfy injunction",
    "lacks the competence to examine the complaint","remains in force","enforcement notices",
    "partially condemns","need appropriate corrective measure and review later",
    "prohibition of the processing","strictly reprimand","did not comply with GDPR",
    "without legal basis","discontinues the proceedings","notify the data breach",
    "delete the personal data","address the data breach","illegal data processing",
    "unlawful processing","unjustified delay","fulfill obligations",
    "provide the personal data","reformulates corrective action",
    "partial illegal data processing","has not complied",
    "fulfill obligations and delete the personal data","application approved",
    "official examination","refused","unlawful","announces a complaint","finding of abuse",
    "grounds for issuing an order to notify of breach","reprimand and instruction",
    "imposed a corrective measure",
]

DECISION_ONLY_SYSTEM = f"""Return STRICT JSON ONLY with:
{{"decision": "<one of {', '.join(DECISION_LABELS)}>"}}
Guidance:
- Read the ENTIRE document below and select the single FINAL OPERATIVE outcome (not proposals, allegations, or interim steps).
- Prefer sections titled 'Decision', 'Operative part', 'Dispositivo', 'Fallo', 'Resolución', or similar if present.
- If the case is closed/archived or ends due to payment/administrative closure, choose 'termination of procedure'.
- If unclear, return "unknown". No extra keys, comments, or markdown."""
DECISION_ONLY_USER = """Document:
---
{body}
---"""

FINE_ONLY_SYSTEM = """Return STRICT JSON ONLY with:
{"fine": "<digits-only or 0>"}
Guidance:
- Read the ENTIRE document and return the FINAL/EFFECTIVE amount actually PAID or IMPOSED (digits only).
- If there are more than one fines to be paid give the final amount as the sum if the mentioned fines. For example "FIRST: TO IMPOSE on LÍNEA DIRECTA ASEGURADORA, S.A., INSURANCE AND REINSURANCE COMPANY, with NIF A80871031:  
1. For an infringement of article 6.1 of the GDPR, classified in article 83.5.a) of the GDPR, an administrative fine (article 58.2.i) in the amount of €100,000 (one hundred thousand euros)  
2. For an infringement of article 28 of the GDPR, classified in article 83.4.a) of the GDPR, an administrative fine (article 58.2.i) in the amount of €200,000 (two hundred thousand euros)  " here the total amount is "300000"
- If multiple amounts exist (proposed, reduced, paid), prefer the final/paid amount.
- Focus on the operative/final sections near the end.
- If no fine or unclear, return "0". No comments, no extra keys."""
FINE_ONLY_USER = """Document:
---
{body}
---"""

# ----------------- Article extraction -----------------
# Instruments explicitly NOT GDPR (used to filter out false positives)
NON_GDPR_TOKENS = [
    # Spain / typical national laws
    "LOPDGDD","LOPD 15/1999","Ley Orgánica 3/2018","Ley 39/2015","Ley 40/2015",
    "LPACAP","Real Decreto","Royal Decree","RDL","RD",
    # Germany/others
    "BDSG","DSG","Telekommunikationsgesetz","Telemediengesetz","TTDSG",
    # Other instruments (exclude)
    "Directive","Directive 95/46/EC","Directive 2002/58/EC","ePrivacy",
    "Regulation (EU) 2018/1725","eIDAS","NIS","DGA","DMA","DSA",
    "ECHR","CEDH","Convention","Charter of Fundamental Rights","TFEU","TFUE",
    "Civil Code","Criminal Code","Penal Code","Código","Code","Constitution"
]

# Old/alternate ways the GDPR is referenced
GDPR_ALIASES = [
    "General Data Protection Regulation","Regulation (EU) 2016/679",
    "EU Regulation 2016/679","RGPD","DSGVO","Règlement (UE) 2016/679",
    "Règlement général sur la protection des données","RGPD de l’UE",
    "Reglamento (UE) 2016/679","Reglamento General de Protección de Datos",
    "Regolamento (UE) 2016/679","Regolamento generale sulla protezione dei dati",
    "Datenschutz-Grundverordnung","GDPR"
]

ARTICLES_ONLY_SYSTEM = f"""Return STRICT JSON ONLY with:
{{"articles":"<comma-separated base GDPR article numbers only>"}}

CRITICAL OBJECTIVE
- Read the entire document like a human reviewer would.
- Return ONLY those article NUMBERS (1–99) that are GDPR articles in context.
- A mention MUST be treated as GDPR if:
  * It explicitly names GDPR or any of its aliases ({'; '.join(GDPR_ALIASES)}), OR
  * The legal/analysis context clearly concerns the GDPR even if "GDPR" isn't repeated (e.g., the decision is a GDPR enforcement action, sanctions under Article 83 with typical GDPR enumerations, corrective powers per Article 58, cross-border cooperation under Article 60), OR
  * The text uses multilingual/short forms (“Art.”,“Artículo”,“Artikel”,“čl.”,“articolo”, etc.) that clearly refer to the GDPR in the surrounding sentence/section.

INSTRUMENT DISAMBIGUATION (very important)
- If the SAME sentence/clause ties an article number to a NON-GDPR instrument (e.g., “Article 20 of the LOPDGDD”; tokens include: {', '.join(NON_GDPR_TOKENS)}), then EXCLUDE that number for that occurrence.
- If an article number appears in BOTH GDPR and non-GDPR contexts in different places, INCLUDE it (because at least one context is GDPR).
- Never include recitals (“Recital 47”), titles, chapters, or sections without a concrete article.

COUNT WHEN ANY OF THESE APPEAR
- “Article N”, “Articles N1, N2, …”, “Art. N”, multilingual equivalents.
- Subparts: “58(2)(b)”, “6(1)(f)”, dotted forms “6.1”, “58.2”.
- Ranges: “12–13”, “12-13”.
- Sanction/aggregation clauses: If “83(5)(a)” mentions “Articles 5, 6, 7, 9”, include 83 plus 5, 6, 7, 9.

TRANSFORM
- Reduce subparts to base: 58(2)(b) → 58; 6(1)(f) → 6; 6.1 → 6; 58.2 → 58.
- Expand ranges: 12–13 → 12, 13.
- Deduplicate and SORT ascending.

OUTPUT
- Only valid JSON with exactly key "articles" and a comma-separated list, e.g., "4, 5, 6".
"""

ARTICLES_ONLY_USER = """Document:
---
{body}
---"""

SYSTEM_PROMPT = f"""You are a precise legal information extractor for GDPR enforcement documents.

Return STRICT JSON ONLY (no markdown, no prose) with keys exactly:
{{
  "decision": "<one of {', '.join(DECISION_LABELS)}> ",
  "fine": "0|<digits only>",
  "controller": "<string or 'unknown'>",
  "articles": "<comma-separated base GDPR article numbers only, e.g., '4, 5, 6'>"
}}

Rules for "decision":
- Output exactly one of: {', '.join(DECISION_LABELS)}.
- If the text states 'dismissed as unfounded', use 'dismissed'.
- If unsure, output 'unknown'.

Rules for "fine":
- Return ONLY the digits of the amount (e.g., '74000', '20000').
- Remove any currency symbols/words (€, euro, EUR, USD, pounds, etc.).
- If multiple amounts appear (proposed vs. reduced vs. paid), return the FINAL/EFFECTIVE amount actually imposed or paid after reductions/early payment.
- If no fine is imposed or unclear, return "0".

Rules for "articles" (context-aware GDPR inference):
- Use the Articles-Only rules provided to extract GDPR articles.
- Accept explicit and contextually clear GDPR mentions (GDPR aliases, sanction clauses, corrective powers, cooperation mechanisms) even if 'GDPR' isn't repeated in the sentence.
- EXCLUDE if the same sentence/clause ties the number to a non-GDPR instrument.
- Reduce to base numbers, expand ranges, deduplicate, sort. No guessing beyond the evidence.

Controller:
- Return the controller(s) named or addressed by the decision (company/authority/person) WITHOUT truncation.
- Prefer full legal names as they appear. If multiple, join with '; '.
- If truly absent, return "unknown".

General:
- If a field is not present, use "unknown" for decision/controller and "0" for fine.
- Output ONLY valid JSON with those exact keys and no trailing commas.
"""

USER_PROMPT_TEMPLATE = """Extract the four fields from this legal decision text:

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
    Normalize the model's 'articles' field to base numbers 1..99.
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
        # base number, possibly with subparagraphs "6(1)(f)" or dotted "6.1"
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
    (re.compile(r"\binfringement\b", re.I), "infringement"),
    (re.compile(r"\bnotice\b", re.I), "notice"),
    (re.compile(r"\badministrative\s+penalty\s+fine\b", re.I), "administrative penalty fine"),
    (re.compile(r"\badministrative\s+fines\b", re.I), "administrative fine"),
    (re.compile(r"\badministrative\s+sanction\s+fee\b", re.I), "administrative sanction fine"),
    (re.compile(r"\bno\s+infraction\b", re.I), "no infraction"),
    (re.compile(r"\binstructions?\b", re.I), "instructions"),
    (re.compile(r"\bfile\s+the\s+procedure\b", re.I), "file the procedure"),
    (re.compile(r"\bcriticism\b", re.I), "criticism"),
    (re.compile(r"\bserious\s+criticism\b", re.I), "serious criticism"),
    (re.compile(r"\bclosed\b", re.I), "closed"),
    (re.compile(r"\bdiscontinue\s+the\s+action\b", re.I), "discontinue the action"),
    (re.compile(r"\bin\s+accordance\s+with\s+the\s+rules\b", re.I), "in accordance with the rules"),
    (re.compile(r"\bnotify\s+an\s+order\b", re.I), "notify an order"),
    (re.compile(r"\bgroundless\b", re.I), "groundless"),
    (re.compile(r"\bgives\s+an\s+order\b", re.I), "gives an order"),
    (re.compile(r"\brejecting\s+the\s+application\b", re.I), "rejecting the application"),
    (re.compile(r"\bofficial\s+warning\b", re.I), "official warning"),
    (re.compile(r"\bcondemns\b", re.I), "condemns"),
    (re.compile(r"\bbaseless\s+and\s+unproven\b", re.I), "baseless and unproven"),
    (re.compile(r"\btermination\s+of\s+procedure\b", re.I), "termination of procedure"),
    (re.compile(r"\bpartially\s+granting\s+the\s+request\b", re.I), "partially granting the request"),
    (re.compile(r"\bviolation\s+of\s+the\s+law\b", re.I), "violation of the law"),
    (re.compile(r"\bexpressed\s+serious\s+criticism\b", re.I), "expressed serious criticism"),
    (re.compile(r"\border\s+the\s+file\b", re.I), "ORDER THE FILE"),
    (re.compile(r"\breprimand\s+and\s+injunction\b", re.I), "reprimand and injunction"),
    (re.compile(r"\bpartial\s+violation\b", re.I), "partial violation"),
    (re.compile(r"\badmonish\b", re.I), "admonish"),
    (re.compile(r"\baddress\b", re.I), "Address"),
    (re.compile(r"\bcomplete\s+assessment\b", re.I), "complete assessment"),
    (re.compile(r"\bimpose\s+corrective\s+measures\b", re.I), "impose corrective measures"),
    (re.compile(r"\bre\-assess\s+the\s+fine\b", re.I), "re-assess the fine"),
    (re.compile(r"\bissues\s+a\s+reminder\b", re.I), "issues a reminder"),
    (re.compile(r"\breject\s+the\s+cassation\s+appeal\b", re.I), "reject the cassation appeal"),
    (re.compile(r"\bviolated\s+gdpr\b", re.I), "violated GDPR"),
    (re.compile(r"\bmonetary\s+penalties\b", re.I), "monetary penalties"),
    (re.compile(r"\billegality\s+of\s+data\s+protection\b", re.I), "illegality of data protection"),
    (re.compile(r"\bchange\s+the\s+fine\s+amount\b", re.I), "change the fine amount"),
    (re.compile(r"\bsatisfy\s+injunction\b", re.I), "satisfy injunction"),
    (re.compile(r"\blacks\s+the\s+competence\s+to\s+examine\s+the\s+complaint\b", re.I), "lacks the competence to examine the complaint"),
    (re.compile(r"\bremains\s+in\s+force\b", re.I), "remains in force"),
    (re.compile(r"\benforcement\s+notices\b", re.I), "enforcement notices"),
    (re.compile(r"\bpartially\s+condemns\b", re.I), "partially condemns"),
    (re.compile(r"\bneed\s+appropriate\s+corrective\s+measure\s+and\s+review\s+later\b", re.I), "need appropriate corrective measure and review later"),
    (re.compile(r"\bprohibition\s+of\s+the\s+processing\b", re.I), "prohibition of the processing"),
    (re.compile(r"\bstrictly\s+reprimand\b", re.I), "strictly reprimand"),
    (re.compile(r"\bdid\s+not\s+comply\s+with\s+gdpr\b", re.I), "did not comply with GDPR"),
    (re.compile(r"\bwithout\s+legal\s+basis\b", re.I), "without legal basis"),
    (re.compile(r"\bdiscontinues\s+the\s+proceedings\b", re.I), "discontinues the proceedings"),
    (re.compile(r"\bnotify\s+the\s+data\s+breach\b", re.I), "notify the data breach"),
    (re.compile(r"\bdelete\s+the\s+personal\s+data\b", re.I), "delete the personal data"),
    (re.compile(r"\baddress\s+the\s+data\s+breach\b", re.I), "address the data breach"),
    (re.compile(r"\billegal\s+data\s+processing\b", re.I), "illegal data processing"),
    (re.compile(r"\bunlawful\s+processing\b", re.I), "unlawful processing"),
    (re.compile(r"\bunjustified\s+delay\b", re.I), "unjustified delay"),
    (re.compile(r"\bfulfill\s+obligations\b", re.I), "fulfill obligations"),
    (re.compile(r"\bprovide\s+the\s+personal\s+data\b", re.I), "provide the personal data"),
    (re.compile(r"\breformulates\s+corrective\s+action\b", re.I), "reformulates corrective action"),
    (re.compile(r"\bpartial\s+illegal\s+data\s+processing\b", re.I), "partial illegal data processing"),
    (re.compile(r"\bhas\s+not\s+complied\b", re.I), "has not complied"),
    (re.compile(r"\bfulfill\s+obligations\s+and\s+delete\s+the\s+personal\s+data\b", re.I), "fulfill obligations and delete the personal data"),
    (re.compile(r"\bapplication\s+approved\b", re.I), "application approved"),
    (re.compile(r"\bofficial\s+examination\b", re.I), "official examination"),
    (re.compile(r"\brefused\b", re.I), "refused"),
    (re.compile(r"\bunlawful\b", re.I), "unlawful"),
    (re.compile(r"\bannounces\s+a\s+complaint\b", re.I), "announces a complaint"),
    (re.compile(r"\bfinding\s+of\s+abuse\b", re.I), "finding of abuse"),
    (re.compile(r"\bgrounds\s+for\s+issuing\s+an\s+order\s+to\s+notify\s+of\s+breach\b", re.I), "grounds for issuing an order to notify of breach"),
    (re.compile(r"\breprimand\s+and\s+instruction\b", re.I), "reprimand and instruction"),
    (re.compile(r"\bimposed\s+a\s+corrective\s+measure\b", re.I), "imposed a corrective measure"),
]

def infer_decision_from_text(text: str) -> str:
    if not text:
        return ""
    norm = text.replace("\r", "")
    lines = norm.split("\n")
    for i, line in enumerate(lines):
        if re.search(r"\bdecision\b", line, re.I):
            window = " ".join([line] + lines[i + 1 : i + 4])[:600]
            for rx, label in DECISION_HEURISTICS:
                if rx.search(window):
                    return label
    for m in re.finditer(r"(?i)\bdecision\b.{0,300}", norm, re.S):
        seg = m.group(0)
        for rx, label in DECISION_HEURISTICS:
            if rx.search(seg):
                return label
    return ""

def llm_decide_final_decision(text: str, retries: int = 3, backoff: float = 2.0) -> str:
    """Single whole-document pass to choose the final operative decision label."""
    body = text[:180000]
    last_err = None
    _bo = backoff
    for _ in range(retries):
        try:
            resp = _chat_complete(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": DECISION_ONLY_SYSTEM},
                    {"role": "user", "content": DECISION_ONLY_USER.format(body=body)},
                ],
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(_strip_json(raw))
            dec = (data.get("decision") or "unknown").strip()
            return dec if dec else "unknown"
        except Exception as e:
            last_err = e
            time.sleep(min(_bo, 16))
            _bo *= 2
    if last_err:
        print(f"[warn] whole-document decision failed: {last_err}", file=sys.stderr)
    return "unknown"

def llm_decide_final_fine(text: str, retries: int = 3, backoff: float = 2.0) -> str:
    """Whole-document pass to return the FINAL/PAID fine (digits only)."""
    body = text[:180000]
    last_err = None
    _bo = backoff
    for _ in range(retries):
        try:
            resp = _chat_complete(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": FINE_ONLY_SYSTEM},
                    {"role": "user", "content": FINE_ONLY_USER.format(body=body)},
                ],
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(_strip_json(raw))
            fine = normalize_fine_to_digits((data.get("fine") or "0").strip())
            return fine if fine else "0"
        except Exception as e:
            last_err = e
            time.sleep(min(_bo, 16))
            _bo *= 2
    if last_err:
        print(f"[warn] whole-document fine failed: {last_err}", file=sys.stderr)
    return "0"

def llm_decide_full_articles(text: str, retries: int = 3, backoff: float = 2.0) -> List[str]:
    """
    Whole-document pass for GDPR articles with context inference:
    - Includes GDPR even when not explicitly repeated (uses aliases and enforcement context)
    - Excludes explicit non-GDPR ties in the same sentence/clause
    - Reduces to base numbers, expands ranges, dedupes, sorts
    """
    body = text[:180000]
    last_err = None
    _bo = backoff
    for _ in range(retries):
        try:
            resp = _chat_complete(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": ARTICLES_ONLY_SYSTEM},
                    {"role": "user", "content": ARTICLES_ONLY_USER.format(body=body)},
                ],
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(_strip_json(raw))
            arts = _normalize_articles_list_from_model(str(data.get("articles", "")).strip())
            return arts
        except Exception as e:
            last_err = e
            time.sleep(min(_bo, 16))
            _bo *= 2
    if last_err:
        print(f"[warn] whole-document articles failed: {last_err}", file=sys.stderr)
    return []

def _split_controllers(val: str) -> List[str]:
    """
    Split a controller field into a list of unique names, preserving order.
    Accepts separators like ';' or ' and '.
    Filters out empty/unknown.
    """
    if not val:
        return []
    s = val.strip()
    s = s.replace(" and ", "; ")
    parts = [p.strip() for p in s.split(";")]
    seen, out = set(), []
    for p in parts:
        if not p or p.lower() == "unknown":
            continue
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

# ========= Fine normalization (digits-only) =========
_NUM_RE = re.compile(r"(?:\d{1,3}(?:[.,]\d{3})+|\d+)")

def normalize_fine_to_digits(fine: str) -> str:
    """
    Keep only digits of the numeric amount; drop currency/symbols/words.
    '€ 74,000' -> '74000', '20.000 euros' -> '20000', 'EUR5000' -> '5000'
    If no usable number is present, return '0'.
    """
    if not fine:
        return "0"
    m = _NUM_RE.search(fine)
    if not m:
        return "0"
    digits_only = re.sub(r"[^\d]", "", m.group(0))
    return digits_only if digits_only else "0"

# progress helpers
def _load_progress(progress_path: Path) -> Dict[str, Any]:
    if progress_path and progress_path.exists():
        try:
            return json.loads(progress_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "last_chunk": -1,
        "decision": "unknown",
        "fine_best": None,
        "fine": "0",
        "controller_candidates": [],
        "articles_seen": [],
    }

def _save_progress(progress_path: Path, state: Dict[str, Any]) -> None:
    if not progress_path:
        return
    tmp = progress_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(progress_path)


# ========= OpenAI extraction (union across chunks) =========
def llm_extract_fields(text: str,progress_path: Path | None = None, retries: int = 3, backoff: float = 2.0) -> Dict[str, str]:
    """
    Calls OpenAI on chunks and unions the results.
    - decision: first non-'unknown'
    - controller: keep only the primary (first) name
    - fine: choose the SMALLEST non-zero digits-only amount (final/paid)
    - articles: union of model-reported base numbers only (sorted at the end)
    """

    state = _load_progress(progress_path)
    seen_articles = set(state.get("articles_seen", []))
    controllers_found: List[str] = state.get("controller_candidates", [])
    best_fine_val = state.get("fine_best", None)
    final_decision = state.get("decision", "unknown")
    last_done = state.get("last_chunk", -1)

    for idx, chunk in enumerate(chunks(text)):
        if idx <= last_done:
            continue
        if progress_path:
            state["last_chunk"] = idx - 1
            _save_progress(progress_path, state)

        prompt = USER_PROMPT_TEMPLATE.format(chunk=chunk[:200000])
        last_err = None
        _bo = backoff
        for _ in range(retries):
            try:
                resp = _chat_complete(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                )
                raw = resp.choices[0].message.content or "{}"
                data = json.loads(_strip_json(raw))
                last_err = None
                break
            except Exception as e:
                last_err = e
                time.sleep(min(_bo, 16))
                _bo *= 2
        if last_err:
            print(f"[warn] OpenAI extract error on a chunk: {last_err}", file=sys.stderr)
            state["last_chunk"] = max(-1, idx - 1) 
            _save_progress(progress_path, state)
            continue

        decision = str(data.get("decision", "unknown")).strip() or "unknown"
        if final_decision  == "unknown" and decision.lower() != "unknown":
            final_decision  = decision

        fine_raw = str(data.get("fine", "0")).strip() or "0"
        fine = normalize_fine_to_digits(fine_raw)
        if fine.isdigit():
            val = int(fine)
            if val > 0 and (best_fine_val is None or val < best_fine_val):
                best_fine_val = val

        controller_val = str(data.get("controller", "unknown")).strip()
        for c in _split_controllers(controller_val):
            if c not in controllers_found:
                controllers_found.append(c)

        arts = _normalize_articles_list_from_model(str(data.get("articles", "")).strip())
        for a in arts:
            seen_articles.add(a)

        state.update({
            "last_chunk": idx,
            "decision": final_decision,
            "fine_best": best_fine_val,
            "controller_candidates": controllers_found,
            "articles_seen": sorted(seen_articles, key=lambda x: int(x)),
        })
        _save_progress(progress_path, state)

    return {
        "decision": final_decision or "unknown",
        "fine": str(best_fine_val) if (best_fine_val is not None and best_fine_val > 0) else "0",
        "controller": controllers_found[0] if controllers_found else "unknown",
        "articles": ", ".join(sorted(seen_articles, key=lambda x: int(x))),
    }


def run_case_and_write(target: Path, is_file: bool) -> Dict[str, str]:
    # Read document
    text = load_text_from_file(target) if is_file else load_text_from_folder(target)
    if not text.strip():
        raise RuntimeError("No text content found (empty/failed read).")
    
    folder = target.parent if is_file else target
    progress_path = folder / "progress.json"

    # Extract (OpenAI only)
    found = llm_extract_fields(text, progress_path=progress_path)

    # Whole-document decision/fine confirmers
    dec_full = llm_decide_final_decision(text)
    if dec_full.lower() != "unknown":
        found["decision"] = dec_full
    elif not found["decision"] or found["decision"].strip().lower() == "unknown":
        heur = infer_decision_from_text(text)
        if heur:
            found["decision"] = heur

    fine_full = llm_decide_final_fine(text)
    if fine_full != "0":
        found["fine"] = fine_full

    # Whole-document pass for articles using context-aware GDPR inference
    full_articles = llm_decide_full_articles(text)
    if full_articles:
        existing = _normalize_articles_list_from_model(found.get("articles", ""))
        merged = sorted(set(existing).union(full_articles), key=lambda x: int(x))
        found["articles"] = ", ".join(merged)

    # Ensure keys
    for k in ("decision", "fine", "controller", "articles"):
        if k not in found:
            found[k] = (
                "unknown" if k in ("decision", "controller")
                else ("0" if k == "fine" else "")
            )

    # Write metadata.json (only if changed)
    meta_path = folder / "metadata.json"
    print(f"[path] metadata.json -> {meta_path}")
    changed = save_metadata_if_changed(meta_path, found)

    # Cleanup progress checkpoint once metadata is written
    try:
        if progress_path.exists():
            progress_path.unlink()
    except Exception as e:
        print(f"[warn] could not remove progress file {progress_path}: {e}", file=sys.stderr)

    return found


# ========= Repo walker (country/section/case) =========  
SECTION_ALLOWLIST = {  
    "Decisions",
    "Decisions & judgements",
    "decisions & judgments",
    "Decisions & Reports",
    "Decisions & Deliberations",
    "Annual Reports",
    "Reports",
    "Decisions_2",
    "AnnualReports",
}

DECISION_LIKE_SECTIONS = { 
    "Decisions",
    "Decisions & judgements",
    "decisions & judgments",
    "Decisions & Reports",
    "Decisions & Deliberations",
    "Annual Reports",
    "Reports",
    "Decisions_2",
    "AnnualReports",
}

def metadata_missing_or_empty(meta: Dict[str, Any]) -> bool: 
    for k in ("decision", "fine", "controller", "articles"):
        v = str(meta.get(k, "")).strip()
        if v == "":
            return True
    return False

def should_process_case_folder(case_dir: Path, force: bool) -> Tuple[bool, str]: 
    """
    Returns (should_process, reason)
    """
    if not ((case_dir / "en.txt").exists() or (case_dir / "en.pdf").exists()):
        return (False, "no en.txt/en.pdf")
    meta_path = case_dir / "metadata.json"
    if force:
        return (True, "--force")
    if not meta_path.exists():
        return (True, "metadata.json missing")
    meta = load_metadata(meta_path)
    if metadata_missing_or_empty(meta):
        return (True, "metadata fields missing/empty")
    return (False, "metadata complete")

def iter_case_folders(  
    repo_root: Path,
    only_decision_like: bool,
    country_names: List[str] | None = None,
) -> Iterable[Path]:
    """
    Yields paths like: documents/<country>/<section>/<case_folder>,
    filtered by selected country names (case-insensitive).
    """
    documents_root = repo_root / "documents"
    if not documents_root.exists():
        return

    sel_names = set(n.lower() for n in country_names) if country_names else None

    # Pick countries
    country_iter = [p for p in documents_root.iterdir() if p.is_dir()]
    for country_dir in country_iter:
        if sel_names is not None and country_dir.name.lower() not in sel_names:
            continue

        for section_dir in country_dir.iterdir():
            if not section_dir.is_dir():
                continue
            section_name = section_dir.name
            if only_decision_like:
                if section_name not in DECISION_LIKE_SECTIONS:
                    continue
            else:
                if section_name not in SECTION_ALLOWLIST:
                    continue

            for case_dir in section_dir.iterdir():
                if case_dir.is_dir():
                    yield case_dir

def run_repo_scan(  
    repo_root: Path,
    force: bool = False,
    dry_run: bool = False,
    only_decision_like: bool = True,
    country_names: List[str] | None = None,
):
    """
    Walk the repository and process case folders whose metadata.json
    is missing/empty for any of the 4 target fields, restricted to the user-given countries.
    """
    total = processed = skipped = 0
    for case_dir in iter_case_folders(
        repo_root,
        only_decision_like=only_decision_like,
        country_names=country_names,
    ):
        total += 1
        ok, reason = should_process_case_folder(case_dir, force=force)
        if not ok:
            skipped += 1
            print(f"[skip] {case_dir} ({reason})")
            continue
        print(f"[todo] {case_dir} ({reason})")
        if dry_run:
            continue
        try:
            run_case_and_write(case_dir, is_file=False)
            processed += 1
        except Exception as e:
            print(f"[!] Failed on {case_dir}: {e}", file=sys.stderr)
    print(f"\nScan summary: total={total}, processed={processed}, skipped={skipped}, dry_run={dry_run}")


# ========= CLI =========
def main():
    ap = argparse.ArgumentParser(
        description="Use ONLY OpenAI to extract decision/fine/controller and GDPR-only base articles (context-aware, excludes non-GDPR ties; expands ranges; dedupe; sort)."
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dir", type=Path, help="Folder with en.txt/en.pdf (en.txt preferred)")
    g.add_argument("--file", type=Path, help="Path to a single en.txt or en.pdf")
    g.add_argument("--repo", type=Path, help="Path to repo root containing documents/")

     # Country selection by user (one or more names) 
    ap.add_argument(
        "--country",
        nargs="+",
        help="One or more country folder names under documents/ (case-insensitive), e.g. --country Spain Germany",
    ) 

    # Optional behavior flags
    ap.add_argument("--force", action="store_true", help="Re-extract even if metadata fields already exist")  
    ap.add_argument("--dry-run", action="store_true", help="List what would be processed without calling OpenAI")  
    ap.add_argument("--all-sections", action="store_true", help="Process across SECTION_ALLOWLIST, not just decision-like sections")


    args = ap.parse_args()
    if args.repo:  # <<< ADDED
        repo_root = args.repo.resolve()
        if not args.country:
            print("[error] --repo requires --country (one or more country folder names under documents/).", file=sys.stderr)
            sys.exit(2)
        run_repo_scan(
            repo_root=repo_root,
            force=args.force,
            dry_run=args.dry_run,
            only_decision_like=not args.all_sections,
            country_names=args.country,
        )
        return
    
    target = args.file.resolve() if args.file else ( args.dir.resolve() if args.dir else None)
    if not target:
        print("[error] Provide either --repo with --country, or --dir/--file.", file=sys.stderr) 
        sys.exit(2)

    data = run_case_and_write(target, is_file=bool(args.file))
    print(json.dumps(data, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

# #!/usr/bin/env python3
# """
# metadata.py

# - Reads en.txt (preferred) or en.pdf from a case folder
# - Uses ONLY OpenAI to extract: decision, fine, controller, GDPR-only articles
# - Robust GDPR article extraction that:
#   * Works even when "GDPR/RGPD/DSGVO" isn't repeated (uses context + old/alternate names)
#   * Handles dotted/subparagraph forms (6.1 -> 6, 58(2)(b) -> 58), ranges, enumerations
#   * Expands ranges, reduces to base numbers, dedupes, sorts ascending
#   * Excludes NON-GDPR instruments even if the same article number appears elsewhere as GDPR
#     (classification is local to the sentence/clause context; only GDPR-classified mentions remain)
# - Writes metadata.json in the SAME folder (only if changed)

# NOTE: This file uses a safe _chat_complete() wrapper that avoids
# "Unsupported value: 'temperature'..." errors by omitting temperature when needed.
# """

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

# MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5")  # default to gpt-5 if available
# OPENAI_KEY = os.getenv("OPENAI_API_KEY")
# if not OPENAI_KEY:
#     raise RuntimeError("Set OPENAI_API_KEY first, e.g.: export OPENAI_API_KEY='sk-...'")
# client = OpenAI(api_key=OPENAI_KEY)

# # ---- Safe chat completion wrapper (avoids temperature=0 errors) ----
# RAW_TEMP = os.getenv("OPENAI_TEMPERATURE", "").strip()
# TEMPERATURE = None if RAW_TEMP == "" else float(RAW_TEMP)

# def _chat_complete(messages, model=MODEL_NAME, temperature=TEMPERATURE):
#     """
#     Safe chat completion that works with models which disallow explicit temperature.
#     - Tries with provided temperature if not None
#     - On 400 'unsupported_value' for 'temperature', retries WITHOUT the temperature field
#     """
#     kwargs = dict(model=model, messages=messages)
#     if temperature is not None:
#         kwargs["temperature"] = temperature
#     try:
#         try:
#             return client.chat.completions.create(**kwargs)
#         except AttributeError:
#             # for older SDK variants
#             return client.chat_completions.create(**kwargs)
#     except Exception as e:
#         msg = str(e)
#         if "unsupported_value" in msg and "temperature" in msg:
#             kwargs.pop("temperature", None)
#             try:
#                 try:
#                     return client.chat.completions.create(**kwargs)
#                 except AttributeError:
#                     return client.chat_completions.create(**kwargs)
#             except Exception:
#                 raise
#         raise

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

# # ========= metadata.json I/O (write only if changed) =========
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
#         meta.update(
#             {
#                 "decision": new.get("decision", ""),
#                 "fine": new.get("fine", ""),
#                 "controller": new.get("controller", ""),
#                 "articles": new.get("articles", ""),
#             }
#         )
#         meta_path.write_text(
#             json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
#         )
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
# DECISION_LABELS = [
#     "upheld","dismissed","pending dismissal","pending","rejected","inadmissible",
#     "unfounded","no violation","reprimand","warning","administrative fine",
#     "partially upheld","unknown","administrative penalty fine","infringement",
#     "notice","administrative sanction fine","no infraction","instructions",
#     "file the procedure","criticism","serious criticism","closed",
#     "discontinue the action","in accordance with the rules","notify an order",
#     "groundless","gives an order","rejecting the application","official warning",
#     "condemns","baseless and unproven","termination of procedure",
#     "partially granting the request","violition of the law","expressed serious criticism",
#     "ORDER THE FILE","reprimand and injunction","partial violation","admonish",
#     "Address","complete assessment","impose corrective measures","re-assess the fine",
#     "issues a reminder","reject the cassation appeal","violated GDPR","monetary penalties",
#     "illegality of data protection","change the fine amount","satisfy injunction",
#     "lacks the competence to examine the complaint","remains in force","enforcement notices",
#     "partially condemns","need appropriate corrective measure and review later",
#     "prohibition of the processing","strictly reprimand","did not comply with GDPR",
#     "without legal basis","discontinues the proceedings","notify the data breach",
#     "delete the personal data","address the data breach","illegal data processing",
#     "unlawful processing","unjustified delay","fulfill obligations",
#     "provide the personal data","reformulates corrective action",
#     "partial illegal data processing","has not complied",
#     "fulfill obligations and delete the personal data","application approved",
#     "official examination","refused","unlawful","announces a complaint","finding of abuse",
#     "grounds for issuing an order to notify of breach","reprimand and instruction",
#     "imposed a corrective measure",
# ]

# DECISION_ONLY_SYSTEM = f"""Return STRICT JSON ONLY with:
# {{"decision": "<one of {', '.join(DECISION_LABELS)}>"}}
# Guidance:
# - Read the ENTIRE document below and select the single FINAL OPERATIVE outcome (not proposals, allegations, or interim steps).
# - Prefer sections titled 'Decision', 'Operative part', 'Dispositivo', 'Fallo', 'Resolución', or similar if present.
# - If the case is closed/archived or ends due to payment/administrative closure, choose 'termination of procedure'.
# - If unclear, return "unknown". No extra keys, comments, or markdown."""
# DECISION_ONLY_USER = """Document:
# ---
# {body}
# ---"""

# FINE_ONLY_SYSTEM = """Return STRICT JSON ONLY with:
# {"fine": "<digits-only or 0>"}
# Guidance:
# - Read the ENTIRE document and return the FINAL/EFFECTIVE amount actually PAID or IMPOSED (digits only).
# - If there are more than one fines to be paid give the final amount as the sum if the mentioned fines. For example "FIRST: TO IMPOSE on LÍNEA DIRECTA ASEGURADORA, S.A., INSURANCE AND REINSURANCE COMPANY, with NIF A80871031:  
# 1. For an infringement of article 6.1 of the GDPR, classified in article 83.5.a) of the GDPR, an administrative fine (article 58.2.i) in the amount of €100,000 (one hundred thousand euros)  
# 2. For an infringement of article 28 of the GDPR, classified in article 83.4.a) of the GDPR, an administrative fine (article 58.2.i) in the amount of €200,000 (two hundred thousand euros)  " here the total amount is "300000"
# - If multiple amounts exist (proposed, reduced, paid), prefer the final/paid amount.
# - Focus on the operative/final sections near the end.
# - If no fine or unclear, return "0". No comments, no extra keys."""
# FINE_ONLY_USER = """Document:
# ---
# {body}
# ---"""

# # ----------------- Article extraction -----------------
# # Instruments explicitly NOT GDPR (used to filter out false positives)
# NON_GDPR_TOKENS = [
#     # Spain / typical national laws
#     "LOPDGDD","LOPD 15/1999","Ley Orgánica 3/2018","Ley 39/2015","Ley 40/2015",
#     "LPACAP","Real Decreto","Royal Decree","RDL","RD",
#     # Germany/others
#     "BDSG","DSG","Telekommunikationsgesetz","Telemediengesetz","TTDSG",
#     # Other instruments (exclude)
#     "Directive","Directive 95/46/EC","Directive 2002/58/EC","ePrivacy",
#     "Regulation (EU) 2018/1725","eIDAS","NIS","DGA","DMA","DSA",
#     "ECHR","CEDH","Convention","Charter of Fundamental Rights","TFEU","TFUE",
#     "Civil Code","Criminal Code","Penal Code","Código","Code","Constitution"
# ]

# # Old/alternate ways the GDPR is referenced
# GDPR_ALIASES = [
#     "General Data Protection Regulation","Regulation (EU) 2016/679",
#     "EU Regulation 2016/679","RGPD","DSGVO","Règlement (UE) 2016/679",
#     "Règlement général sur la protection des données","RGPD de l’UE",
#     "Reglamento (UE) 2016/679","Reglamento General de Protección de Datos",
#     "Regolamento (UE) 2016/679","Regolamento generale sulla protezione dei dati",
#     "Datenschutz-Grundverordnung","GDPR"
# ]

# ARTICLES_ONLY_SYSTEM = f"""Return STRICT JSON ONLY with:
# {{"articles":"<comma-separated base GDPR article numbers only>"}}

# CRITICAL OBJECTIVE
# - Read the entire document like a human reviewer would.
# - Return ONLY those article NUMBERS (1–99) that are GDPR articles in context.
# - A mention MUST be treated as GDPR if:
#   * It explicitly names GDPR or any of its aliases ({'; '.join(GDPR_ALIASES)}), OR
#   * The legal/analysis context clearly concerns the GDPR even if "GDPR" isn't repeated (e.g., the decision is a GDPR enforcement action, sanctions under Article 83 with typical GDPR enumerations, corrective powers per Article 58, cross-border cooperation under Article 60), OR
#   * The text uses multilingual/short forms (“Art.”,“Artículo”,“Artikel”,“čl.”,“articolo”, etc.) that clearly refer to the GDPR in the surrounding sentence/section.

# INSTRUMENT DISAMBIGUATION (very important)
# - If the SAME sentence/clause ties an article number to a NON-GDPR instrument (e.g., “Article 20 of the LOPDGDD”; tokens include: {', '.join(NON_GDPR_TOKENS)}), then EXCLUDE that number for that occurrence.
# - If an article number appears in BOTH GDPR and non-GDPR contexts in different places, INCLUDE it (because at least one context is GDPR).
# - Never include recitals (“Recital 47”), titles, chapters, or sections without a concrete article.

# COUNT WHEN ANY OF THESE APPEAR
# - “Article N”, “Articles N1, N2, …”, “Art. N”, multilingual equivalents.
# - Subparts: “58(2)(b)”, “6(1)(f)”, dotted forms “6.1”, “58.2”.
# - Ranges: “12–13”, “12-13”.
# - Sanction/aggregation clauses: If “83(5)(a)” mentions “Articles 5, 6, 7, 9”, include 83 plus 5, 6, 7, 9.

# TRANSFORM
# - Reduce subparts to base: 58(2)(b) → 58; 6(1)(f) → 6; 6.1 → 6; 58.2 → 58.
# - Expand ranges: 12–13 → 12, 13.
# - Deduplicate and SORT ascending.

# OUTPUT
# - Only valid JSON with exactly key "articles" and a comma-separated list, e.g., "4, 5, 6".
# """

# ARTICLES_ONLY_USER = """Document:
# ---
# {body}
# ---"""

# SYSTEM_PROMPT = f"""You are a precise legal information extractor for GDPR enforcement documents.

# Return STRICT JSON ONLY (no markdown, no prose) with keys exactly:
# {{
#   "decision": "<one of {', '.join(DECISION_LABELS)}> ",
#   "fine": "0|<digits only>",
#   "controller": "<string or 'unknown'>",
#   "articles": "<comma-separated base GDPR article numbers only, e.g., '4, 5, 6'>"
# }}

# Rules for "decision":
# - Output exactly one of: {', '.join(DECISION_LABELS)}.
# - If the text states 'dismissed as unfounded', use 'dismissed'.
# - If unsure, output 'unknown'.

# Rules for "fine":
# - Return ONLY the digits of the amount (e.g., '74000', '20000').
# - Remove any currency symbols/words (€, euro, EUR, USD, pounds, etc.).
# - If multiple amounts appear (proposed vs. reduced vs. paid), return the FINAL/EFFECTIVE amount actually imposed or paid after reductions/early payment.
# - If no fine is imposed or unclear, return "0".

# Rules for "articles" (context-aware GDPR inference):
# - Use the Articles-Only rules provided to extract GDPR articles.
# - Accept explicit and contextually clear GDPR mentions (GDPR aliases, sanction clauses, corrective powers, cooperation mechanisms) even if 'GDPR' isn't repeated in the sentence.
# - EXCLUDE if the same sentence/clause ties the number to a non-GDPR instrument.
# - Reduce to base numbers, expand ranges, deduplicate, sort. No guessing beyond the evidence.

# Controller:
# - Return the controller(s) named or addressed by the decision (company/authority/person) WITHOUT truncation.
# - Prefer full legal names as they appear. If multiple, join with '; '.
# - If truly absent, return "unknown".

# General:
# - If a field is not present, use "unknown" for decision/controller and "0" for fine.
# - Output ONLY valid JSON with those exact keys and no trailing commas.
# """

# USER_PROMPT_TEMPLATE = """Extract the four fields from this legal decision text:

# ---
# {chunk}
# ---
# """

# def _strip_json(s: str) -> str:
#     s = s.strip()
#     s = re.sub(r"^```(?:json)?\s*", "", s)
#     s = re.sub(r"\s*```$", "", s)
#     return s.strip()

# # ========= normalize model's articles list (no document mining) =========
# def _normalize_articles_list_from_model(raw: str) -> List[str]:
#     """
#     Normalize the model's 'articles' field to base numbers 1..99.
#     """
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
#         # expand ranges like "5-7" or "5 to 7"
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
#         # base number, possibly with subparagraphs "6(1)(f)" or dotted "6.1"
#         m = re.match(r"^\s*(\d{1,2})", tok)
#         if m:
#             push(int(m.group(1)))
#     return out

# # ========= decision helpers =========
# DECISION_HEURISTICS = [
#     (re.compile(r"\bdismiss(ed|al)\s+as\s+unfounded\b", re.I), "dismissed"),
#     (re.compile(r"\b(application|complaint|appeal)\s+is\s+dismissed\b", re.I), "dismissed"),
#     (re.compile(r"\bdismiss(ed|al)\b", re.I), "dismissed"),
#     (re.compile(r"\bpending\s+dismissal\b", re.I), "pending dismissal"),
#     (re.compile(r"\bpending\b", re.I), "pending"),
#     (re.compile(r"\bupheld\b", re.I), "upheld"),
#     (re.compile(r"\brejected\b", re.I), "rejected"),
#     (re.compile(r"\binadmissible\b", re.I), "inadmissible"),
#     (re.compile(r"\bunfounded\b", re.I), "dismissed"),
#     (re.compile(r"\bno\s+violation\b", re.I), "no violation"),
#     (re.compile(r"\breprimand\b", re.I), "reprimand"),
#     (re.compile(r"\bwarning\b", re.I), "warning"),
#     (re.compile(r"\badministrative\s+fine\b", re.I), "administrative fine"),
#     (re.compile(r"\bpartially\s+upheld\b", re.I), "partially upheld"),
#     (re.compile(r"\binfringement\b", re.I), "infringement"),
#     (re.compile(r"\bnotice\b", re.I), "notice"),
#     (re.compile(r"\badministrative\s+penalty\s+fine\b", re.I), "administrative penalty fine"),
#     (re.compile(r"\badministrative\s+fines\b", re.I), "administrative fine"),
#     (re.compile(r"\badministrative\s+sanction\s+fee\b", re.I), "administrative sanction fine"),
#     (re.compile(r"\bno\s+infraction\b", re.I), "no infraction"),
#     (re.compile(r"\binstructions?\b", re.I), "instructions"),
#     (re.compile(r"\bfile\s+the\s+procedure\b", re.I), "file the procedure"),
#     (re.compile(r"\bcriticism\b", re.I), "criticism"),
#     (re.compile(r"\bserious\s+criticism\b", re.I), "serious criticism"),
#     (re.compile(r"\bclosed\b", re.I), "closed"),
#     (re.compile(r"\bdiscontinue\s+the\s+action\b", re.I), "discontinue the action"),
#     (re.compile(r"\bin\s+accordance\s+with\s+the\s+rules\b", re.I), "in accordance with the rules"),
#     (re.compile(r"\bnotify\s+an\s+order\b", re.I), "notify an order"),
#     (re.compile(r"\bgroundless\b", re.I), "groundless"),
#     (re.compile(r"\bgives\s+an\s+order\b", re.I), "gives an order"),
#     (re.compile(r"\brejecting\s+the\s+application\b", re.I), "rejecting the application"),
#     (re.compile(r"\bofficial\s+warning\b", re.I), "official warning"),
#     (re.compile(r"\bcondemns\b", re.I), "condemns"),
#     (re.compile(r"\bbaseless\s+and\s+unproven\b", re.I), "baseless and unproven"),
#     (re.compile(r"\btermination\s+of\s+procedure\b", re.I), "termination of procedure"),
#     (re.compile(r"\bpartially\s+granting\s+the\s+request\b", re.I), "partially granting the request"),
#     (re.compile(r"\bviolation\s+of\s+the\s+law\b", re.I), "violition of the law"),
#     (re.compile(r"\bexpressed\s+serious\s+criticism\b", re.I), "expressed serious criticism"),
#     (re.compile(r"\border\s+the\s+file\b", re.I), "ORDER THE FILE"),
#     (re.compile(r"\breprimand\s+and\s+injunction\b", re.I), "reprimand and injunction"),
#     (re.compile(r"\bpartial\s+violation\b", re.I), "partial violation"),
#     (re.compile(r"\badmonish\b", re.I), "admonish"),
#     (re.compile(r"\baddress\b", re.I), "Address"),
#     (re.compile(r"\bcomplete\s+assessment\b", re.I), "complete assessment"),
#     (re.compile(r"\bimpose\s+corrective\s+measures\b", re.I), "impose corrective measures"),
#     (re.compile(r"\bre\-assess\s+the\s+fine\b", re.I), "re-assess the fine"),
#     (re.compile(r"\bissues\s+a\s+reminder\b", re.I), "issues a reminder"),
#     (re.compile(r"\breject\s+the\s+cassation\s+appeal\b", re.I), "reject the cassation appeal"),
#     (re.compile(r"\bviolated\s+gdpr\b", re.I), "violated GDPR"),
#     (re.compile(r"\bmonetary\s+penalties\b", re.I), "monetary penalties"),
#     (re.compile(r"\billegality\s+of\s+data\s+protection\b", re.I), "illegality of data protection"),
#     (re.compile(r"\bchange\s+the\s+fine\s+amount\b", re.I), "change the fine amount"),
#     (re.compile(r"\bsatisfy\s+injunction\b", re.I), "satisfy injunction"),
#     (re.compile(r"\blacks\s+the\s+competence\s+to\s+examine\s+the\s+complaint\b", re.I), "lacks the competence to examine the complaint"),
#     (re.compile(r"\bremains\s+in\s+force\b", re.I), "remains in force"),
#     (re.compile(r"\benforcement\s+notices\b", re.I), "enforcement notices"),
#     (re.compile(r"\bpartially\s+condemns\b", re.I), "partially condemns"),
#     (re.compile(r"\bneed\s+appropriate\s+corrective\s+measure\s+and\s+review\s+later\b", re.I), "need appropriate corrective measure and review later"),
#     (re.compile(r"\bprohibition\s+of\s+the\s+processing\b", re.I), "prohibition of the processing"),
#     (re.compile(r"\bstrictly\s+reprimand\b", re.I), "strictly reprimand"),
#     (re.compile(r"\bdid\s+not\s+comply\s+with\s+gdpr\b", re.I), "did not comply with GDPR"),
#     (re.compile(r"\bwithout\s+legal\s+basis\b", re.I), "without legal basis"),
#     (re.compile(r"\bdiscontinues\s+the\s+proceedings\b", re.I), "discontinues the proceedings"),
#     (re.compile(r"\bnotify\s+the\s+data\s+breach\b", re.I), "notify the data breach"),
#     (re.compile(r"\bdelete\s+the\s+personal\s+data\b", re.I), "delete the personal data"),
#     (re.compile(r"\baddress\s+the\s+data\s+breach\b", re.I), "address the data breach"),
#     (re.compile(r"\billegal\s+data\s+processing\b", re.I), "illegal data processing"),
#     (re.compile(r"\bunlawful\s+processing\b", re.I), "unlawful processing"),
#     (re.compile(r"\bunjustified\s+delay\b", re.I), "unjustified delay"),
#     (re.compile(r"\bfulfill\s+obligations\b", re.I), "fulfill obligations"),
#     (re.compile(r"\bprovide\s+the\s+personal\s+data\b", re.I), "provide the personal data"),
#     (re.compile(r"\breformulates\s+corrective\s+action\b", re.I), "reformulates corrective action"),
#     (re.compile(r"\bpartial\s+illegal\s+data\s+processing\b", re.I), "partial illegal data processing"),
#     (re.compile(r"\bhas\s+not\s+complied\b", re.I), "has not complied"),
#     (re.compile(r"\bfulfill\s+obligations\s+and\s+delete\s+the\s+personal\s+data\b", re.I), "fulfill obligations and delete the personal data"),
#     (re.compile(r"\bapplication\s+approved\b", re.I), "application approved"),
#     (re.compile(r"\bofficial\s+examination\b", re.I), "official examination"),
#     (re.compile(r"\brefused\b", re.I), "refused"),
#     (re.compile(r"\bunlawful\b", re.I), "unlawful"),
#     (re.compile(r"\bannounces\s+a\s+complaint\b", re.I), "announces a complaint"),
#     (re.compile(r"\bfinding\s+of\s+abuse\b", re.I), "finding of abuse"),
#     (re.compile(r"\bgrounds\s+for\s+issuing\s+an\s+order\s+to\s+notify\s+of\s+breach\b", re.I), "grounds for issuing an order to notify of breach"),
#     (re.compile(r"\breprimand\s+and\s+instruction\b", re.I), "reprimand and instruction"),
#     (re.compile(r"\bimposed\s+a\s+corrective\s+measure\b", re.I), "imposed a corrective measure"),
# ]

# def infer_decision_from_text(text: str) -> str:
#     if not text:
#         return ""
#     norm = text.replace("\r", "")
#     lines = norm.split("\n")
#     for i, line in enumerate(lines):
#         if re.search(r"\bdecision\b", line, re.I):
#             window = " ".join([line] + lines[i + 1 : i + 4])[:600]
#             for rx, label in DECISION_HEURISTICS:
#                 if rx.search(window):
#                     return label
#     for m in re.finditer(r"(?i)\bdecision\b.{0,300}", norm, re.S):
#         seg = m.group(0)
#         for rx, label in DECISION_HEURISTICS:
#             if rx.search(seg):
#                 return label
#     return ""

# def llm_decide_final_decision(text: str, retries: int = 3, backoff: float = 2.0) -> str:
#     """Single whole-document pass to choose the final operative decision label."""
#     body = text[:180000]
#     last_err = None
#     _bo = backoff
#     for _ in range(retries):
#         try:
#             resp = _chat_complete(
#                 model=MODEL_NAME,
#                 messages=[
#                     {"role": "system", "content": DECISION_ONLY_SYSTEM},
#                     {"role": "user", "content": DECISION_ONLY_USER.format(body=body)},
#                 ],
#             )
#             raw = resp.choices[0].message.content or "{}"
#             data = json.loads(_strip_json(raw))
#             dec = (data.get("decision") or "unknown").strip()
#             return dec if dec else "unknown"
#         except Exception as e:
#             last_err = e
#             time.sleep(min(_bo, 16))
#             _bo *= 2
#     if last_err:
#         print(f"[warn] whole-document decision failed: {last_err}", file=sys.stderr)
#     return "unknown"

# def llm_decide_final_fine(text: str, retries: int = 3, backoff: float = 2.0) -> str:
#     """Whole-document pass to return the FINAL/PAID fine (digits only)."""
#     body = text[:180000]
#     last_err = None
#     _bo = backoff
#     for _ in range(retries):
#         try:
#             resp = _chat_complete(
#                 model=MODEL_NAME,
#                 messages=[
#                     {"role": "system", "content": FINE_ONLY_SYSTEM},
#                     {"role": "user", "content": FINE_ONLY_USER.format(body=body)},
#                 ],
#             )
#             raw = resp.choices[0].message.content or "{}"
#             data = json.loads(_strip_json(raw))
#             fine = normalize_fine_to_digits((data.get("fine") or "0").strip())
#             return fine if fine else "0"
#         except Exception as e:
#             last_err = e
#             time.sleep(min(_bo, 16))
#             _bo *= 2
#     if last_err:
#         print(f"[warn] whole-document fine failed: {last_err}", file=sys.stderr)
#     return "0"

# def llm_decide_full_articles(text: str, retries: int = 3, backoff: float = 2.0) -> List[str]:
#     """
#     Whole-document pass for GDPR articles with context inference:
#     - Includes GDPR even when not explicitly repeated (uses aliases and enforcement context)
#     - Excludes explicit non-GDPR ties in the same sentence/clause
#     - Reduces to base numbers, expands ranges, dedupes, sorts
#     """
#     body = text[:180000]
#     last_err = None
#     _bo = backoff
#     for _ in range(retries):
#         try:
#             resp = _chat_complete(
#                 model=MODEL_NAME,
#                 messages=[
#                     {"role": "system", "content": ARTICLES_ONLY_SYSTEM},
#                     {"role": "user", "content": ARTICLES_ONLY_USER.format(body=body)},
#                 ],
#             )
#             raw = resp.choices[0].message.content or "{}"
#             data = json.loads(_strip_json(raw))
#             arts = _normalize_articles_list_from_model(str(data.get("articles", "")).strip())
#             return arts
#         except Exception as e:
#             last_err = e
#             time.sleep(min(_bo, 16))
#             _bo *= 2
#     if last_err:
#         print(f"[warn] whole-document articles failed: {last_err}", file=sys.stderr)
#     return []

# def _split_controllers(val: str) -> List[str]:
#     """
#     Split a controller field into a list of unique names, preserving order.
#     Accepts separators like ';' or ' and '.
#     Filters out empty/unknown.
#     """
#     if not val:
#         return []
#     s = val.strip()
#     s = s.replace(" and ", "; ")
#     parts = [p.strip() for p in s.split(";")]
#     seen, out = set(), []
#     for p in parts:
#         if not p or p.lower() == "unknown":
#             continue
#         if p not in seen:
#             seen.add(p)
#             out.append(p)
#     return out

# # ========= Fine normalization (digits-only) =========
# _NUM_RE = re.compile(r"(?:\d{1,3}(?:[.,]\d{3})+|\d+)")

# def normalize_fine_to_digits(fine: str) -> str:
#     """
#     Keep only digits of the numeric amount; drop currency/symbols/words.
#     '€ 74,000' -> '74000', '20.000 euros' -> '20000', 'EUR5000' -> '5000'
#     If no usable number is present, return '0'.
#     """
#     if not fine:
#         return "0"
#     m = _NUM_RE.search(fine)
#     if not m:
#         return "0"
#     digits_only = re.sub(r"[^\d]", "", m.group(0))
#     return digits_only if digits_only else "0"

# # ========= OpenAI extraction (union across chunks) =========
# def llm_extract_fields(text: str, retries: int = 3, backoff: float = 2.0) -> Dict[str, str]:
#     """
#     Calls OpenAI on chunks and unions the results.
#     - decision: first non-'unknown'
#     - controller: keep only the primary (first) name
#     - fine: choose the SMALLEST non-zero digits-only amount (final/paid)
#     - articles: union of model-reported base numbers only (sorted at the end)
#     """
#     final = {
#         "decision": "unknown",
#         "fine": "0",
#         "controller": "unknown",
#         "articles": "",
#     }
#     seen_articles = set()
#     ordered_articles: List[str] = []
#     controllers_found: List[str] = []
#     best_fine_val: int | None = None

#     for chunk in chunks(text):
#         prompt = USER_PROMPT_TEMPLATE.format(chunk=chunk[:200000])
#         last_err = None
#         _bo = backoff
#         for _ in range(retries):
#             try:
#                 resp = _chat_complete(
#                     model=MODEL_NAME,
#                     messages=[
#                         {"role": "system", "content": SYSTEM_PROMPT},
#                         {"role": "user", "content": prompt},
#                     ],
#                 )
#                 raw = resp.choices[0].message.content or "{}"
#                 data = json.loads(_strip_json(raw))

#                 decision = str(data.get("decision", "unknown")).strip() or "unknown"
#                 if final["decision"] == "unknown" and decision.lower() != "unknown":
#                     final["decision"] = decision

#                 fine_raw = str(data.get("fine", "0")).strip() or "0"
#                 fine = normalize_fine_to_digits(fine_raw)
#                 if fine.isdigit():
#                     val = int(fine)
#                     if val > 0 and (best_fine_val is None or val < best_fine_val):
#                         best_fine_val = val
#                         final["fine"] = fine

#                 controller_val = str(data.get("controller", "unknown")).strip()
#                 for c in _split_controllers(controller_val):
#                     if c not in controllers_found:
#                         controllers_found.append(c)

#                 arts = _normalize_articles_list_from_model(
#                     str(data.get("articles", "")).strip()
#                 )
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
#     if controllers_found:
#         final["controller"] = controllers_found[0]
#     final["articles"] = ", ".join(sorted(ordered_articles, key=lambda x: int(x)))
#     return final

# def run_case_and_write(target: Path, is_file: bool) -> Dict[str, str]:
#     # Read document
#     text = load_text_from_file(target) if is_file else load_text_from_folder(target)
#     if not text.strip():
#         raise RuntimeError("No text content found (empty/failed read).")

#     # Extract (OpenAI only)
#     found = llm_extract_fields(text)

#     # Whole-document decision/fine confirmers
#     dec_full = llm_decide_final_decision(text)
#     if dec_full.lower() != "unknown":
#         found["decision"] = dec_full
#     elif not found["decision"] or found["decision"].strip().lower() == "unknown":
#         heur = infer_decision_from_text(text)
#         if heur:
#             found["decision"] = heur

#     fine_full = llm_decide_final_fine(text)
#     if fine_full != "0":
#         found["fine"] = fine_full

#     # Whole-document pass for articles using context-aware GDPR inference
#     full_articles = llm_decide_full_articles(text)
#     if full_articles:
#         existing = _normalize_articles_list_from_model(found.get("articles", ""))
#         merged = sorted(set(existing).union(full_articles), key=lambda x: int(x))
#         found["articles"] = ", ".join(merged)

#     # Ensure keys
#     for k in ("decision", "fine", "controller", "articles"):
#         if k not in found:
#             found[k] = (
#                 "unknown" if k in ("decision", "controller")
#                 else ("0" if k == "fine" else "")
#             )

#     # Write metadata.json (only if changed)
#     folder = target.parent if is_file else target
#     meta_path = folder / "metadata.json"
#     print(f"[path] metadata.json -> {meta_path}")
#     save_metadata_if_changed(meta_path, found)

#     return found

# # ========= CLI =========
# def main():
#     ap = argparse.ArgumentParser(
#         description="Use ONLY OpenAI to extract decision/fine/controller and GDPR-only base articles (context-aware, excludes non-GDPR ties; expands ranges; dedupe; sort)."
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