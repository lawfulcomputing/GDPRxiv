#!/usr/bin/env python3

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Iterable, Optional, Set


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
    "Courts Decisions",
    "Annual Reports",
    "CPDP Decisions or Opinion",
    "SCA Decisions",
    "CourtRulings",
    "Decision of President",
    "Decision-Making Activities",
    "PressReleases",
    "Opinions",
    "Inspections",
    "Instructions",
    "Prescriptions",
    "2018 Finland Documents",
    "2019 Finland Documents",
    "2020 Finland Documents",
    "2021 Finland Documents",
    "2022 Finland Documents",
    "2023 Finland Documents",
    "2024 Finland Documents",
    "2025 Finland Documents",
    "Hearings",
    "Injunctions",
    "Newsletters",
    "Publications",
    "Interviews",
    "Enforcements",
    "Notices"
    }


# ================== ITERATOR ==================
def iter_case_folders(
    repo_root: Path,
    *,
    only_decision_like: bool = True,
    countries: Optional[Set[str]] = None,
) -> Iterable[Path]:

    docs_root = repo_root / "documents"
    if not docs_root.exists():
        return

    wanted_countries = {c.lower() for c in countries} if countries else None

    for country_dir in docs_root.iterdir():
        if not country_dir.is_dir():
            continue

        country_name = country_dir.name.lower()
        if wanted_countries and country_name not in wanted_countries:
            continue

        # ===== Germany special layout: documents/germany/<subplace>/<case> =====
        if country_name == "germany":
            for subplace_dir in country_dir.iterdir():
                if not subplace_dir.is_dir():
                    continue
                for case_dir in subplace_dir.iterdir():
                    if case_dir.is_dir():
                        yield case_dir
            continue

        # ===== Czech Republic special: Inspections has an extra level =====
        if country_name == "czech_republic":
            for section_dir in country_dir.iterdir():
                if not section_dir.is_dir():
                    continue

                # Handle Inspections/<subsection>/<case>
                if section_dir.name == "Inspections":
                    for subsec_dir in section_dir.iterdir():
                        if not subsec_dir.is_dir():
                            continue
                        for case_dir in subsec_dir.iterdir():
                            if case_dir.is_dir():
                                yield case_dir
                    continue

                # Other Czech sections follow normal layout
                if only_decision_like and section_dir.name not in DECISION_LIKE_SECTIONS:
                    continue

                for case_dir in section_dir.iterdir():
                    if case_dir.is_dir():
                        yield case_dir
            continue

        # ===== Normal countries: documents/<country>/<section>/<case> =====
        for section_dir in country_dir.iterdir():
            if not section_dir.is_dir():
                continue

            if only_decision_like and section_dir.name not in DECISION_LIKE_SECTIONS:
                continue

            for case_dir in section_dir.iterdir():
                if case_dir.is_dir():
                    yield case_dir


# ================== METADATA ==================
def _load_metadata(case_dir: Path) -> dict:
    meta_path = case_dir / "metadata.json"
    if not meta_path.exists():
        return {}

    try:
        data = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
        if isinstance(data, dict):
            return data
        else:
            # If somehow metadata is a list, ignore it
            return {}
    except Exception:
        return {}

def _parse_articles_to_int_set(val: Any) -> Set[int]:
    out: Set[int] = set()

    if isinstance(val, str):
        parts = [p.strip() for p in val.split(",")]
        for p in parts:
            if p.isdigit():
                out.add(int(p))
        return out

    if isinstance(val, (list, tuple)):
        for item in val:
            s = str(item).strip()
            if s.isdigit():
                out.add(int(s))
        return out

    return out


def _has_article_17(meta: dict) -> bool:
    articles_str = meta.get("articles")
    if not isinstance(articles_str, str):
        return False

    # Split strictly on comma
    parts = [p.strip() for p in articles_str.split(",")]

    # Match exact integer 17 only
    return "17" in parts

# ================== COPY ==================
def _dest_case_path(repo_root: Path, case_dir: Path) -> Path:
    rel = case_dir.relative_to(repo_root / "documents")
    return repo_root / "documents" / "rtbf" / rel


def copy_rtbf_cases(
    repo_root: Path,
    *,
    only_decision_like: bool = True,
    countries: Optional[Set[str]] = None,
    overwrite: bool = False,
) -> int:

    copied = 0

    for case_dir in iter_case_folders(
        repo_root,
        only_decision_like=only_decision_like,
        countries=countries,
    ):
        meta = _load_metadata(case_dir)

        if not _has_article_17(meta):
            continue

        dest = _dest_case_path(repo_root, case_dir)
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            if overwrite:
                shutil.rmtree(dest)
            else:
                continue

        shutil.copytree(case_dir, dest)
        copied += 1
        print(f"[copied] {case_dir} -> {dest}")

    print(f"\nDone. Total Article 17 folders copied: {copied}")
    print(f"Output root: {repo_root / 'documents' / 'rtbf'}")
    return copied


# ================== CLI ==================
def main():
    ap = argparse.ArgumentParser(
        description="Copy folders where metadata.json contains integer article 17 into documents/rtbf/"
    )
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--country", action="append")
    ap.add_argument("--overwrite", action="store_true")

    args = ap.parse_args()

    repo_root = args.repo.resolve()
    countries = set(args.country) if args.country else None

    copy_rtbf_cases(
        repo_root,
        countries=countries,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()