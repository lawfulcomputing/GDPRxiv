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
    file_order = [
        "en.txt",
        "en.pdf",
        "en_Full.txt",
        "en_Summary.pdf",
        "enSummary.txt",
        "en_1.pdf",
        "en-Enforcement notices.txt",
        "en-Monetary penalties.pdf",
    ]

    for name in file_order:
        p = folder / name
        if not p.exists():
            continue
        try:
            if p.suffix.lower() == ".pdf":
                txt = _read_pdf_text(p)
            else:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            if txt and txt.strip():
                return txt
        except Exception:
            continue
    return ""


def _articles_contains_17(meta: dict) -> bool:
    arts = meta.get("articles", "")
    if not arts:
        return False

    # your structure: "15, 17, 21"
    nums = re.findall(r"\d+", str(arts))
    return "17" in nums

def _load_metadata(p: Path) -> dict:
    folder = p.parent

    def has_article_17(d: dict) -> bool:
        arts = d.get("articles", "")
        nums = re.findall(r"\d+", str(arts))
        return "17" in nums

    def coerce_to_record(obj) -> dict:
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            if len(obj) > 1:
                for it in obj:
                    if isinstance(it, dict) and has_article_17(it):
                        return it
            for it in obj:
                if isinstance(it, dict):
                    return it
        return {}

    meta_files = sorted(folder.glob("metadata*.json"))

    if len(meta_files) > 1:
        for mf in meta_files:
            try:
                obj = json.loads(mf.read_text(encoding="utf-8"))
            except Exception:
                continue
            rec = coerce_to_record(obj)
            if rec and has_article_17(rec):
                return rec

        if p.exists():
            try:
                return coerce_to_record(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                return {}
        return {}

    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return coerce_to_record(obj)
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


# ================== Amount normalization + matching ==================
def _to_int_amount(x: object) -> int:
    if x is None or isinstance(x, bool):
        return 0
    if isinstance(x, int):
        return x if x >= 0 else 0
    if isinstance(x, float):
        return int(x) if x >= 0 else 0

    s = str(x).strip()
    if not s:
        return 0

    s2 = re.sub(r"[^0-9,.\-]", "", s)


    if "." in s2:
        s2 = s2.split(".", 1)[0]

    digits = re.sub(r"\D+", "", s2)
    if not digits:
        return 0

    try:
        val = int(digits)
        return val if val >= 0 else 0
    except Exception:
        return 0


# ================== Prompt ==================
SYSTEM_FINE = (
    "You will be given a legal decision / enforcement document.\n"
    "Extract the fine that is FINAL/PAID/IMPOSED.\n"
    "Ignore proposed fines, maximum statutory fines and non-final amounts.\n"
    "If multiple final/paid amounts exist, return their SUM.\n"
    "If a range is present, use the UPPER bound."
    "If no final/paid fine exists, return 0.\n\n"
)


# ================== Providers ==================
def _require_openai_client(api_key_env: str, *, base_url: Optional[str] = None):
    key = os.getenv(api_key_env, "").strip()
    if not key:
        _die(f"{api_key_env} is not set.")
    try:
        from openai import OpenAI
    except Exception:
        _die("OpenAI SDK not installed. Run: pip install openai")
    if base_url:
        return OpenAI(api_key=key, base_url=base_url)
    return OpenAI(api_key=key)


def _require_gemini_client():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        _die("GEMINI_API_KEY is not set.")
    try:
        from google import genai
    except Exception:
        _die("Gemini SDK not installed. Run: pip install google-genai")
    return genai.Client(api_key=key)


def _parse_fine_json(raw: str) -> int:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()

    if re.fullmatch(r"\d+(\.\d+)?", raw):
        try:
            return int(float(raw))
        except Exception:
            return 0

    m = re.search(r"\{[\s\S]*?\}", raw)
    if not m:
        return _to_int_amount(raw)

    try:
        obj = json.loads(m.group(0))
    except Exception:
        return _to_int_amount(raw)

    fine_val = obj.get("fine", 0)

    # enforce integer output
    if isinstance(fine_val, bool):
        return 0
    if isinstance(fine_val, int):
        return fine_val if fine_val >= 0 else 0
    if isinstance(fine_val, float):
        return int(fine_val) if fine_val >= 0 else 0
    return _to_int_amount(fine_val)


def extract_fine_openai(text: str) -> int:
    client = _require_openai_client("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-5").strip()

    user = f"Document:\n---\n{text[:180000]}\n---"

    try:
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_FINE},
                {"role": "user", "content": user},
            ],
        )
        raw = getattr(resp, "output_text", "") or ""
    except Exception as e:
        _die(f"OpenAI call failed: {e}")

    return _parse_fine_json(raw)


