#!/usr/bin/env python3
"""
documenttype.py
---------------------------------
- Walks the repo (using SECTION_ALLOWLIST / DECISION_LIKE_SECTIONS)
- For each case folder:
    1) Reads en.txt (preferred) or en.pdf
    2) If metadata.json lacks 'documentType', determines GDPR / non-GDPR
- Can also run on a specific single file or folder
- Uses OpenAI if OPENAI_API_KEY is set
"""

import csv
import os, re, json, sys, random
from pathlib import Path
from typing import Optional, Set, Dict, Tuple
from datetime import datetime, timezone


GITHUB_BASE = "https://github.com/lawfulcomputing/GDPRxiv/blob/revert_metadata_update/"
# ================== Section filters ==================
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
    txt = folder / "en.txt"
    if txt.exists():
        try:
            data = txt.read_text(encoding="utf-8", errors="ignore")
            if data.strip():
                return data
        except Exception:
            pass
    pdf = folder / "en.pdf"
    if pdf.exists():
        return _read_pdf_text(pdf)
    return ""


def _load_metadata(meta_path: Path) -> dict:
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_metadata(meta_path: Path, meta: dict):
    try:
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as e:
        _die(f"Failed to write {meta_path}: {e}")

def _progress_path(repo_root: Path, mode: str) -> Path:
    """
    mode: "scan" for run_repo_scan, "verify" for verify_random_sample
    """
    return repo_root / f".progress_{mode}.txt"


def _load_progress(repo_root: Path, mode: str) -> Set[str]:
    p = _progress_path(repo_root, mode)
    if not p.exists():
        return set()
    return {
        line.strip()
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip()
    }


def _save_progress(repo_root: Path, mode: str, visited: Set[str]):
    """
    Overwrites the progress file each time.
    """
    p = _progress_path(repo_root, mode)
    p.write_text("\n".join(sorted(visited)) + "\n", encoding="utf-8")


def _mark_visited(repo_root: Path, mode: str, visited: Set[str], case_path: Path):
    visited.add(str(case_path))
    _save_progress(repo_root, mode, visited)


def _github_link_for_case(folder: Path, repo_root: Path) -> Optional[str]: 
    """
    Build a GitHub URL for this case, pointing to en.pdf if present,
    otherwise en.txt. Uses the revert_metadata_update branch.
    Example:
    /Users/venya/Desktop/GDPRxiv/documents/spain/Decisions/5567... → 
    https://github.com/lawfulcomputing/GDPRxiv/blob/revert_metadata_update/documents/spain/Decisions/5567.../en.pdf
    """
    try:
        rel_case = folder.relative_to(repo_root)
    except ValueError:
        # folder not under repo_root
        return None

    # Prefer en.pdf, fall back to en.txt
    ext = None
    if (folder / "en.pdf").exists():
        ext = "en.pdf"
    elif (folder / "en.txt").exists():
        ext = "en.txt"
    else:
        return None

    rel_path = (rel_case / ext).as_posix()
    return GITHUB_BASE + rel_path

# ================== OpenAI + heuristic classifiers ==================
# def _require_watsonx_client():
#     """
#     Requires:
#       - WATSONX_AI_URL
#       - WATSONX_AI_APIKEY
#       - WATSONX_PROJECT_ID (or WATSONX_SPACE_ID, but project is typical)
#     Optional:
#       - WATSONX_MODEL_ID (default below)
#     """
#     url = os.getenv("WATSONX_AI_URL", "").strip()
#     api_key = os.getenv("WATSONX_AI_APIKEY", "").strip()
#     project_id = os.getenv("WATSONX_PROJECT_ID", "").strip()
#     space_id = os.getenv("WATSONX_SPACE_ID", "").strip()

#     if not url or not api_key:
#         _die("Missing WATSONX_AI_URL or WATSONX_AI_APIKEY in environment.")
#     if not project_id and not space_id:
#         _die("Missing WATSONX_PROJECT_ID (or WATSONX_SPACE_ID) in environment.")

#     try:
#         from ibm_watsonx_ai import APIClient, Credentials
#     except Exception:
#         _die("IBM watsonx.ai SDK not installed. Run: pip install ibm-watsonx-ai")

#     credentials = Credentials(url=url, api_key=api_key)
#     client = APIClient(credentials)

#     return client, project_id or None, space_id or None
# ================== Grok (xAI) classifier ==================
# def _require_grok_client():
#     """
#     Grok (xAI) is OpenAI-compatible. Use OpenAI SDK with base_url=https://api.x.ai/v1
#     Env:
#       - XAI_API_KEY (required)
#       - GROK_MODEL  (optional; default below)
#     """
#     api_key = os.getenv("XAI_API_KEY", "").strip()
#     if not api_key:
#         _die("XAI_API_KEY is not set. Export it and try again.")

#     try:
#         from openai import OpenAI
#     except Exception:
#         _die("OpenAI SDK not installed. Run: pip install openai")

#     return OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
def _require_gemini_client():
    """
    Gemini (Google) client.
    Env:
      - GEMINI_API_KEY 
      - GEMINI_MODEL   
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        _die("GEMINI_API_KEY is not set. Export it and try again.")

    try:
        from google import genai
    except Exception:
        _die("Gemini SDK not installed. Run: pip install google-genai")

    return genai.Client(api_key=api_key)



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

# def _require_openai_client():
#     api_key = os.getenv("OPENAI_API_KEY", "").strip()
#     if not api_key:
#         _die("OPENAI_API_KEY is not set. Export it and try again.")
#     try:
#         from openai import OpenAI
#     except Exception:
#         _die("OpenAI SDK not installed. Run: pip install openai")
#     return OpenAI(api_key=api_key)
def _classify_with_gemini(text: str) -> str:
    client = _require_gemini_client()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()

    system = (
        "You will be given a legal document or legal decision. Your task is to classify it as GDPR only when "
        "provisions of Regulation (EU) 2016/679 (GDPR) are directly relied upon to determine, justify, or influence "
        "the outcome (for example: an explicit finding/allegation of breach or non-compliance with GDPR articles; "
        "GDPR provisions used as the legal basis of reasoning; a fine/sanction/corrective measure imposed pursuant "
        "to GDPR; or explicit language that the outcome is because of/pursuant to/in accordance with GDPR). Treat "
        "GDPR synonyms and equivalents (GDPR, Regulation (EU) 2016/679, DSGVO, RGPD, RODO, and formulations like "
        "'Article X of GDPR/DSGVO/RGPD/RODO') as GDPR references. Classify as non-GDPR when GDPR appears only "
        "incidentally (background, boilerplate competence/jurisdiction, citation lists) or is not applied in the "
        "legal reasoning/operative part. If GDPR relevance is unclear or marginal, default to non-GDPR. "
        'Return STRICT JSON only: {"documentType":"GDPR"} or {"documentType":"non-GDPR"}.'
    )

    user = f"Document:\n---\n{text[:180000]}\n---"

    try:
        from google.genai import types

        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0,
                response_mime_type="application/json",
            ),
        )


    except Exception as e:
        _die(f"Gemini call failed: {e}")

    raw = (getattr(resp, "text", None) or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)

    try:
        val = str(json.loads(raw).get("documentType", "")).strip()
    except Exception:
        _die(f"Gemini did not return valid JSON. Got:\n{raw[:500]}")

    if val not in ("GDPR", "non-GDPR"):
        _die('Gemini JSON missing/invalid "documentType" (expected "GDPR" or "non-GDPR").')

    return val
# def _classify_with_grok(text: str) -> str:
#     client = _require_grok_client()
#     model = os.getenv("GROK_MODEL", "grok-4-1-fast-reasoning").strip()

#     system = (
#         "You will be given a legal document or legal decision. Your task is to classify it as GDPR only when "
#         "provisions of Regulation (EU) 2016/679 (GDPR) are directly relied upon to determine, justify, or influence "
#         "the outcome (for example: an explicit finding/allegation of breach or non-compliance with GDPR articles; "
#         "GDPR provisions used as the legal basis of reasoning; a fine/sanction/corrective measure imposed pursuant "
#         "to GDPR; or explicit language that the outcome is because of/pursuant to/in accordance with GDPR). Treat "
#         "GDPR synonyms and equivalents (GDPR, Regulation (EU) 2016/679, DSGVO, RGPD, RODO, and formulations like "
#         "'Article X of GDPR/DSGVO/RGPD/RODO') as GDPR references. Classify as non-GDPR when GDPR appears only "
#         "incidentally (background, boilerplate competence/jurisdiction, citation lists) or is not applied in the "
#         "legal reasoning/operative part. If GDPR relevance is unclear or marginal, default to non-GDPR. "
#         'Return STRICT JSON only: {"documentType":"GDPR"} or {"documentType":"non-GDPR"}.'
#     )

#     user = f"Document:\n---\n{text[:180000]}\n---"

#     try:
#         resp = client.chat.completions.create(
#             model=model,
#             messages=[
#                 {"role": "system", "content": system},
#                 {"role": "user", "content": user},
#             ],
#             temperature=0,
#         )
#     except Exception as e:
#         _die(f"Grok (xAI) call failed: {e}")

#     raw = (resp.choices[0].message.content or "").strip()
#     raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)

#     try:
#         val = str(json.loads(raw).get("documentType", "")).strip()
#     except Exception:
#         _die(f"Grok did not return valid JSON. Got:\n{raw[:500]}")

#     if val not in ("GDPR", "non-GDPR"):
#         _die('Grok JSON missing/invalid "documentType" (expected "GDPR" or "non-GDPR").')

#     return val
# def _classify_with_watsonx_granite(text: str) -> str:
#     """
#     Calls watsonx.ai with an IBM Granite instruct model and expects STRICT JSON:
#       {"documentType": "GDPR"} or {"documentType": "non-GDPR"}
#     """
#     client, project_id, space_id = _require_watsonx_client()

