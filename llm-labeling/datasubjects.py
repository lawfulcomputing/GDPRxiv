#!/usr/bin/env python3
import csv
import os
import re
import json
import sys
from pathlib import Path
from typing import Optional, Set, Dict, Any
from datetime import datetime, timezone


# ================== Utilities ==================
def _die(msg: str, code: int = 2):
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(code)


def _read_pdf_text(pdf: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except Exception:
        return ""
    try:
        doc = fitz.open(str(pdf))
        txt = "\n".join(p.get_text("text") for p in doc)
        doc.close()
        return txt
    except Exception:
        return ""


def _read_en_text(folder: Path) -> str:
    p = folder / "en.txt"
    if p.exists():
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    p = folder / "en.pdf"
    if p.exists():
        return _read_pdf_text(p)
    return ""


def _load_metadata(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                return item
        return {}
    return {}


def _extract_country(folder: Path, repo_root: Path) -> str:
    try:
        rel = folder.relative_to(repo_root)
    except ValueError:
        return "unknown"
    parts = rel.parts
    if "documents" in parts:
        i = parts.index("documents")
        if i + 1 < len(parts):
            return parts[i + 1].lower()
    return "unknown"


def _is_gdpr_doc(meta: dict) -> bool:
    if isinstance(meta, list):
        return any(_is_gdpr_doc(m) for m in meta)
    if not isinstance(meta, dict):
        return False
    v = meta.get("document_type") or meta.get("documentType")
    return isinstance(v, str) and v.strip().upper() == "GDPR"

# def _load_case_paths_from_disagreements(csv_path: Path) -> Set[str]:
#     """
#     Read a disagreements CSV that has a 'case_path' column.
#     Returns a set of absolute, resolved folder paths.
#     """
#     if not csv_path.exists():
#         _die(f"Disagreements CSV not found: {csv_path}")

#     out: Set[str] = set()
#     with csv_path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
#         r = csv.DictReader(f)
#         if not r.fieldnames or "case_path" not in r.fieldnames:
#             _die(f"Disagreements CSV must contain a 'case_path' column: {csv_path}")
#         for row in r:
#             cp = (row.get("case_path") or "").strip()
#             if not cp:
#                 continue
#             out.add(str(Path(cp).expanduser().resolve()))
#     return out
# ================== Repo walker (GDPRxiv structure) ==================
def iter_case_folders(
    repo_root: Path,
    countries: Optional[Set[str]] = None,
    subplaces: Optional[Set[str]] = None,
):
    docs = repo_root / "documents"
    if not docs.exists():
        return

    wanted_countries = {c.lower() for c in countries} if countries else None
    wanted_subplaces = {s.lower() for s in subplaces} if subplaces else None

    for country_dir in docs.iterdir():
        if not country_dir.is_dir():
            continue

        country_name = country_dir.name.lower()
        if wanted_countries and country_name not in wanted_countries:
            continue

        # germany/<subplace>/<case>
        if country_name == "germany":
            for sub_dir in country_dir.iterdir():
                if not sub_dir.is_dir():
                    continue
                if wanted_subplaces and sub_dir.name.lower() not in wanted_subplaces:
                    continue
                for case_dir in sub_dir.iterdir():
                    if case_dir.is_dir():
                        yield case_dir
            continue

        # country/<section>/<case>
        for section in country_dir.iterdir():
            if not section.is_dir():
                continue
            for case_dir in section.iterdir():
                if case_dir.is_dir():
                    yield case_dir


# ================== Prompt ==================
SYSTEM_PROMPT = """
You extract structured metadata from GDPR enforcement and legal decision documents.

Instructions:

Return ONLY the number of natural persons whose personal data was involved in this specific case.

Strict rules:
- If the case is dismissed, rejected, annulled, discontinued, refused, closed, or unfounded, then return 0.
- If the document explicitly states the number of complainants, return that number unless a higher number is explicitly stated.
- Do NOT return years, dates, article numbers, case numbers, file numbers, reference numbers, decision numbers, docket numbers, or monetary amounts.
- Do NOT return company size, turnover, number of employees, or total customers unless explicitly stated as involved in the case.
- If multiple numbers appear, return ONLY the number explicitly referring to persons, individuals, customers, users, records, or data subjects involved in the case.
- If multiple distinct data subjects appear return the sum of those numbers.
- If a range is given (e.g., 500–700), return the upper bound.
- If approximate wording is used (e.g., “about 2,000”), return the integer value.
- Only Return "unspecified" only if natural persons were involved but the number cannot be determined from the document.



Output must contain only:
{
  "numDataSubjectsAffected": <integer OR "unspecified">
}
"""


# ================== JSON extraction ==================
def _extract_json_object(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()

    # Try parse whole thing first
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    return item
    except Exception:
        pass

    m_arr = re.search(r"\[[\s\S]*\]", raw)
    if m_arr:
        try:
            parsed = json.loads(m_arr.group(0))
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        return item
        except Exception:
            pass

    # Fallback: first object in text
    m_obj = re.search(r"\{[\s\S]*\}", raw)
    if m_obj:
        try:
            parsed = json.loads(m_obj.group(0))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    return {"raw_output": raw}


def _normalize_output(obj: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        _die("Model did not return a JSON object.")

    # if "numDataSubjectsAffected" not in obj or obj["numDataSubjectsAffected"] is None:
    #     return {"numDataSubjectsAffected": 0}

    return obj



# ================== LLM backends ==================
def _require_openai():
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        _die("OPENAI_API_KEY is not set.")
    try:
        from openai import OpenAI
    except Exception:
        _die("OpenAI SDK not installed. Run: pip install openai")
    return OpenAI(api_key=key)


def _require_grok():
    key = os.getenv("XAI_API_KEY", "").strip()
    if not key:
        _die("XAI_API_KEY is not set.")
    try:
        from openai import OpenAI
    except Exception:
        _die("OpenAI SDK not installed. Run: pip install openai")
    return OpenAI(api_key=key, base_url="https://api.x.ai/v1")


def _require_gemini():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        _die("GEMINI_API_KEY is not set.")
    try:
        from google import genai
    except Exception:
        _die("Gemini SDK not installed. Run: pip install google-genai")
    return genai.Client(api_key=key)


def extract_metadata(text: str, backend: str) -> Dict[str, Any]:
    backend = (backend or "").lower()
    user = f"Document:\n---\n{text[:180000]}\n---"

    if backend == "openai":
        client = _require_openai()
        model = os.getenv("OPENAI_MODEL", "gpt-5").strip()
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as e:
            _die(f"OpenAI call failed: {e}")
        raw = (r.choices[0].message.content or "").strip()
        return _normalize_output(_extract_json_object(raw))

    if backend == "grok":
        client = _require_grok()
        model = os.getenv("GROK_MODEL", "grok-4-1-fast-reasoning").strip()
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as e:
            _die(f"Grok call failed: {e}")
        raw = (r.choices[0].message.content or "").strip()
        return _normalize_output(_extract_json_object(raw))

    if backend == "gemini":
        client = _require_gemini()
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()
        try:
            from google.genai import types
            resp = client.models.generate_content(
                model=model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0,
                    response_mime_type="application/json",
                    candidate_count=1,
                ),
            )
        except Exception as e:
            _die(f"Gemini call failed: {e}")

        raw = (getattr(resp, "text", None) or "").strip()
        return _normalize_output(_extract_json_object(raw))


    _die(f"Unknown backend: {backend}. Use openai|grok|gemini")
    return {}


# ================== CSV logic ==================
CSV_COLUMNS = [
    "timestamp_utc",
    "model",
    "country",
    "case_path",
    "numDataSubjectsAffected",
]


def _csv_path(repo_root: Path, backend: str, model_name: str) -> Path:
    safe_model = re.sub(r"[^a-zA-Z0-9._-]+", "_", model_name)
    out_dir = repo_root / "llm-labeling" / "extracted_metadata" / backend / safe_model
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "metadata_num_data_subject_updated.csv"


def _load_processed_cases(csv_path: Path) -> Set[str]:
    processed: Set[str] = set()
    if not csv_path.exists():
        return processed
    with csv_path.open("r", encoding="utf-8", errors="ignore") as f:
        r = csv.DictReader(f)
        for row in r:
            cp = (row.get("case_path") or "").strip()
            if cp:
                # processed.add(cp)
                processed.add(str(Path(cp).expanduser().resolve()))
    return processed


def _append_metadata_row(
    csv_path: Path,
    *,
    model_name: str,
    country: str,
    case_path: Path,
    obj: Dict[str, Any],
):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    row = {
        "timestamp_utc": ts,
        "model": model_name,
        "country": country,
        "case_path": str(case_path),
        "numDataSubjectsAffected": str(obj.get("numDataSubjectsAffected", 0)),
    }

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            w.writeheader()
        w.writerow(row)


# ================== Main processing ==================
def run_metadata_repo(
    repo_root: Path,
    *,
    backend: str,
    countries: Optional[Set[str]] = None,
    subplaces: Optional[Set[str]] = None,
    # disagreements_csv: Path,
):
    backend = (backend or "").lower()
    if backend == "openai":
        model_name = os.getenv("OPENAI_MODEL", "gpt-5").strip()
    elif backend == "grok":
        model_name = os.getenv("GROK_MODEL", "grok-4-1-fast-reasoning").strip()
    elif backend == "gemini":
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()
    else:
        _die("backend must be one of: openai, grok, gemini")

    out_csv = _csv_path(repo_root, backend, model_name)
    processed = _load_processed_cases(out_csv)
    # selected_cases = _load_case_paths_from_disagreements(disagreements_csv)
    eligible = 0
    written = 0
    skipped_non_gdpr = 0

    for case in iter_case_folders(repo_root, countries=countries, subplaces=subplaces):
        meta = _load_metadata(case / "metadata.json")
        if not meta:
            continue

        if not _is_gdpr_doc(meta):
            skipped_non_gdpr += 1
            continue

        if not ((case / "en.txt").exists() or (case / "en.pdf").exists()):
            continue

        eligible += 1
        if str(case) in processed:
            continue

        text = _read_en_text(case)
        if not text.strip():
            print(f"[skip: no text] {case}", file=sys.stderr)
            continue

        ctry = _extract_country(case, repo_root)

        try:
            obj = extract_metadata(text, backend=backend)
            _append_metadata_row(
                out_csv,
                model_name=model_name,
                country=ctry,
                case_path=case,
                obj=obj,
            )
            written += 1
            print(f"[{ctry}] wrote → {case}")
        except SystemExit:
            raise
        except Exception as e:
            print(f"[warn] Failed {case}: {e}", file=sys.stderr)
            continue
    # for cp in sorted(selected_cases):
    #     case = Path(cp)

    #     if not case.exists() or not case.is_dir():
    #         print(f"[skip: missing dir] {case}", file=sys.stderr)
    #         continue

    #     # require en.pdf/en.txt under the case path
    #     if not ((case / "en.pdf").exists() or (case / "en.txt").exists()):
    #         print(f"[skip: missing en.pdf/en.txt] {case}", file=sys.stderr)
    #         continue

    #     meta = _load_metadata(case / "metadata.json")
    #     if not meta:
    #         continue

    #     if not _is_gdpr_doc(meta):
    #         skipped_non_gdpr += 1
    #         continue

    #     eligible += 1
    #     if str(case) in processed:
    #         continue

    #     text = _read_en_text(case)
    #     if not text.strip():
    #         print(f"[skip: no text] {case}", file=sys.stderr)
    #         continue

    #     ctry = _extract_country(case, repo_root)

    #     try:
    #         obj = extract_metadata(text, backend=backend)
    #         _append_metadata_row(
    #             out_csv,
    #             model_name=model_name,
    #             country=ctry,
    #             case_path=case,
    #             obj=obj,
    #         )
    #         written += 1
    #         print(f"[{ctry}] wrote → {case}")
    #     except SystemExit:
    #         raise
    #     except Exception as e:
    #         print(f"[warn] Failed {case}: {e}", file=sys.stderr)
    #         continue


    print("\nDONE")
    print(f"  eligible_seen={eligible}")
    print(f"  rows_written={written}")
    print(f"  skipped_non_gdpr={skipped_non_gdpr}")
    print(f"  out_csv={out_csv}")


# ================== CLI ==================
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Extract numDataSubjectsAffected only (GDPR-only).")
    ap.add_argument("--repo", type=Path, required=True, help="Repo root containing /documents")
    ap.add_argument("--backend", required=True, choices=["openai", "grok", "gemini"], help="LLM backend to use")
    ap.add_argument("--country", action="append", help="Limit to country folder(s) under /documents")
    ap.add_argument("--subplace", action="append", help="Limit germany sub-place(s) under /documents/germany")
    # ap.add_argument(
    #     "--disagreements-csv",
    #     type=Path,
    #     required=True,
    #     help="CSV in disagreements folder that contains a 'case_path' column",
    # )
    args = ap.parse_args()

    countries = set(args.country) if args.country else None
    subplaces = set(args.subplace) if args.subplace else None

    run_metadata_repo(args.repo.resolve(), backend=args.backend, countries=countries, subplaces=subplaces)
    # run_metadata_repo(
    #     args.repo.resolve(),
    #     backend=args.backend,
    #     disagreements_csv=args.disagreements_csv.resolve(),
    # )

