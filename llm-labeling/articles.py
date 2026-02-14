#!/usr/bin/env python3
"""
"""

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


def _norm_main_articles(items: List[str]) -> List[str]:
    """
    Normalize to ONLY main article numbers (no sub-articles), de-dup, preserve order.
      "83(5)" -> "83"
      "6(1)(a)" -> "6"
      "Article 32" -> "32"
    """
    out: List[str] = []
    for x in items or []:
        s = re.sub(r"^(article|art\.?)\s*", "", str(x).strip(), flags=re.I).strip()
        m = re.match(r"^(\d+)", s)
        if m:
            out.append(m.group(1))

    seen = set()
    deduped = []
    for a in out:
        if a not in seen:
            seen.add(a)
            deduped.append(a)
    return deduped

def _filter_articles_for_compare(articles: List[str]) -> List[str]:
    out = []
    for a in articles or []:
        try:
            n = int(a)
        except Exception:
            continue
        if 5 <= n <= 50:
            out.append(str(n))
    return sorted(set(out), key=int)



# ================== Metrics ==================
# def _confusion_update(c: Dict[str, int], truth_pos: bool, pred_pos: bool):
#     # Positive class = "HAS_ARTICLES" (non-empty list)
#     if truth_pos and pred_pos:
#         c["tp"] += 1
#     elif (not truth_pos) and pred_pos:
#         c["fp"] += 1
#     elif truth_pos and (not pred_pos):
#         c["fn"] += 1
#     else:
#         c["tn"] += 1


# def _metrics_from_counts(c: Dict[str, int]) -> Tuple[float, Optional[float], Optional[float], int]:
#     tp, fp, fn, tn = c["tp"], c["fp"], c["fn"], c["tn"]
#     n = tp + fp + fn + tn
#     acc = (tp + tn) / n if n else 0.0
#     prec = tp / (tp + fp) if (tp + fp) else None
#     rec = tp / (tp + fn) if (tp + fn) else None
#     return acc, prec, rec, n
def _list_overlap_counts(existing: List[str], predicted: List[str]) -> Tuple[int, int, int]:
    """
    Treat article numbers as a set (after normalization).
    Returns (tp, fp, fn).
    """
    a = set(existing or [])
    b = set(predicted or [])
    tp = len(a & b)
    fp = len(b - a)
    fn = len(a - b)
    return tp, fp, fn


def _case_jaccard(existing: List[str], predicted: List[str]) -> float:
    a = set(existing or [])
    b = set(predicted or [])
    if not a and not b:
        return 1.0
    union = a | b
    inter = a & b
    return (len(inter) / len(union)) if union else 0.0


def _micro_precision_recall_f1(tp: int, fp: int, fn: int) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    f1 = None
    if prec is not None and rec is not None and (prec + rec) > 0:
        f1 = 2 * prec * rec / (prec + rec)
    return prec, rec, f1

def _fmt(x: Optional[float]) -> str:
    return "—" if x is None else f"{x*100:.2f}%"


# ================== LLM extractor ==================
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

def _extract_first_json_object(raw: str) -> str:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    m = re.search(r"\{[\s\S]*?\}", raw)
    if not m:
        _die(f"No JSON object found in Gemini output:\n{raw[:500]}")
    return m.group(0)


def extract_violated_articles_with_gemini(text: str) -> List[str]:
    client = _require_gemini()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()

    prompt = (
        "Extract GDPR article numbers that are explicitly stated as violated, breached, infringed, "
        "or not complied with.\n"
        # "- Include ONLY explicitly violated/non-compliant articles.\n"
        "- Ignore articles cited only for competence/procedure/background.\n"
        "- Treat GDPR synonyms (GDPR, Regulation (EU) 2016/679, DSGVO, RGPD, RODO) as GDPR.\n"
        "- Output ONLY main article numbers (e.g., 83(5)->\"83\", 6(1)(a)->\"6\").\n"
        "- If the decision is non-negative (dismissed, rejected, inadmissible, or no violation found), extract GDPR articles that were explicitly assessed, examined, or discussed in the legal analysis, even if no violation was found."
        "- If no articles are found using the above rules AND the document explicitly states a GDPR legal basis, then extract the GDPR article number(s) mentioned as the legal basis."
        "- Do NOT output any article number less than 5 or greater than 50"
        "- Sort the article numbers numerically in ascending order.\n"
        "Return STRICT JSON only:\n"
        "{\"violatedGDPRArticles\":[\"5\",\"6\"]} or {\"violatedGDPRArticles\":[]}\n\n"
        "Document:\n---\n"
        f"{text[:180000]}\n"
        "---"
    )

    try:
        resp = client.models.generate_content(model=model, contents=prompt)
    except Exception as e:
        _die(f"Gemini call failed: {e}")

    # google-genai returns .text for convenience
    raw = getattr(resp, "text", None) or ""
    json_str = _extract_first_json_object(raw)

    try:
        obj = json.loads(json_str)
    except Exception:
        _die(f"Invalid JSON from Gemini:\n{raw[:500]}")

    arts = _norm_main_articles(obj.get("violatedGDPRArticles", []))
    arts = sorted(set(arts), key=int)  # enforce numeric sorting + dedupe
    return arts