def extract_fine_grok(text: str) -> int:
    # xAI Grok is OpenAI-compatible at this base_url
    client = _require_openai_client("XAI_API_KEY", base_url="https://api.x.ai/v1")
    model = os.getenv("GROK_MODEL", "grok-4-1-fast-reasoning").strip()

    user = f"Document:\n---\n{text[:180000]}\n---"

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_FINE},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        _die(f"Grok call failed: {e}")

    return _parse_fine_json(raw)


def extract_fine_gemini(text: str) -> int:
    client = _require_gemini_client()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()

    user = f"Document:\n---\n{text[:180000]}\n---"

    try:
        from google.genai import types

        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_FINE,
                temperature=0,
                response_mime_type="application/json",
            ),
        )
        raw = (getattr(resp, "text", None) or "").strip()
    except Exception as e:
        _die(f"Gemini call failed: {e}")

    return _parse_fine_json(raw)


def extract_fine(text: str) -> int:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider == "openai":
        return extract_fine_openai(text)
    if provider == "grok":
        return extract_fine_grok(text)
    if provider == "gemini":
        return extract_fine_gemini(text)
    _die(f"Unknown LLM_PROVIDER={provider}. Use one of: openai, grok, gemini.")
    return 0


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

        # RTBF wrapper layout: documents/rtbf/<country>/<section>/<case>
        if country_name == "rtbf":
            for sub_country_dir in country_dir.iterdir():
                if not sub_country_dir.is_dir():
                    continue

                sub_country = sub_country_dir.name.lower()

                # Germany special layout inside rtbf: documents/rtbf/germany/<subplace>/<case>
                if sub_country == "germany":
                    for subplace_dir in sub_country_dir.iterdir():
                        if not subplace_dir.is_dir():
                            continue
                        if wanted_subplaces and subplace_dir.name.lower() not in wanted_subplaces:
                            continue
                        for case_dir in subplace_dir.iterdir():
                            if case_dir.is_dir():
                                yield case_dir
                    continue

                # Czech Republic inspections inside rtbf
                if sub_country == "czech_republic":
                    for section_dir in sub_country_dir.iterdir():
                        if not section_dir.is_dir():
                            continue
                        if section_dir.name == "Inspections":
                            for subsec_dir in section_dir.iterdir():
                                if not subsec_dir.is_dir():
                                    continue
                                for case_dir in subsec_dir.iterdir():
                                    if case_dir.is_dir():
                                        yield case_dir
                            continue
                        for case_dir in section_dir.iterdir():
                            if case_dir.is_dir():
                                yield case_dir
                    continue

                # Normal countries inside rtbf
                for section_dir in sub_country_dir.iterdir():
                    if not section_dir.is_dir():
                        continue
                    for case_dir in section_dir.iterdir():
                        if case_dir.is_dir():
                            yield case_dir
            continue


# ================== CSV + resume helpers ==================
def _country_results_csv(repo_root: Path, model_name: str, country: str) -> Path:
    safe_model = re.sub(r"[^a-zA-Z0-9._-]+", "_", model_name)
    out_dir = repo_root / "llm-labeling" / "rtbf_results" / "fines" / safe_model
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
    existing_fine: int,
    new_fine: int,
):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    status = "MATCH" if existing_fine == new_fine else "DIFF"

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(
                [
                    "timestamp_utc",
                    "provider",
                    "model",
                    "country",
                    "case_path",
                    "existing_fine",
                    "new_fine",
                    "status",
                ]
            )
        w.writerow(
            [
                ts,
                os.getenv("LLM_PROVIDER", "openai").strip().lower(),
                model_name,
                country,
                str(case_path),
                existing_fine,
                new_fine,
                status,
            ]
        )