#     model_id = os.getenv("WATSONX_MODEL_ID", "ibm/granite-3-8b-instruct").strip()

#     try:
#         from ibm_watsonx_ai.foundation_models import ModelInference
#     except Exception:
#         _die("IBM watsonx.ai SDK missing foundation_models. Update: pip install -U ibm-watsonx-ai")

#     # system = (
#     #     "A GDPR document is one in which GDPR articles from Regulation (EU) 2016/679 "
#     #     "directly shape the outcome of the decision.\n"
#     #     "This means:\n"
#     #     "- A GDPR article is violated, OR\n"
#     #     "- GDPR articles directly influence the decision, sanction, fine, or corrective order, OR\n"
#     #     "- The document states something happened because of GDPR / due to a GDPR article / in accordance with GDPR.\n"
#     #     "A document is NOT a GDPR document when GDPR is mentioned only in passing or does not affect reasoning/outcome.\n"
#     #     "Also consider synonyms (DSGVO, RGPD, RODO, etc.).\n\n"
#     #     "Return STRICT JSON only:\n"
#     #     '{"documentType": "GDPR"}\n'
#     #     "or\n"
#     #     '{"documentType": "non-GDPR"}\n'
#     # )
#     system = (
#     "Classify a document as GDPR ONLY if one or more articles of Regulation (EU) 2016/679 "
#     "(referred to as GDPR, DSGVO, RGPD, RODO, or equivalent local names) are explicitly "
#     "found to be VIOLATED and those violated articles directly lead to the fine or decision.\n\n"
#     "In ALL other cases, classify as NON-GDPR.\n\n"
#     "Return STRICT JSON only:\n"
#     "{\"documentType\": \"GDPR\"}\n"
#     "or\n"
#     "{\"documentType\": \"non-GDPR\"}\n"
# )


#     prompt = f"{system}\nDocument:\n---\n{text[:20000]}\n---\n"

#     params = {
#         "max_new_tokens": 200,
#         "temperature": 0,
#     }

#     model = ModelInference(
#         model_id=model_id,
#         api_client=client,
#         project_id=project_id,
#         space_id=space_id,
#         params=params,
#     )

#     try:
#         raw = model.generate_text(prompt) 
#     except Exception as e:
#         _die(f"watsonx.ai call failed: {e}")

#     raw = (raw or "").strip()
#     raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)

#     try:
#         val = str(json.loads(raw).get("documentType", "")).strip()
#     except Exception:
#         _die(f"watsonx.ai did not return valid JSON. Got:\n{raw[:500]}")

#     if val not in ("GDPR", "non-GDPR"):
#         _die('watsonx.ai JSON missing/invalid "documentType" (expected "GDPR" or "non-GDPR").')

