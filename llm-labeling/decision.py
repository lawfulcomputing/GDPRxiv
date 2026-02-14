#!/usr/bin/env python3
""" """

import csv
import os
import re
import json
import sys
from pathlib import Path
from typing import Optional, Set, List, Dict, Tuple
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
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
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


def _norm_decision(x: object) -> str:
    """
    Normalize decisions for comparison.
    - lowercases
    - collapses whitespace
    - strips punctuation at ends
    """
    s = str(x).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" .;:\t\r\n\"'")
    return s

def _decision_match(existing: str, predicted: str) -> bool:
    a = _norm_decision(existing)
    b = _norm_decision(predicted)

    if not a or not b:
        return False

    if a == b:
        return True

    # substring either way
    return (b in a) or (a in b)


# ================== GPT extractor ==================
# def _require_openai():
#     key = os.getenv("OPENAI_API_KEY", "").strip()
#     if not key:
#         _die("OPENAI_API_KEY is not set.")
#     try:
#         from openai import OpenAI
#     except Exception:
#         _die("OpenAI SDK not installed. Run: pip install openai")
#     return OpenAI(api_key=key)
# def _require_grok():
#     """
#     Grok (xAI) is OpenAI-compatible.
#     Env:
#       - XAI_API_KEY (required)
#       - GROK_MODEL  (optional)
#     """
#     key = os.getenv("XAI_API_KEY", "").strip()
#     if not key:
#         _die("XAI_API_KEY is not set.")
#     try:
#         from openai import OpenAI
#     except Exception:
#         _die("OpenAI SDK not installed. Run: pip install openai")
#     return OpenAI(api_key=key, base_url="https://api.x.ai/v1")
def _require_gemini():
    """
    Gemini client.
    Env:
      - GEMINI_API_KEY 
      - GEMINI_MODEL  
    """
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        _die("GEMINI_API_KEY is not set.")
    try:
        from google import genai
    except Exception:
        _die("Gemini SDK not installed. Run: pip install google-genai")
    return genai.Client(api_key=key)

# def extract_decision_with_gpt(text: str) -> str:
#     # client = _require_openai()
#     # model = os.getenv("OPENAI_MODEL", "gpt-5").strip()
#     client = _require_grok()
#     model = os.getenv("GROK_MODEL", "grok-4-1-fast-reasoning").strip()

#     system = (
#         "You will be given a legal decision document.\n"
#         "Extract ONLY the final operative decision/outcome of the case.\n"
#         "Focus on the dispositive or concluding part of the document, not background or reasoning.\n"
#         "Return a label with one or two words describing the final outcome.\n"
#         "Return STRICT JSON only:\n"
#         '{"decision":"..."}'
#     )

#     user = f"Document:\n---\n{text[:180000]}\n---"

#     try:
#         r = client.chat.completions.create(
#             model=model,
#             messages=[
#                 {"role": "system", "content": system},
#                 {"role": "user", "content": user},
#             ],
#         )
#     except Exception as e:
#         _die(f"GPT call failed: {e}")

#     raw = (r.choices[0].message.content or "").strip()
#     raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)

#     m = re.search(r"\{[\s\S]*?\}", raw)
#     if not m:
#         _die(f"No JSON object found in Grok output:\n{raw[:500]}")
#     json_str = m.group(0)
#     try:
#         obj = json.loads(json_str)
#     except Exception:
#         _die(f"Invalid JSON from Grok:\n{raw[:500]}")

