#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path
from typing import Iterable, Optional, Set


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
    "Injuctions",
    "Newsletters",
    "Publications",
    "Interviews",
    "Enforcements",
    "Notices",
}


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

        # Germany: documents/germany/<subplace>/<case>
        if country_name == "germany":
            for subplace_dir in country_dir.iterdir():
                if not subplace_dir.is_dir():
                    continue
                for case_dir in subplace_dir.iterdir():
                    if case_dir.is_dir():
                        yield case_dir
            continue

        # Czech Republic: Inspections/<subsection>/<case>
        if country_name == "czech_republic":
            for section_dir in country_dir.iterdir():
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

                if only_decision_like and section_dir.name not in DECISION_LIKE_SECTIONS:
                    continue

                for case_dir in section_dir.iterdir():
                    if case_dir.is_dir():
                        yield case_dir
            continue

        # Normal: documents/<country>/<section>/<case>
        for section_dir in country_dir.iterdir():
            if not section_dir.is_dir():
                continue

            if only_decision_like and section_dir.name not in DECISION_LIKE_SECTIONS:
                continue

            for case_dir in section_dir.iterdir():
                if case_dir.is_dir():
                    yield case_dir


def load_metadata(case_dir: Path) -> dict:
    meta_path = case_dir / "metadata.json"
    if not meta_path.exists():
        return {}
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Write a CSV of case paths where metadata.json contains 'RTBF component'."
    )
    ap.add_argument("--repo", type=Path, required=True, help="Repo root containing /documents")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output CSV path (default: <repo>/rtbf_component_cases.csv)",
    )
    ap.add_argument("--country", action="append", help="Restrict to specific countries (repeatable)")
    ap.add_argument("--all-sections", action="store_true", help="Scan ALL sections, not just decision-like")
    args = ap.parse_args()

    repo_root = args.repo.resolve()
    out_csv = args.out.resolve() if args.out else (repo_root / "rtbf_component_cases.csv")
    countries = set(args.country) if args.country else None

    hits = []
    for case_dir in iter_case_folders(repo_root, only_decision_like=not args.all_sections, countries=countries):
        meta = load_metadata(case_dir)

        # Match exact key
        if "RTBF component" in meta:
            hits.append(str(case_dir))

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_path"])
        for p in sorted(hits):
            w.writerow([p])

    print(f"Done. Found {len(hits)} case folders with 'RTBF component'.")
    print(f"CSV written to: {out_csv}")


if __name__ == "__main__":
    main()