#     return val
# def _classify_with_openai(text: str) -> str:
#     client = _require_openai_client()
#     model = os.getenv("OPENAI_MODEL", "gpt-5")
# #     system = (
# #      "Classify a document as GDPR ONLY if one or more articles of Regulation (EU) 2016/679 "
# #      "(referred to as GDPR, DSGVO, RGPD, RODO, or equivalent local names) are explicitly "
# #     "found to be VIOLATED and those violated articles directly lead to the fine or decision.\n\n"     "In ALL other cases, classify as NON-GDPR.\n\n"
# #      "Return STRICT JSON only:\n"
# #      "{\"documentType\": \"GDPR\"}\n"
# #     "or\n"
# #     "{\"documentType\": \"non-GDPR\"}\n"
# #  )
# #     system = """
# # A GDPR document is one in which GDPR articles from Regulation (EU) 2016/679 directly shape the outcome of the decision.
# # This means:
# # A GDPR article is violated, OR GDPR articles directly influence the decision, sanction, fine, or corrective order, OR
# # The document states that something happened “because of GDPR,” “due to a GDPR article,” “in accordance with GDPR,” or similar wording that shows GDPR is the reason for the outcome.
# # A document is NOT a GDPR document when GDPR is mentioned only in passing or does not affect the reasoning or final decision.
# # Also consider synonyms of GDPR, and treat phrases like “Article X of GDPR/DSGVO/RGPD/RODO” as GDPR references.
# # Return STRICT JSON only:
# # {"documentType": "GDPR"}
# # or
# # {"documentType": "non-GDPR"}
# # """
# #     system = """
# #  "You will be prompted with a legal document or legal decision.\n\nYour goal is to determine whether the document is a GDPR document or a non-GDPR document.\n\nA document MUST be classified as a GDPR document if articles from Regulation (EU) 2016/679 (GDPR) directly determine, justify, or influence the outcome of the decision. This includes, but is not limited to, cases where:\n- The document explicitly states a violation of Article X of GDPR (e.g., \"violation of Article 6 of GDPR\").\n- A GDPR article is cited as violated, breached, infringed, or not complied with.\n- GDPR articles form the legal basis for a sanction, fine, corrective measure, or decision.\n- The outcome is justified using expressions such as \"because of GDPR\", \"due to a GDPR article\", \"in accordance with GDPR\", or equivalent wording.\n- GDPR is referenced using synonyms or equivalents, including GDPR, Regulation (EU) 2016/679, DSGVO, RGPD, or RODO.\n- References such as \"Article X of GDPR / DSGVO / RGPD / RODO\" count as GDPR references.\n\nA document MUST be classified as a non-GDPR document if:\n- GDPR is mentioned only incidentally or as background context.\n- GDPR does not influence the legal reasoning or the final outcome.\n\nDo NOT extract articles.\nDo NOT summarize the document.\n\nReturn STRICT JSON only. Do not include explanations or additional text.\n\nUse ONLY one of the following output formats:\n\n{\"documentType\": \"GDPR\"}\n\nOR\n\n{\"documentType\": \"non-GDPR\"}\n\nHere is the document to analyze:"
# # """
#     system = """ You will be given a legal document or legal decision. 
#     Your task is to determine whether it should be classified as a GDPR document or a non-GDPR document. 
#     A document must be classified as GDPR only when provisions of Regulation (EU) 2016/679 (the General Data Protection Regulation) are directly relied upon to determine, justify, or influence the outcome of the case. 
#     This includes situations where the decision finds or alleges a breach, infringement, or non-compliance with GDPR articles; applies GDPR provisions as the legal basis for the reasoning; 
#     imposes or upholds a fine, sanction, or corrective measure pursuant to GDPR (for example under Articles 58 or 83); or explicitly states that the outcome is reached because of, pursuant to, or in accordance with GDPR. 
#     References to GDPR synonyms and equivalents—such as GDPR, Regulation (EU) 2016/679, DSGVO, RGPD, RODO, or formulations like “Article X of GDPR/DSGVO/RGPD/RODO”—should be treated as GDPR references. 
#     A document must be classified as non-GDPR when GDPR is mentioned only incidentally, as background information, in boilerplate or competence sections, or alongside other laws without being applied to reach the decision, or when the legal reasoning and operative part are clearly based on non-GDPR legal regimes. 
#     In making this determination, focus primarily on the legal reasoning and the operative part of the decision rather than headings, citations lists, or introductory material. 
#     If the relevance of GDPR is unclear or marginal, default to non-GDPR unless there is explicit reliance on GDPR provisions to determine the outcome. Return strict JSON only, using exactly one of the following outputs:
# {"documentType": "GDPR"} or {"documentType": "non-GDPR"}. """


#     user = f"Document:\n---\n{text[:180000]}\n---"
#     try:
#         resp = client.chat.completions.create(
#             model=model,
#             messages=[
#                 {"role": "system", "content": system},
#                 {"role": "user", "content": user},
#             ],
#         )
#     except Exception as e:
#         _die(f"OpenAI call failed: {e}")
#     raw = (resp.choices[0].message.content or "").strip()
#     raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
#     try:
#         val = str(json.loads(raw).get("documentType", "")).strip()
#     except Exception:
#         _die("OpenAI did not return valid JSON.")
#     if val not in ("GDPR", "non-GDPR"):
#         _die(
#             'OpenAI JSON missing/invalid "documentType" (expected "GDPR" or "non-GDPR").'
#         )
#     return val


# ================== Core function ==================
def ensure_document_type(folder: Path) -> str:
    meta_path = folder / "metadata.json"
    meta = _load_metadata(meta_path)
    if meta.get("documentType"):
        return meta["documentType"]

    text = _read_en_text(folder)
    if not text.strip():
        _die(f"No text found in {folder} (need en.txt or en.pdf)")

    doc_type = _classify_with_gemini(text)
    meta["documentType"] = doc_type
    _save_metadata(meta_path, meta)
    return doc_type


def _country_results_csv(repo_root: Path, model_name: str, country: str) -> Path:
    safe_model = re.sub(r"[^a-zA-Z0-9._-]+", "_", model_name)
    out_dir = repo_root / "llmtraining" / "verification_results" / safe_model
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{country}.csv"


def _append_country_result_row(
    csv_path: Path,
    *,
    model_name: str,
    country: str,
    folder: Path,
    stored: str,
    fresh: str,
    github_url: Optional[str],
):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    status = "MATCH" if stored == fresh else "DIFF"

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow([
                "timestamp_utc",
                "model",
                "country",
                "case_path",
                "stored",
                "fresh",
                "status",
                "github_url",
            ])
        w.writerow([
            ts,
            model_name,
            country,
            str(folder),
            stored,
            fresh,
            status,
            github_url or "",
        ])


def _load_processed_cases_from_country_csv(csv_path: Path) -> Set[str]:
    processed: Set[str] = set()
    if not csv_path.exists():
        return processed
    with csv_path.open("r", encoding="utf-8", errors="ignore") as f:
        r = csv.DictReader(f)
        for row in r:
            p = (row.get("case_path") or "").strip()
            if p:
                processed.add(p)
    return processed


def _eligible_cases_by_country(
    repo_root: Path,
    *,
    only_decision_like: bool,
    countries: Optional[Set[str]] = None,
    subplaces: Optional[Set[str]] = None,
) -> Dict[str, Set[str]]:
    """
    Returns {country: {case_path_str, ...}} for eligible cases (have stored docType and text).
    """
    out: Dict[str, Set[str]] = {}
    for folder in _eligible_with_existing_doc_type(
        repo_root,
        only_decision_like=only_decision_like,
        countries=countries,
        subplaces=subplaces,
    ):
        c = _extract_country(folder, repo_root)
        out.setdefault(c, set()).add(str(folder))
    return out


def _compute_counts_from_country_csv(csv_path: Path) -> Dict[str, int]:
    """
    Treat stored as truth, GDPR as positive class.
    """
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    if not csv_path.exists():
        return counts

    with csv_path.open("r", encoding="utf-8", errors="ignore") as f:
        r = csv.DictReader(f)
        for row in r:
            stored = (row.get("stored") or "").strip()
            fresh = (row.get("fresh") or "").strip()
            if stored in ("GDPR", "non-GDPR") and fresh in ("GDPR", "non-GDPR"):
                _confusion_update(counts, stored, fresh)
    return counts


def _maybe_finalize_country_metrics(
    *,
    repo_root: Path,
    model_name: str,
    country: str,
    eligible_cases: Set[str],
):
    """
    If the country's results CSV contains all eligible cases, compute metrics
    and append exactly one row for that country+model into verification_metrics_by_country.csv.
    """
    results_csv = _country_results_csv(repo_root, model_name, country)
    processed = _load_processed_cases_from_country_csv(results_csv)

    if not eligible_cases:
        return  # nothing to do

    if len(processed) < len(eligible_cases):
        return  # not finished yet

    # Finished: compute metrics
    counts = _compute_counts_from_country_csv(results_csv)
    acc, prec, rec, n = _metrics_from_counts(counts)

    # Avoid duplicate "finalized" rows: write a marker file per country+model
    marker = results_csv.with_suffix(".finalized")
    if marker.exists():
        return

    metrics_csv = repo_root / "verification_metrics_by_country.csv"
    # sample_size = N for country-finalized runs
    append_single_country_metrics_row(
        metrics_csv,
        model_name=model_name,
        country=country,
        counts=counts,
        sample_size=n,
        seed=None,
    )

    marker.write_text(
        f"finalized_utc={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"country={country}\nmodel={model_name}\nN={n}\n"
        f"accuracy={acc}\nprecision={prec}\nrecall={rec}\n",
        encoding="utf-8",
    )