# def _require_grok():
#     key = os.getenv("XAI_API_KEY", "").strip()
#     if not key:
#         _die("XAI_API_KEY is not set.")
#     try:
#         from openai import OpenAI
#     except Exception:
#         _die("OpenAI SDK not installed. Run: pip install openai")
#     return OpenAI(api_key=key, base_url="https://api.x.ai/v1")


# def extract_violated_articles_with_grok(text: str) -> List[str]:
#     client = _require_grok()
#     model = os.getenv("GROK_MODEL", "grok-4-1-fast-reasoning").strip()

#     system = (
#         "Extract GDPR article numbers that are explicitly stated as violated, "
#         "breached, infringed, or not complied with.\n"
#         "- Include ONLY explicitly violated/non-compliant articles.\n"
#         "- Ignore articles cited only for competence/procedure/background.\n"
#         "- Treat GDPR synonyms (GDPR, Regulation (EU) 2016/679, DSGVO, RGPD, RODO) as GDPR.\n"
#         "- Output ONLY main article numbers (e.g., 83(5)->\"83\", 6(1)(a)->\"6\").\n"
#         "- Sort the article numbers numerically in ascending order.\n"
#         "Return STRICT JSON only:\n"
#         "{\"violatedGDPRArticles\":[\"5\",\"6\"]} or {\"violatedGDPRArticles\":[]}"
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
#         _die(f"Grok call failed: {e}")

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

#     arts = _norm_main_articles(obj.get("violatedGDPRArticles", []))
#     # enforce numeric sorting + dedupe just in case
#     arts = sorted(set(arts), key=int)
#     return arts

# def _require_openai():
#     key = os.getenv("OPENAI_API_KEY", "").strip()
#     if not key:
#         _die("OPENAI_API_KEY is not set.")
#     try:
#         from openai import OpenAI
#     except Exception:
#         _die("OpenAI SDK not installed. Run: pip install openai")
#     return OpenAI(api_key=key)


# def extract_violated_articles_with_gpt(text: str) -> List[str]:
#     client = _require_openai()
#     model = os.getenv("OPENAI_MODEL", "gpt-5").strip()

#     system = (
#         "Extract GDPR article numbers that are explicitly stated as violated, "
#         "breached, infringed, or not complied with.\n"
#         "- Include ONLY explicitly violated/non-compliant articles.\n"
#         "- Ignore articles cited only for competence/procedure/background.\n"
#         "- Treat GDPR synonyms (GDPR, Regulation (EU) 2016/679, DSGVO, RGPD, RODO) as GDPR.\n"
#         "- Output ONLY main article numbers (e.g., 83(5)->\"83\", 6(1)(a)->\"6\").\n"
#         "- Sort the article numbers numerically in ascending order.\n"
#         "Return STRICT JSON only:\n"
#         "{\"violatedGDPRArticles\":[\"5\",\"6\"]} or {\"violatedGDPRArticles\":[]}"
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
#     m = re.search(r"\{[\s\S]*\}", raw)   # greedy to capture full JSON object
#     if not m:
#         _die(f"No JSON object found in model output:\n{raw[:500]}")
#     json_str = m.group(0)

#     try:
#         obj = json.loads(json_str)
#     except Exception:
#         _die(f"Invalid JSON from GPT:\n{raw[:500]}")

#     return _norm_main_articles(obj.get("violatedGDPRArticles", []))


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
    out_dir = repo_root / "llmtraining" / "article_results_gemini_new" / safe_model
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
    existing_articles: List[str],
    new_articles: List[str],
):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # existing_nonempty = 1 if len(existing_articles) > 0 else 0
    # new_nonempty = 1 if len(new_articles) > 0 else 0
    existing_cmp = _filter_articles_for_compare(existing_articles)
    new_cmp = _filter_articles_for_compare(new_articles)
    tp, fp, fn = _list_overlap_counts(existing_cmp, new_cmp)
    case_acc = _case_jaccard(existing_cmp, new_cmp)
    status = "MATCH" if (fp == 0 and fn == 0) else "DIFF"


    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow([
                "timestamp_utc",
                "model",
                "country",
                "case_path",
                "existing_articles",
                "new_articles",
                "tp",
                "fp",
                "fn",
                "case_accuracy_jaccard",
                "status",
            ])
        w.writerow([
            ts,
            model_name,
            country,
            str(case_path),
            ";".join(existing_cmp),
            ";".join(new_cmp),
            tp,
            fp,
            fn,
            round(case_acc, 6),
            status,
        ])