def _compute_country_metrics_from_csv(csv_path: Path) -> Tuple[int, float]:
    if not csv_path.exists():
        return 0, 0.0

    truth: List[int] = []
    pred: List[int] = []

    with csv_path.open("r", encoding="utf-8", errors="ignore") as f:
        r = csv.DictReader(f)
        for row in r:
            t = _to_int_amount(row.get("existing_fine", 0))
            p = _to_int_amount(row.get("new_fine", 0))
            truth.append(t)
            pred.append(p)

    n = len(truth)
    if n == 0:
        return 0, 0.0

    correct = sum(1 for t, p in zip(truth, pred) if t == p)
    return n, correct / n


def _append_country_metrics_row(
    metrics_csv: Path,
    *,
    provider: str,
    model_name: str,
    country: str,
    n: int,
    acc: float,
):
    metrics_csv.parent.mkdir(parents=True, exist_ok=True)
    file_exists = metrics_csv.exists()
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with metrics_csv.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["run_id", "provider", "model", "country", "N", "accuracy"])
        w.writerow([run_id, provider, model_name, country, n, round(acc, 6)])


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

    n, acc = _compute_country_metrics_from_csv(results_csv)

    metrics_csv = repo_root / "verification_metrics_by_country_fine.csv"
    _append_country_metrics_row(
        metrics_csv,
        provider=os.getenv("LLM_PROVIDER", "openai").strip().lower(),
        model_name=model_name,
        country=country,
        n=n,
        acc=acc,
    )

    marker.write_text(
        f"finalized_utc={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"country={country}\nprovider={os.getenv('LLM_PROVIDER','openai').strip().lower()}\n"
        f"model={model_name}\nN={n}\naccuracy={acc}\n",
        encoding="utf-8",
    )


# ================== Main processing ==================
def run_fine_repo(
    repo_root: Path,
    *,
    countries: Optional[Set[str]] = None,
    subplaces: Optional[Set[str]] = None,
):
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

    # Pick model name based on provider (for output folder naming)
    if provider == "openai":
        model_name = os.getenv("OPENAI_MODEL", "gpt-5").strip()
    elif provider == "grok":
        model_name = os.getenv("GROK_MODEL", "grok-4-1-fast-reasoning").strip()
    elif provider == "gemini":
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()
    else:
        _die(f"Unknown LLM_PROVIDER={provider}. Use one of: openai, grok, gemini.")
        return

    # Build eligible set per country first
    eligible_by_country: Dict[str, Set[str]] = {}
    for case in iter_case_folders(repo_root, countries=countries, subplaces=subplaces):
        meta = _load_metadata(case / "metadata.json")

        # fine must exist (adjust if your key differs)
        if "fine" not in meta:
            continue

        if not isinstance(meta["fine"], (str, int, float)):
            continue

        # need text
        if not any(
            (case / name).exists()
            for name in [
                "en.txt",
                "en.pdf",
                "en_Full.txt",
                "en_Summary.pdf",
                "enSummary.txt",
                "en_1.pdf",
                "en-Enforcement notices.txt",
                "en-Monetary penalties.pdf",
            ]
        ):
            continue

        ctry = _extract_country(case, repo_root)
        eligible_by_country.setdefault(ctry, set()).add(str(case))

    if not eligible_by_country:
        _die("No eligible cases found (need metadata['fine'] + en.txt/en.pdf).")

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
                existing = _to_int_amount(meta.get("fine", 0))

                text = _read_en_text(case)
                if not text.strip():
                    print(f"[skip: no text] {case}", file=sys.stderr)
                    continue

                new_fine = int(extract_fine(text))

                _append_result_row(
                    out_csv,
                    model_name=model_name,
                    country=ctry,
                    case_path=case,
                    existing_fine=existing,
                    new_fine=new_fine,
                )

                status = "MATCH" if existing == new_fine else "DIFF"
                print(f"[{ctry}] {case} → {status} existing={existing} new={new_fine}")

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

    safe_model = re.sub(r"[^a-zA-Z0-9._-]+", "_", model_name)
    print("\nPer-country CSVs:")
    print("  →", repo_root / "llm-labeling" / "rtbf_results" / "fines" / safe_model)
    print("\nCountry metrics (finalized rows) appended to:")
    print("  →", repo_root / "verification_metrics_by_country_fine.csv")


# ================== CLI ==================
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description=(
            "Resumable per-country verification of LLM-extracted fine amount "
            "vs existing metadata['fine']. Writes per-country CSVs and finalizes country accuracy "
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

    run_fine_repo(args.repo.resolve(), countries=countries, subplaces=subplaces)