def append_single_country_metrics_row(
    csv_path: Path,
    *,
    model_name: str,
    country: str,
    counts: Dict[str, int],
    sample_size: int,
    seed: Optional[int],
):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    acc, prec, rec, n = _metrics_from_counts(counts)

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow([
                "run_id",
                "model",
                "sample_size",
                "seed",
                "scope",
                "N",
                "tp",
                "fp",
                "fn",
                "tn",
                "accuracy",
                "precision",
                "recall",
            ])

        w.writerow([
            run_id,
            model_name,
            sample_size,
            seed if seed is not None else "",
            country,
            n,
            counts["tp"],
            counts["fp"],
            counts["fn"],
            counts["tn"],
            round(acc, 6),
            round(prec, 6) if prec is not None else "",
            round(rec, 6) if rec is not None else "",
        ])


# ================== Repo walker ==================
def iter_case_folders(
    repo_root: Path, only_decision_like=True, countries: Optional[Set[str]] = None, subplaces: Optional[Set[str]] = None,
):
    docs_root = repo_root / "documents"
    if not docs_root.exists():
        return
    wanted_countries = {c.lower() for c in countries} if countries else None
    wanted_subplaces = {s.lower() for s in subplaces} if subplaces else None


    for country_dir in docs_root.iterdir():
        if not country_dir.is_dir():
            continue
        country_name = country_dir.name.lower()
        if wanted_countries and country_name not in wanted_countries:
            continue

        if country_name == "germany":
            for sub_dir in country_dir.iterdir():
                if not sub_dir.is_dir():
                    continue
                if wanted_subplaces and sub_dir.name.lower() not in wanted_subplaces:
                    continue

                # under each subplace we have case folders directly
                for case_dir in sub_dir.iterdir():
                    if case_dir.is_dir():
                        yield case_dir
            continue
        for section_dir in country_dir.iterdir():
            if not section_dir.is_dir():
                continue
            if only_decision_like and section_dir.name not in DECISION_LIKE_SECTIONS:
                continue
            if not only_decision_like and section_dir.name not in SECTION_ALLOWLIST:
                continue
            for case_dir in section_dir.iterdir():
                if case_dir.is_dir():
                    yield case_dir


def run_repo_scan(
    repo_root: Path, only_decision_like=True, countries: Optional[Set[str]] = None, subplaces: Optional[Set[str]] = None,
):
    visited = _load_progress(repo_root, "scan")
    total = processed = skipped = already_done = 0
    for case in iter_case_folders(
        repo_root, only_decision_like=only_decision_like, countries=countries, subplaces=subplaces,
    ):
        total += 1
        if str(case) in visited:
            already_done += 1
            continue
        if not ((case / "en.txt").exists() or (case / "en.pdf").exists()):
            skipped += 1
            _mark_visited(repo_root, "scan", visited, case)
            continue
        try:
            result = ensure_document_type(case)
            processed += 1
            print(f"{case} → {result}")
            _mark_visited(repo_root, "scan", visited, case)
        except SystemExit:
            # make sure we don't lose progress on hard exit
            _mark_visited(repo_root, "scan", visited, case)
            raise
        except Exception as e:
            print(f"[warn] Failed {case}: {e}", file=sys.stderr)
            # mark visited anyway (so rerun continues on unvisited only)
            _mark_visited(repo_root, "scan", visited, case)
        
    print(
        f"\nSummary: total={total}, processed={processed}, skipped={skipped}, already_done={already_done}"
    )
    print("Progress saved to:", _progress_path(repo_root, "scan"))

def _confusion_update(counts: Dict[str, int], truth: str, pred: str):
    if truth == "GDPR" and pred == "GDPR":
        counts["tp"] += 1
    elif truth == "non-GDPR" and pred == "GDPR":
        counts["fp"] += 1
    elif truth == "GDPR" and pred == "non-GDPR":
        counts["fn"] += 1
    elif truth == "non-GDPR" and pred == "non-GDPR":
        counts["tn"] += 1

def _metrics_from_counts(c: Dict[str, int]) -> Tuple[float, Optional[float], Optional[float], int]:
    tp, fp, fn, tn = c["tp"], c["fp"], c["fn"], c["tn"]
    n = tp + fp + fn + tn
    acc = (tp + tn) / n if n else 0.0
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    return acc, prec, rec, n

def _fmt(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return f"{x*100:.2f}%"

def _append_country_mismatch( repo_root: Path, country: str, stored: str, fresh: str, github_url: str,):
    """
    Save mismatches into country-wise text files under:
      repo_root/llmtraining/mismatch_groc/<country>/
        - existing_gdpr_classified_non_gdpr.txt
        - existing_non_gdpr_classified_gdpr.txt
    """
    out_dir = repo_root / "llmtraining" / "mismatch_gemini" / country
    out_dir.mkdir(parents=True, exist_ok=True)

    gdpr_to_non = out_dir / "existing_gdpr_classified_non_gdpr.txt"
    non_to_gdpr = out_dir / "existing_non_gdpr_classified_gdpr.txt"

    # Ensure headers exist once
    if not gdpr_to_non.exists():
        gdpr_to_non.write_text("Existing = GDPR but Classified = non-GDPR\n", encoding="utf-8")
    if not non_to_gdpr.exists():
        non_to_gdpr.write_text("Existing = non-GDPR but Classified = GDPR\n", encoding="utf-8")

    if stored == "GDPR" and fresh == "non-GDPR":
        with gdpr_to_non.open("a", encoding="utf-8") as f:
            f.write(github_url + "\n")
    elif stored == "non-GDPR" and fresh == "GDPR":
        with non_to_gdpr.open("a", encoding="utf-8") as f:
            f.write(github_url + "\n")

def append_country_metrics_csv(
    csv_path: Path,
    overall: Dict[str, int],
    by_country: Dict[str, Dict[str, int]],
    *,
    model_name: str,
    sample_size: int,
    seed: Optional[int],
):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)

        if not file_exists:
            w.writerow([
                "run_id",
                "model",
                "sample_size",
                "seed",
                "scope",  
                "N",
                "tp",
                "fp",
                "fn",
                "tn",
                "accuracy",
                "precision",
                "recall",
            ])

        # Overall row
        acc, prec, rec, n = _metrics_from_counts(overall)
        w.writerow([
            run_id,
            model_name,
            sample_size,
            seed if seed is not None else "",
            "overall",
            n,
            overall["tp"],
            overall["fp"],
            overall["fn"],
            overall["tn"],
            round(acc, 6),
            round(prec, 6) if prec is not None else "",
            round(rec, 6) if rec is not None else "",
        ])

        # Per-country rows
        for country, c in sorted(by_country.items()):
            acc, prec, rec, n = _metrics_from_counts(c)
            w.writerow([
                run_id,
                model_name,
                sample_size,
                seed if seed is not None else "",
                country,
                n,
                c["tp"],
                c["fp"],
                c["fn"],
                c["tn"],
                round(acc, 6),
                round(prec, 6) if prec is not None else "",
                round(rec, 6) if rec is not None else "",
            ])


# ================== Sampling verification ==================
def _eligible_with_existing_doc_type(
    repo_root: Path, only_decision_like=True, countries: Optional[Set[str]] = None,  subplaces: Optional[Set[str]] = None,
):
    for case in iter_case_folders(
        repo_root, only_decision_like=only_decision_like, countries=countries, subplaces=subplaces,
    ):
        if not ((case / "en.txt").exists() or (case / "en.pdf").exists()):
            continue
        meta = _load_metadata(case / "metadata.json")
        if isinstance(meta, dict) and meta.get("documentType") in ("GDPR", "non-GDPR"):
            yield case