#     val = obj.get("decision", "unknown")
#     return _norm_decision(val)
def extract_decision_with_gemini(text: str) -> str:
    client = _require_gemini()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()

    system = (
        "You will be given a legal decision document.\n"
        "Extract ONLY the final operative decision/outcome of the case.\n"
        "Focus on the dispositive or concluding part of the document, not background or reasoning.\n"
        "Return a label with one word describing the final outcome.\n"
        "Return STRICT JSON only:\n"
        '{"decision":"..."}'
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

    # Gemini can still sometimes wrap/append; parse first JSON object defensively
    m = re.search(r"\{[\s\S]*?\}", raw)
    if not m:
        _die(f"No JSON object found in Gemini output:\n{raw[:500]}")

    try:
        obj = json.loads(m.group(0))
    except Exception:
        _die(f"Invalid JSON from Gemini:\n{raw[:500]}")

    return _norm_decision(obj.get("decision", "unknown"))


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


# ================== CSV + resume helpers ==================
def _country_results_csv(repo_root: Path, model_name: str, country: str) -> Path:
    safe_model = re.sub(r"[^a-zA-Z0-9._-]+", "_", model_name)
    out_dir = repo_root / "llmtraining" / "decision_results_gemini_" / safe_model
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{country}.csv"


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


def _append_result_row(
    csv_path: Path,
    *,
    model_name: str,
    country: str,
    case_path: Path,
    existing_decision: str,
    new_decision: str,
):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    status = "MATCH" if _decision_match(existing_decision, new_decision) else "DIFF"

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(
                [
                    "timestamp_utc",
                    "model",
                    "country",
                    "case_path",
                    "existing_decision",
                    "new_decision",
                    "status",
                ]
            )
        w.writerow(
            [
                ts,
                model_name,
                country,
                str(case_path),
                existing_decision,
                new_decision,
                status,
            ]
        )


def _compute_country_metrics_from_csv(
    csv_path: Path,
) -> Tuple[int, float, Optional[float], Optional[float]]:
    """
    Computes multiclass metrics:
      - accuracy (exact match)
      - macro_precision/macro_recall over labels observed in TRUTH

    Returns: (N, accuracy, macro_precision, macro_recall)
    """
    if not csv_path.exists():
        return 0, 0.0, None, None

    truth: List[str] = []
    pred: List[str] = []

    with csv_path.open("r", encoding="utf-8", errors="ignore") as f:
        r = csv.DictReader(f)
        for row in r:
            t = _norm_decision(row.get("existing_decision", ""))
            p = _norm_decision(row.get("new_decision", ""))
            if not t:
                continue
            truth.append(t)
            pred.append(p)

    n = len(truth)
    if n == 0:
        return 0, 0.0, None, None

    correct = sum(1 for t, p in zip(truth, pred) if _decision_match(t, p))
    acc = correct / n

    labels = sorted(set(truth))  # macro over truth labels
    # per-label TP/FP/FN
    precs: List[float] = []
    recs: List[float] = []

    for lab in labels:
        tp = sum(1 for t, p in zip(truth, pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(truth, pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(truth, pred) if t == lab and p != lab)

        if tp + fp > 0:
            precs.append(tp / (tp + fp))
        # else: skip (no predicted positives for this label)

        if tp + fn > 0:
            recs.append(tp / (tp + fn))
        # else: skip (shouldn't happen since label is in truth, but keep safe)

    macro_p = sum(precs) / len(precs) if precs else None
    macro_r = sum(recs) / len(recs) if recs else None
    return n, acc, macro_p, macro_r


def _append_country_metrics_row(
    metrics_csv: Path,
    *,
    model_name: str,
    country: str,
    n: int,
    acc: float,
    macro_p: Optional[float],
    macro_r: Optional[float],
):
    metrics_csv.parent.mkdir(parents=True, exist_ok=True)
    file_exists = metrics_csv.exists()
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with metrics_csv.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(
                [
                    "run_id",
                    "model",
                    "country",
                    "N",
                    "accuracy",
                    "macro_precision",
                    "macro_recall",
                ]
            )
        w.writerow(
            [
                run_id,
                model_name,
                country,
                n,
                round(acc, 6),
                round(macro_p, 6) if macro_p is not None else "",
                round(macro_r, 6) if macro_r is not None else "",
            ]
        )


def _maybe_finalize_country_metrics(
    *,
    repo_root: Path,
    model_name: str,
    country: str,
    eligible_cases: Set[str],
):
    results_csv = _country_results_csv(repo_root, model_name, country)
    processed = _load_processed_cases_from_country_csv(results_csv)

    if not eligible_cases:
        return
    if len(processed) < len(eligible_cases):
        return

    marker = results_csv.with_suffix(".finalized")
    if marker.exists():
        return

    n, acc, mp, mr = _compute_country_metrics_from_csv(results_csv)

    metrics_csv = repo_root / "verification_metrics_by_country_decision.csv"
    _append_country_metrics_row(
        metrics_csv,
        model_name=model_name,
        country=country,
        n=n,
        acc=acc,
        macro_p=mp,
        macro_r=mr,
    )

    marker.write_text(
        f"finalized_utc={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"country={country}\nmodel={model_name}\nN={n}\n"
        f"accuracy={acc}\nmacro_precision={mp}\nmacro_recall={mr}\n",
        encoding="utf-8",
    )


# ================== Main processing ==================
def run_decision_repo(
    repo_root: Path,
    *,
    countries: Optional[Set[str]] = None,
    subplaces: Optional[Set[str]] = None,
):
    # model_name = os.getenv("OPENAI_MODEL", "gpt-5").strip()
    # model_name = os.getenv("GROK_MODEL", "grok-4-1-fast-reasoning").strip()
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()


    # Build eligible set per country first
    eligible_by_country: Dict[str, Set[str]] = {}
    for case in iter_case_folders(repo_root, countries=countries, subplaces=subplaces):
        meta = _load_metadata(case / "metadata.json")

        # decision must exist
        if "decision" not in meta:
            continue

        # accept string-ish
        if not isinstance(meta["decision"], (str, int, float)):
            continue

        # need text
        if not ((case / "en.txt").exists() or (case / "en.pdf").exists()):
            continue

        ctry = _extract_country(case, repo_root)
        eligible_by_country.setdefault(ctry, set()).add(str(case))

    if not eligible_by_country:
        _die("No eligible cases found (need metadata['decision'] + en.txt/en.pdf).")

    for ctry in sorted(eligible_by_country.keys()):
        out_csv = _country_results_csv(repo_root, model_name, ctry)
        processed_cases = _load_processed_cases_from_country_csv(out_csv)

        if out_csv.with_suffix(".finalized").exists():
            continue

        for case_path_str in sorted(eligible_by_country[ctry]):
            if case_path_str in processed_cases:
                continue

            case = Path(case_path_str)
            try:
                meta = _load_metadata(case / "metadata.json")
                existing = _norm_decision(meta["decision"])

                text = _read_en_text(case)
                if not text.strip():
                    print(f"[skip: no text] {case}", file=sys.stderr)
                    continue

                new_dec = extract_decision_with_gemini(text)

                _append_result_row(
                    out_csv,
                    model_name=model_name,
                    country=ctry,
                    case_path=case,
                    existing_decision=existing,
                    new_decision=new_dec,
                )

                status = "MATCH" if _decision_match(existing, new_dec) else "DIFF"
                print(f"[{ctry}] {case} → {status} existing={existing} new={new_dec}")

            except SystemExit:
                raise
            except Exception as e:
                # don't write CSV row => retried on rerun
                print(f"[warn] Failed {case}: {e}", file=sys.stderr)
                continue

        _maybe_finalize_country_metrics(
            repo_root=repo_root,
            model_name=model_name,
            country=ctry,
            eligible_cases=eligible_by_country[ctry],
        )

    print("\nPer-country CSVs:")
    safe_model = re.sub(r"[^a-zA-Z0-9._-]+", "_", model_name)
    print("  →", repo_root / "llmtraining" / "decision_results" / safe_model)
    print("\nCountry metrics (finalized rows) appended to:")
    print("  →", repo_root / "verification_metrics_by_country_decision.csv")


# ================== CLI ==================
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description=(
            "Resumable per-country verification of GPT-extracted decision outcome "
            "vs existing metadata['decision']. Writes per-country CSVs and finalizes country metrics "
            "once all eligible cases are processed."
        )
    )
    ap.add_argument(
        "--repo",
        type=Path,
        required=True,
        help="Root folder of repository containing /documents",
    )

    ap.add_argument(
        "--country",
        action="append",
        help="Limit processing to specific country folder(s) under /documents (case-insensitive). Can be used multiple times.",
    )

    ap.add_argument(
        "--subplace",
        action="append",
        help="For countries with nested sub-place folders (e.g. documents/germany/<subplace>/<case>), limit processing to sub-place(s).",
    )

    args = ap.parse_args()
    countries = set(args.country) if args.country else None
    subplaces = set(args.subplace) if args.subplace else None

    run_decision_repo(args.repo.resolve(), countries=countries, subplaces=subplaces)