def _compute_country_metrics_from_csv(csv_path: Path) -> Tuple[int, float, int, int, int, Optional[float], Optional[float], Optional[float]]:
    """
    Returns:
      N_cases,
      mean_case_accuracy (mean Jaccard),
      TP_total, FP_total, FN_total,
      micro_precision, micro_recall, micro_f1
    """
    if not csv_path.exists():
        return 0, 0.0, 0, 0, 0, None, None, None

    n_cases = 0
    acc_sum = 0.0
    tp_total = fp_total = fn_total = 0

    with csv_path.open("r", encoding="utf-8", errors="ignore") as f:
        r = csv.DictReader(f)
        for row in r:
            n_cases += 1
            try:
                tp_total += int(row.get("tp", "0") or "0")
                fp_total += int(row.get("fp", "0") or "0")
                fn_total += int(row.get("fn", "0") or "0")
                acc_sum += float(row.get("case_accuracy_jaccard", "0") or "0")
            except Exception:
                # if a malformed row exists, skip it from metrics
                n_cases -= 1
                continue

    mean_acc = (acc_sum / n_cases) if n_cases else 0.0
    prec, rec, f1 = _micro_precision_recall_f1(tp_total, fp_total, fn_total)
    return n_cases, mean_acc, tp_total, fp_total, fn_total, prec, rec, f1


def _append_country_metrics_row(
    metrics_csv: Path,
    *,
    model_name: str,
    country: str,
    n_cases: int,
    mean_acc: float,
    tp: int,
    fp: int,
    fn: int,
    micro_p: Optional[float],
    micro_r: Optional[float],
    micro_f1: Optional[float],
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
                    "N_cases",
                    "mean_case_accuracy_jaccard",
                    "TP_total",
                    "FP_total",
                    "FN_total",
                    "micro_precision",
                    "micro_recall",
                    "micro_f1",
                ]
            )
        w.writerow(
            [
                run_id,
                model_name,
                country,
                n_cases,
                round(mean_acc, 6),
                tp,
                fp,
                fn,
                round(micro_p, 6) if micro_p is not None else "",
                round(micro_r, 6) if micro_r is not None else "",
                round(micro_f1, 6) if micro_f1 is not None else "",
            ]
        )


def _maybe_finalize_country_metrics(
    *,
    repo_root: Path,
    model_name: str,
    country: str,
    eligible_cases: Set[str],
):
    """
    Finalize a country exactly once when processed cases >= eligible cases.
    Uses <country>.finalized marker next to the results CSV.
    """
    results_csv = _country_results_csv(repo_root, model_name, country)
    processed = _load_processed_cases_from_country_csv(results_csv)

    if not eligible_cases:
        return
    if len(processed) < len(eligible_cases):
        return

    marker = results_csv.with_suffix(".finalized")
    if marker.exists():
        return

    n_cases, mean_acc, tp, fp, fn, micro_p, micro_r, micro_f1 = _compute_country_metrics_from_csv(results_csv)


    metrics_csv = repo_root / "verification_metrics_by_country_articles.csv"
    _append_country_metrics_row(
        metrics_csv,
        model_name=model_name,
        country=country,
        n_cases=n_cases,
        mean_acc=mean_acc,
        tp=tp,
        fp=fp,
        fn=fn,
        micro_p=micro_p,
        micro_r=micro_r,
        micro_f1=micro_f1,
    )

    marker.write_text(
        f"finalized_utc={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"country={country}\nmodel={model_name}\nN_cases={n_cases}\n"
        f"mean_case_accuracy_jaccard={mean_acc}\n"
        f"TP_total={tp}\nFP_total={fp}\nFN_total={fn}\n"
        f"micro_precision={micro_p}\nmicro_recall={micro_r}\nmicro_f1={micro_f1}\n",
        encoding="utf-8",
    )