def verify_random_sample(
    repo_root: Path,
    sample_size: int,
    only_decision_like: bool = True,
    seed: Optional[int] = None,
    countries: Optional[Set[str]] = None,
    subplaces: Optional[Set[str]] = None,
):
    if seed is not None:
        random.seed(seed)

    eligible = list(
        _eligible_with_existing_doc_type(
            repo_root, only_decision_like=only_decision_like, countries=countries ,
            subplaces=subplaces,
        )
    )
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()

    eligible_by_country = _eligible_cases_by_country(
        repo_root,
        only_decision_like=only_decision_like,
        countries=countries,
        subplaces=subplaces,
    )

    already_processed: Set[str] = set()
    for ctry in eligible_by_country.keys():
        c_csv = _country_results_csv(repo_root, model_name, ctry)
        already_processed |= _load_processed_cases_from_country_csv(c_csv)

    if not eligible:
        _die(
            "No eligible folders found with existing documentType and text "
            "in the selected scope."
        )
    
    eligible_not_done = [f for f in eligible if str(f) not in already_processed]


    if not eligible_not_done:
        print("All eligible folders in this scope have already been verified.")
        # still attempt finalize for any fully completed countries
        for ctry, cases in eligible_by_country.items():
            _maybe_finalize_country_metrics(
                repo_root=repo_root,
                model_name=model_name,
                country=ctry,
                eligible_cases=cases,
            )
        return 0, 0


    pick_n = min(sample_size, len(eligible_not_done))
    matches = 0
    overall = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    by_country: Dict[str, Dict[str, int]] = {}

    for folder in random.sample(eligible_not_done, k=pick_n):
        try:
            meta = _load_metadata(folder / "metadata.json")
            stored = meta.get("documentType")
            text = _read_en_text(folder)
            if not text.strip():
                print(f"[skip: no text] {folder}")
                continue
            
            fresh = _classify_with_gemini(text)
            status = "MATCH" if fresh == stored else "DIFF"
            if status == "MATCH":
                matches += 1

            country = _extract_country(folder, repo_root)
            if country not in by_country:
                by_country[country] = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}

            _confusion_update(overall, stored, fresh)
            _confusion_update(by_country[country], stored, fresh)

            github_url = _github_link_for_case(folder, repo_root)
            country_csv = _country_results_csv(repo_root, model_name, country)
            _append_country_result_row(
                country_csv,
                model_name=model_name,
                country=country,
                folder=folder,
                stored=stored,
                fresh=fresh,
                github_url=github_url,
            )

            # If this country is now fully processed, finalize metrics once
            _maybe_finalize_country_metrics(
                repo_root=repo_root,
                model_name=model_name,
                country=country,
                eligible_cases=eligible_by_country.get(country, set()),
            )


            if github_url:
                print(f"{folder} → stored={stored} fresh={fresh} [{status}] {github_url}")
            else:
                print(f"{folder} → stored={stored} fresh={fresh} [{status}]")

            if github_url and stored != fresh:
                _append_country_mismatch(
                    repo_root=repo_root,
                    country=country,
                    stored=stored,
                    fresh=fresh,
                    github_url=github_url,
                )
        except SystemExit:
            # ensure progress saved before exiting hard
            raise
        except Exception as e:
            print(f"[warn] Failed {folder}: {e}", file=sys.stderr)
            # Do NOT mark visited; allow retry on rerun
            continue

    
    print(f"\nVerification summary: matches={matches} out of {pick_n}")
    print("Progress saved to per-country CSVs under:")
    print("  →", repo_root / "llmtraining" / "verification_results")

    print("Country-wise mismatch lists saved under:")
    print("  →", repo_root / "llmtraining" / "mismatch_gemini")

    acc, prec, rec, n = _metrics_from_counts(overall)
    print("\nMetrics treating existing metadata as truth; GDPR is positive class :")
    print(f"  Overall: N={n}  accuracy={_fmt(acc)}  precision={_fmt(prec)}  recall={_fmt(rec)}")
    print("\n  Per-country:")
    for ctry in sorted(by_country.keys()):
        a, p, r, nn = _metrics_from_counts(by_country[ctry])
        print(f"    - {ctry}: N={nn}  accuracy={_fmt(a)}  precision={_fmt(p)}  recall={_fmt(r)}")
    metrics_csv = repo_root / "verification_metrics_by_country.csv"
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

    append_country_metrics_csv(
        metrics_csv,
        overall,
        by_country,
        model_name=model_name,
        sample_size=pick_n,
        seed=seed,
    )
    print("\nCountry-wise metrics CSV saved to:")
    print("  →", metrics_csv)
    return matches, pick_n



# ================== CLI ==================
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Assign or verify documentType=GDPR/non-GDPR for case folders/files."
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--repo", type=Path, help="Root folder of repository containing /documents"
    )
    g.add_argument("--dir", type=Path, help="Specific case folder with en.txt/en.pdf")
    g.add_argument("--file", type=Path, help="Specific .txt or .pdf file to classify")

    ap.add_argument(
        "--verify-sample",
        nargs="?",
        const=20,
        type=int,
        help="With --repo: randomly verify up to N existing documentType values (default 20).",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional RNG seed for reproducible sampling.",
    )

    ap.add_argument(
        "--country",
        action="append",
        help=(
            "Limit processing to specific country folder(s) under /documents "
            "(case-insensitive). Can be used multiple times."
        ),
    )
    
    ap.add_argument(
        "--subplace",
        action="append",
        help=(
            "For countries with nested sub-place folders (e.g. documents/germany/<subplace>/<case>), "
            "limit processing to specific sub-place folder(s). Can be used multiple times."
        ),
    )


    args = ap.parse_args()
    countries = set(args.country) if args.country else None
    subplaces = set(args.subplace) if args.subplace else None

    if args.repo and args.verify_sample:
        verify_random_sample(
            args.repo.resolve(),
            sample_size=args.verify_sample,
            seed=args.seed,
            countries=countries,
            subplaces=subplaces,
        )
    elif args.repo:
        run_repo_scan(args.repo.resolve(), countries=countries,subplaces=subplaces)
    elif args.dir:
        result = ensure_document_type(args.dir.resolve())
        print(f" Folder → {result or 'no text'}")
    elif args.file:
        fpath = args.file.resolve()
        folder = fpath.parent
        result = ensure_document_type(folder)
        print(f" File {fpath.name} → {result or 'no text'}")






# #!/usr/bin/env python3
# """
# documenttype.py
# ---------------------------------
# - Walks the repo (using SECTION_ALLOWLIST / DECISION_LIKE_SECTIONS)
# - For each case folder:
#     1) Reads en.txt (preferred) or en.pdf
#     2) If metadata.json lacks 'documentType', determines GDPR / non-GDPR
# - Can also run on a specific single file or folder
# - Uses OpenAI if OPENAI_API_KEY is set
# ---------------------------------
# """

# import os, re, json, sys
# from pathlib import Path

# # ================== Section filters ==================
# SECTION_ALLOWLIST = {
#     "Decisions",
#     "Decisions & judgements",
#     "decisions & judgments",
#     "Decisions & Reports",
#     "Decisions & Deliberations",
#     "Annual Reports",
#     "Reports",
#     "Decisions_2",
#     "AnnualReports",
# }

# DECISION_LIKE_SECTIONS = {
#     "Decisions",
#     "Decisions & judgements",
#     "decisions & judgments",
#     "Decisions & Reports",
#     "Decisions & Deliberations",
#     "Annual Reports",
#     "Reports",
#     "Decisions_2",
#     "AnnualReports",
# }

# # ================== Utilities ==================
# def _die(msg: str, code: int = 2):
#     print(f"[error] {msg}", file=sys.stderr)
#     sys.exit(code)

# def _read_pdf_text(pdf: Path) -> str:
#     try:
#         import fitz  # PyMuPDF
#     except Exception:
#         return ""
#     try:
#         doc = fitz.open(str(pdf))
#         txt = "\n".join(p.get_text("text") for p in doc)
#         doc.close()
#         return txt
#     except Exception:
#         return ""

# def _read_en_text(folder: Path) -> str:
#     txt = folder / "en.txt"
#     if txt.exists():
#         try:
#             data = txt.read_text(encoding="utf-8", errors="ignore")
#             if data.strip():
#                 return data
#         except Exception:
#             pass
#     pdf = folder / "en.pdf"
#     if pdf.exists():
#         return _read_pdf_text(pdf)
#     return ""

# def _load_metadata(meta_path: Path) -> dict:
#     if not meta_path.exists():
#         return {}
#     try:
#         return json.loads(meta_path.read_text(encoding="utf-8"))
#     except Exception:
#         return {}

# def _save_metadata(meta_path: Path, meta: dict):
#     try:
#         meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
#     except Exception as e:
#         _die(f"Failed to write {meta_path}: {e}")

# # ================== OpenAI + heuristic classifiers ==================

# def _require_openai_client():
#     api_key = os.getenv("OPENAI_API_KEY", "").strip()
#     if not api_key:
#         _die("OPENAI_API_KEY is not set. Export it and try again.")
#     try:
#         from openai import OpenAI
#     except Exception:
#         _die("OpenAI SDK not installed. Run: pip install openai")
#     return OpenAI(api_key=api_key)

# def _classify_with_openai(text: str) -> str | None:
#     client = _require_openai_client()
#     model = os.getenv("OPENAI_MODEL", "gpt-5")

#     system = (
#     'Return STRICT JSON only: {"documentType": "GDPR" | "non-GDPR"}\n'
#     "You are a LEGAL DOCUMENT CLASSIFIER for enforcement decisions.\n"
#     "Your task is to determine whether a decision falls under the EU General Data Protection Regulation (GDPR)\n"
#     "or another (non-GDPR) framework.\n"
#     "\n"
#     "You MUST base the classification on the LEGAL PROVISIONS THAT ACTUALLY GROUND THE FINE OR MAIN OPERATIVE RULING.\n"
#     "Carefully read the entire decision text (facts, legal assessment, and operative part), including any section\n"
#     "explicitly titled or functioning as \"Legal basis\", \"Legal bases\", \"Rechtsgrundlagen\", or similar, and identify\n"
#     "which articles/sections of law are used as the legal basis for the sanction, fine, or binding order.\n"
#     "\n"
#     "OUTPUT FORMAT (MANDATORY):\n"
#     "Return EXACTLY one of: {\"documentType\": \"GDPR\"} OR {\"documentType\": \"non-GDPR\"}\n"
#     "Do not add any other text, comments, or symbols.\n"
#     "\n"
#     "=== RECOGNIZING GDPR PROVISIONS AND SYNONYMS ===\n"
#     "Treat as GDPR any reference to Regulation (EU) 2016/679 or its local names/abbreviations, including for example:\n"
#     "- \"GDPR\" or \"General Data Protection Regulation\"\n"
#     "- \"Regulation (EU) 2016/679\"\n"
#     "- German: \"Datenschutz-Grundverordnung\", \"DSGVO\"\n"
#     "- Other language abbreviations such as \"RGPD\", \"RODO\", etc., when they clearly refer to Regulation (EU) 2016/679.\n"
#     "If a law is clearly described as the EU-wide general data protection regulation adopted as Regulation (EU) 2016/679,\n"
#     "treat it as GDPR even if only the local-language name or abbreviation is used.\n"
#     "\n"
#     "=== OPERATIVE LEGAL BASIS / FINE-FOCUSED CLASSIFICATION ===\n"
#     "Classify based ONLY on the provisions that actually contribute to the fine/sanction/operative decision:\n"
#     "\n"
#     "1) If one or more GDPR provisions (articles or recitals of the EU GDPR, including the above synonyms) contribute to\n"
#     "   the fine or binding decision (i.e., they are part of the operative legal basis, not just background discussion),\n"
#     "   then return {\"documentType\": \"GDPR\"}.\n"
#     "   - This includes cases where BOTH GDPR and other laws (e.g. national law, ePrivacy, sectoral law) contribute.\n"
#     "   - Example: a legal bases section such as \"§§ 22 para. 1 and 4 of the Data Protection Act (DSG) ...\n"
#     "     Art. 18, 51, 57, and 58 of the General Data Protection Regulation (GDPR) ... §§ 56, 57 para. 1 and 58 AVG ...\n"
#     "     Art. 52a, 53, and 138b B-VG ... § 25 VO-UA\" MUST be treated as GDPR contributing, because specific GDPR\n"
#     "     articles are part of the listed legal bases for the decision.\n"
#     "   - As soon as GDPR is part of the operative legal basis for the sanction, classify as \"GDPR\".\n"
#     "\n"
#     "2) If ONLY non-GDPR laws (national laws, other EU instruments, sectoral regulations, etc.) contribute to the\n"
#     "   fine or binding decision, and GDPR is NOT part of the operative legal basis, return\n"
#     "   {\"documentType\": \"non-GDPR\"}.\n"
#     "\n"
#     "3) If GDPR is mentioned only as background/context, high-level principles, or general references, but the actual\n"
#     "   fine/operative ruling is based solely on other laws, return {\"documentType\": \"non-GDPR\"}.\n"
#     "\n"
#     "=== DEFAULT ===\n"
#     "- If it is ambiguous or unclear whether GDPR provisions contribute to the fine / operative ruling, return\n"
#     "  {\"documentType\": \"non-GDPR\"}.\n"
# )


#     user = f"Document:\n---\n{text[:180000]}\n---"
#     try:
#         resp = client.chat.completions.create(
#             model=model,
#             messages=[
#                 {"role": "system", "content": system},
#                 {"role": "user", "content": user},
#             ],
#         )
#     except Exception as e:
#         _die(f"OpenAI call failed: {e}")
#     raw = (resp.choices[0].message.content or "").strip()
#     raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
#     try:
#         val = str(json.loads(raw).get("documentType", "")).strip()
#     except Exception:
#         _die("OpenAI did not return valid JSON.")
#     if val not in ("GDPR", "non-GDPR"):
#         _die('OpenAI JSON missing/invalid "documentType" (expected "GDPR" or "non-GDPR").')
#     return val

# # ================== Core function ==================
# def ensure_document_type(folder: Path) -> str:
#     """
#     If metadata.json lacks 'documentType', read en.txt/en.pdf, classify (OpenAI),
#     and update metadata.json. Returns the final documentType.
#     """
#     meta_path = folder / "metadata.json"
#     meta = _load_metadata(meta_path)
#     if meta.get("documentType"):
#         return meta["documentType"]