# ================== Main processing ==================
def run_articles_repo(
    repo_root: Path,
    *,
    countries: Optional[Set[str]] = None,
    subplaces: Optional[Set[str]] = None,
):
    # model_name = os.getenv("GROK_MODEL", "grok-4-1-fast-reasoning").strip()
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()


    # Build eligible set per country first (same idea as documenttype verify)
    eligible_by_country: Dict[str, Set[str]] = {}

    for case in iter_case_folders(repo_root, countries=countries, subplaces=subplaces):
        meta = _load_metadata(case / "metadata.json")

        # STRICT: "articles" row must exist and be a list
        if "articles" not in meta:
            continue
        if not isinstance(meta["articles"], (list, str)):
            continue


        # Need text file
        if not ((case / "en.txt").exists() or (case / "en.pdf").exists()):
            continue

        ctry = _extract_country(case, repo_root)
        eligible_by_country.setdefault(ctry, set()).add(str(case))

    if not eligible_by_country:
        _die("No eligible cases found (need metadata['articles'] list + en.txt/en.pdf).")

    # Run country-by-country; resume per country using country CSV
    for ctry in sorted(eligible_by_country.keys()):
        out_csv = _country_results_csv(repo_root, model_name, ctry)
        processed_cases = _load_processed_cases_from_country_csv(out_csv)

        # If already finalized, still skip processing and continue
        if out_csv.with_suffix(".finalized").exists():
            continue

        # Process remaining cases only
        for case_path_str in sorted(eligible_by_country[ctry]):
            if case_path_str in processed_cases:
                continue

            case = Path(case_path_str)

            try:
                meta = _load_metadata(case / "metadata.json")
                existing_raw = meta["articles"]
                if isinstance(existing_raw, str):
                    # split on commas / semicolons
                    existing_raw = [
                        x.strip()
                        for x in re.split(r"[;,]\s*", existing_raw)
                        if x.strip()
                    ]

                existing = _norm_main_articles(existing_raw)


                text = _read_en_text(case)
                if not text.strip():
                    # keep it eligible but we can't process; DO NOT mark as processed in CSV
                    print(f"[skip: no text] {case}", file=sys.stderr)
                    continue

                new_articles = extract_violated_articles_with_gemini(text)

                _append_result_row(
                    out_csv,
                    model_name=model_name,
                    country=ctry,
                    case_path=case,
                    existing_articles=existing,
                    new_articles=new_articles,
                )
                existing_cmp = _filter_articles_for_compare(existing)
                new_cmp = _filter_articles_for_compare(new_articles)

                tp, fp, fn = _list_overlap_counts(existing_cmp, new_cmp)
                case_acc = _case_jaccard(existing_cmp, new_cmp)
                print(
                    f"[{ctry}] {case}  existing={existing_cmp}  new={new_cmp}  "
                    f"tp={tp} fp={fp} fn={fn}  case_acc={case_acc:.3f}"
                )

            except SystemExit:
                raise
            except Exception as e:
                # Do NOT write a CSV row => it will be retried on rerun
                print(f"[warn] Failed {case}: {e}", file=sys.stderr)
                continue

        # After processing, attempt to finalize if complete
        _maybe_finalize_country_metrics(
            repo_root=repo_root,
            model_name=model_name,
            country=ctry,
            eligible_cases=eligible_by_country[ctry],
        )

    # Print overall summary from finalized (and non-finalized) CSVs in this scope
    # (This is optional; accuracy/precision per country is guaranteed once finalized.)
    overall_cases = 0
    overall_acc_sum = 0.0
    overall_tp = overall_fp = overall_fn = 0

    for ctry in sorted(eligible_by_country.keys()):
        results_csv = _country_results_csv(repo_root, model_name, ctry)
        n_cases, mean_acc, tp, fp, fn, _, _, _ = _compute_country_metrics_from_csv(results_csv)
        overall_cases += n_cases
        overall_acc_sum += mean_acc * n_cases
        overall_tp += tp
        overall_fp += fp
        overall_fn += fn

    overall_mean_acc = (overall_acc_sum / overall_cases) if overall_cases else 0.0
    o_prec, o_rec, o_f1 = _micro_precision_recall_f1(overall_tp, overall_fp, overall_fn)

    print("\nOVERALL (article-list match):")
    print(f"  cases={overall_cases}  mean_case_accuracy={_fmt(overall_mean_acc)}")
    print(f"  micro_precision={_fmt(o_prec)}  micro_recall={_fmt(o_rec)}  micro_f1={_fmt(o_f1)}")

    safe_model = re.sub(r"[^a-zA-Z0-9._-]+", "_", model_name)
    print("\nPer-country CSVs:")
    print("  →", repo_root / "llmtraining" / "article_results" / safe_model)
    print("\nCountry metrics appended to:")
    print("  →", repo_root / "verification_metrics_by_country_articles.csv")


# ================== CLI ==================
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description=(
            "Resumable per-country verification of GPT-extracted violated GDPR articles "
            "vs existing metadata['articles'] (must be present as a list). "
            "Writes per-country CSVs, and finalizes country metrics once all eligible cases are processed."
        )
    )
    ap.add_argument("--repo", type=Path, required=True, help="Root folder of repository containing /documents")

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

    run_articles_repo(args.repo.resolve(), countries=countries, subplaces=subplaces)