#     text = _read_en_text(folder)
#     if not text.strip():
#         _die(f"No text found in {folder} (need en.txt or en.pdf)")

#     # Prefer OpenAI only
#     doc_type = _classify_with_openai(text)

#     meta["documentType"] = doc_type
#     _save_metadata(meta_path, meta)
#     return doc_type

# # ================== Repo walker ==================
# def iter_case_folders(repo_root: Path, only_decision_like=True):
#     docs_root = repo_root / "documents"
#     if not docs_root.exists():
#         return
#     for country_dir in docs_root.iterdir():
#         if not country_dir.is_dir():
#             continue
#         for section_dir in country_dir.iterdir():
#             if not section_dir.is_dir():
#                 continue
#             if only_decision_like:
#                 if section_dir.name not in DECISION_LIKE_SECTIONS:
#                     continue
#             else:
#                 if section_dir.name not in SECTION_ALLOWLIST:
#                     continue
#             for case_dir in section_dir.iterdir():
#                 if case_dir.is_dir():
#                     yield case_dir

# def run_repo_scan(repo_root: Path, only_decision_like=True):
#     total = processed = skipped = 0
#     for case in iter_case_folders(repo_root, only_decision_like=only_decision_like):
#         total += 1
#         if not ((case / "en.txt").exists() or (case / "en.pdf").exists()):
#             skipped += 1
#             continue
#         result = ensure_document_type(case)
#         if result:
#             processed += 1
#             print(f"{case} → {result}")
#         else:
#             print(f"[–] {case} skipped (no text)")
#     print(f"\nSummary: total={total}, processed={processed}, skipped={skipped}")


# # ================== CLI ==================
# if __name__ == "__main__":
#     import argparse
#     ap = argparse.ArgumentParser(description="Assign documentType=GDPR/non-GDPR to case folders or files.")
#     g = ap.add_mutually_exclusive_group(required=True)
#     g.add_argument("--repo", type=Path, help="Root folder of repository containing /documents")
#     g.add_argument("--dir", type=Path, help="Specific case folder with en.txt/en.pdf")
#     g.add_argument("--file", type=Path, help="Specific .txt or .pdf file to classify")

#     args = ap.parse_args()

#     if args.repo:
#         run_repo_scan(args.repo.resolve())
#     elif args.dir:
#         result = ensure_document_type(args.dir.resolve())
#         print(f" Folder → {result or 'no text'}")
#     elif args.file:
#         fpath = args.file.resolve()
#         folder = fpath.parent
#         # Create metadata.json if needed
#         result = ensure_document_type(folder)
#         print(f" File {fpath.name} → {result or 'no text'}")

#     system = """
# Return STRICT JSON only: {"documentType": "GDPR" | "non-GDPR"}
# You are a LEGAL DOCUMENT CLASSIFIER for enforcement decisions.
# Your task is to determine whether a decision falls under the EU General Data Protection Regulation (GDPR)
# or another (non-GDPR) framework.

# You MUST base the classification on the LEGAL PROVISIONS THAT ACTUALLY GROUND THE FINE OR MAIN OPERATIVE RULING.
# Carefully read the entire decision text (facts, legal assessment, and operative part), including any section
# explicitly titled or functioning as "Legal basis", "Legal bases", "Rechtsgrundlagen", "Rechtsgrundlage",
# "Rechtliche Beurteilung", "Law", "Applicable law", "Legal assessment", or similar, and identify
# which articles/sections of law are used as the legal basis for the sanction, fine, or binding order.

# OUTPUT FORMAT (MANDATORY):
# Return EXACTLY one of: {"documentType": "GDPR"} OR {"documentType": "non-GDPR"}
# Do not add any other text, comments, or symbols.

# ========================
# RECOGNIZING GDPR PROVISIONS AND SYNONYMS
# ========================
# Treat as GDPR any reference to Regulation (EU) 2016/679 or its local names/abbreviations, including for example:
# - "GDPR" or "General Data Protection Regulation"
# - "Regulation (EU) 2016/679"
# - German: "Datenschutz-Grundverordnung", "DSGVO"
# - French: "RGPD"
# - Polish: "RODO"
# - Any other local-language name/abbreviation clearly referring to Regulation (EU) 2016/679.

# If a law is clearly described as the EU-wide general data protection regulation adopted as Regulation (EU) 2016/679,
# treat it as GDPR even if only the local-language name or abbreviation is used.

# IMPORTANT: Distinguish GDPR from OTHER EU DATA-PROTECTION INSTRUMENTS, such as e.g.:
# - Directive (EU) 2016/680 (police and criminal justice directive)
# - Directive 2002/58/EC (ePrivacy Directive)
# - Regulation (EU) 2018/1725 (EU institutions’ data protection regulation)
# These are NOT GDPR. If the operative legal basis relies ONLY on such instruments (plus national law), classify as "non-GDPR".

# ========================
# OPERATIVE LEGAL BASIS / FINE-FOCUSED CLASSIFICATION
# ========================
# Classify based ONLY on the provisions that actually contribute to the fine/sanction/operative decision:

# 1) When to return {"documentType": "GDPR"}:
#    - If one or more GDPR provisions (articles or recitals of the EU GDPR, including the above synonyms) contribute to
#      the fine or binding decision (i.e., they are part of the operative legal basis, not just background discussion),
#      then return {"documentType": "GDPR"}.

#    - "Contribute to the fine or binding decision" means:
#      a) GDPR provisions are cited in a section titled or functioning as:
#         "Legal basis", "Legal bases", "Rechtsgrundlagen", "Applicable law", "Law", "Legal assessment",
#         or directly in the operative part (disposition) that imposes obligations or fines, OR
#      b) The decision explicitly states that the infringement is an "infringement of Article X GDPR" or
#         "violation of the GDPR" and connects this to the fine/sanction/order.

#    - This includes cases where BOTH GDPR and other laws (e.g. national law, ePrivacy, sectoral law) contribute.
#      Example: a legal bases section such as
#        "§§ 22 para. 1 and 4 of the Data Protection Act (DSG) ...
#         Art. 18, 51, 57, and 58 of the General Data Protection Regulation (GDPR) ...
#         §§ 56, 57 para. 1 and 58 AVG ...
#         Art. 52a, 53, and 138b B-VG ...
#         § 25 VO-UA"
#      MUST be treated as GDPR contributing, because specific GDPR articles are part of the listed legal bases.

#    - ALSO classify as GDPR if all of the following are true:
#      * The decision clearly refers to "controller" / "processor" / "supervisory authority" in the GDPR sense, AND
#      * It identifies a violation of specific numbered "Articles" (e.g. Articles 5, 6, 12–22, 25, 32, 33, 34, 44–49)
#        together with the words "GDPR"/"DSGVO"/"RGPD"/etc. anywhere in the legal analysis or operative part.
#      In these cases, treat the referenced "Article X" as GDPR.

#    - Heuristic for right-based claims:
#      * If the decision explicitly refers to rights such as "Right to erasure / right to be forgotten",
#        "Right of access", "Right to rectification", "Right to restriction", "Right to data portability",
#        and clearly links them to "Article X GDPR" (with any local abbreviation like DSGVO, RGPD, RODO),
#        and those rights are the basis of the ruling, classify as GDPR.

# 2) When to return {"documentType": "non-GDPR"}:
#    - If ONLY non-GDPR laws (national laws, other EU instruments, sectoral regulations, criminal codes, etc.)
#      contribute to the fine or binding decision, and GDPR is NOT part of the operative legal basis, return
#      {"documentType": "non-GDPR"}.

#    - If GDPR is mentioned only as background/context, high-level principles, or general references, but the actual
#      fine/operative ruling is based solely on other laws, return {"documentType": "non-GDPR"}.
#      Example: A decision may describe GDPR generally in the introduction, but the "Legal basis" and operative part
#      rely exclusively on the national data-protection act or criminal-procedure act without citing any GDPR articles.
#      This must be classified as "non-GDPR".

#    - If the ONLY detailed EU instrument in the operative legal basis is another EU act (e.g. Directive (EU) 2016/680),
#      even if the GDPR is mentioned in passing in the background, classify as "non-GDPR".

#    - If a national law is described as "implementing the GDPR" but the decision NEVER cites any specific GDPR article
#      as part of the legal basis or infringement, and the operative part rests exclusively on national provisions,
#      classify as "non-GDPR".
#      (Implementation alone is not enough: there must be an operative reference to GDPR itself.)

# 3) Mixed / ambiguous cases:
#    - If both GDPR and non-GDPR provisions are cited, BUT:
#      * GDPR is mentioned ONLY in the introductory/contextual parts, AND
#      * The explicit legal basis for the sanction/order refers ONLY to non-GDPR provisions,
#      THEN classify as {"documentType": "non-GDPR"}.

#    - If the decision is unclear or ambiguous as to whether GDPR provisions contribute to the fine/operative ruling,
#      you MUST default to {"documentType": "non-GDPR"}.

# ========================
# PRACTICAL HEURISTICS TO REDUCE FALSE POSITIVES / FALSE NEGATIVES
# ========================
# When deciding, carefully check ALL of the following:

# A) HEADERS / OPERATIVE PART / LEGAL BASIS:
#    - Look for a distinct section naming legal provisions (often with enumerated articles/sections).
#    - If ANY of the enumerated provisions clearly belong to the GDPR (Regulation (EU) 2016/679),
#      classify as GDPR (even if other laws are listed too).

# B) LANGUAGE PATTERNS STRONGLY INDICATING GDPR:
#    - Phrases like "infringement of Article X GDPR/DSGVO/RGPD/RODO", "breach of the GDPR", or
#      "violation of the General Data Protection Regulation" in the context of the fine/order
#      strongly indicate GDPR as operative basis → classify as "GDPR".
#    - Phrases like "pursuant to Articles X and Y GDPR" directly linked to the decision (e.g. an order under Art. 58(2) GDPR)
#      indicate GDPR basis.

# C) LANGUAGE PATTERNS STRONGLY INDICATING NON-GDPR:
#    - References only to:
#      * Directive (EU) 2016/680,
#      * Directive 2002/58/EC (ePrivacy),
#      * Regulation (EU) 2018/1725,
#      * National criminal-procedure or security laws,
#      * Military or intelligence-authority acts,
#      with NO operative GDPR articles cited → classify as "non-GDPR".

# D) DEFAULT RULE:
#    - If, after reading the entire decision, you CANNOT confidently identify at least one GDPR provision
#      that clearly participates in the legal basis for the sanction/order, you MUST return:
#        {"documentType": "non-GDPR"}.

# Remember: the goal is to capture whether the enforcement decision is legally grounded on GDPR provisions.
# Mere mention of GDPR in background, context, or general discussion is NOT enough for "GDPR".

# """

    #     system = (
    #     'Return STRICT JSON only: {"documentType": "GDPR" | "non-GDPR"}\n'
    #     "You are a LEGAL DOCUMENT CLASSIFIER for enforcement decisions.\n"
    #     "Your task is to determine whether a decision falls under the EU General Data Protection Regulation (GDPR)\n"
    #     "or another (non-GDPR) framework.\n"
    #     "\n"
    #     "You MUST base the classification on the LEGAL PROVISIONS THAT ACTUALLY GROUND THE FINE OR MAIN OPERATIVE RULING.\n"
    #     "Carefully read the entire decision text (facts, legal assessment, and operative part), including any section\n"
    #     "explicitly titled or functioning as \"Legal basis\", \"Legal bases\", \"Rechtsgrundlagen\", or similar, and identify\n"
    #     "which articles/sections of law are used as the legal basis for the sanction, fine, or binding order.\n"
    #     "\n"
    #     "OUTPUT FORMAT (MANDATORY):\n"
    #     "Return EXACTLY one of: {\"documentType\": \"GDPR\"} OR {\"documentType\": \"non-GDPR\"}\n"
    #     "Do not add any other text, comments, or symbols.\n"
    #     "\n"
    #     "=== RECOGNIZING GDPR PROVISIONS AND SYNONYMS ===\n"
    #     "Treat as GDPR any reference to Regulation (EU) 2016/679 or its local names/abbreviations, including for example:\n"
    #     "- \"GDPR\" or \"General Data Protection Regulation\"\n"
    #     "- \"Regulation (EU) 2016/679\"\n"
    #     "- German: \"Datenschutz-Grundverordnung\", \"DSGVO\"\n"
    #     "- Other language abbreviations such as \"RGPD\", \"RODO\", etc., when they clearly refer to Regulation (EU) 2016/679.\n"
    #     "If a law is clearly described as the EU-wide general data protection regulation adopted as Regulation (EU) 2016/679,\n"
    #     "treat it as GDPR even if only the local-language name or abbreviation is used.\n"
    #     "\n"
    #     "=== OPERATIVE LEGAL BASIS / FINE-FOCUSED CLASSIFICATION ===\n"
    #     "Classify based ONLY on the provisions that actually contribute to the fine/sanction/operative decision:\n"
    #     "\n"
    #     "1) If one or more GDPR provisions (articles or recitals of the EU GDPR, including the above synonyms) contribute to\n"
    #     "   the fine or binding decision (i.e., they are part of the operative legal basis, not just background discussion),\n"
    #     "   then return {\"documentType\": \"GDPR\"}.\n"
    #     "   - This includes cases where BOTH GDPR and other laws (e.g. national law, ePrivacy, sectoral law) contribute.\n"
    #     "   - Example: a legal bases section such as \"§§ 22 para. 1 and 4 of the Data Protection Act (DSG) ...\n"
    #     "     Art. 18, 51, 57, and 58 of the General Data Protection Regulation (GDPR) ... §§ 56, 57 para. 1 and 58 AVG ...\n"
    #     "     Art. 52a, 53, and 138b B-VG ... § 25 VO-UA\" MUST be treated as GDPR contributing, because specific GDPR\n"
    #     "     articles are part of the listed legal bases for the decision.\n"
    #     "   - As soon as GDPR is part of the operative legal basis for the sanction, classify as \"GDPR\".\n"
    #     "\n"
    #     "2) If ONLY non-GDPR laws (national laws, other EU instruments, sectoral regulations, etc.) contribute to the\n"
    #     "   fine or binding decision, and GDPR is NOT part of the operative legal basis, return\n"
    #     "   {\"documentType\": \"non-GDPR\"}.\n"
    #     "\n"
    #     "3) If GDPR is mentioned only as background/context, high-level principles, or general references, but the actual\n"
    #     "   fine/operative ruling is based solely on other laws, return {\"documentType\": \"non-GDPR\"}.\n"
    #     "\n"
    #     "=== DEFAULT ===\n"
    #     "- If it is ambiguous or unclear whether GDPR provisions contribute to the fine / operative ruling, return\n"
    #     "  {\"documentType\": \"non-GDPR\"}.\n"
    # )