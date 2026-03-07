#!/usr/bin/env python3
import csv
import argparse
from pathlib import Path
from typing import Dict, Optional, Tuple, List


UNKNOWN_TOKEN = "unspecified"


def parse_count(raw: str) -> Optional[int]:
    if raw is None:
        return None

    s = raw.strip()
    if s == "" or s == UNKNOWN_TOKEN:
        return None

    return int(s)


def read_counts(path: Path) -> Dict[str, Optional[int]]:
    data: Dict[str, Optional[int]] = {}

    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)

        required = {"case_path", "numDataSubjectsAffected"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                f"{path} must contain columns: case_path, numDataSubjectsAffected"
            )

        for row in reader:
            case = (row.get("case_path") or "").strip()
            if not case:
                continue

            try:
                value = parse_count(row.get("numDataSubjectsAffected"))
            except ValueError:
                continue

            data[case] = value

    return data


def fmt(v: Optional[int]) -> str:
    return UNKNOWN_TOKEN if v is None else str(v)


def main():
    ap = argparse.ArgumentParser(
        description="Save 3-way disagreement cases for numDataSubjectsAffected."
    )
    ap.add_argument("--a", required=True, help="CSV file for model A")
    ap.add_argument("--b", required=True, help="CSV file for model B")
    ap.add_argument("--c", required=True, help="CSV file for model C")
    ap.add_argument("--out", required=True, help="Output CSV file")
    args = ap.parse_args()

    A = read_counts(Path(args.a))
    B = read_counts(Path(args.b))
    C = read_counts(Path(args.c))

    common = sorted(set(A.keys()) & set(B.keys()) & set(C.keys()))

    disagreements: List[
        Tuple[str, Optional[int], Optional[int], Optional[int]]
    ] = []

    for case in common:
        av = A[case]
        bv = B[case]
        cv = C[case]

        # keep only cases where not all three agree
        if not (av == bv == cv):
            disagreements.append((case, av, bv, cv))

    # Write output
    out_path = Path(args.out)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case_path", "model_A", "model_B", "model_C"])

        for case, av, bv, cv in disagreements:
            writer.writerow([
                case,
                fmt(av),
                fmt(bv),
                fmt(cv),
            ])

    print(f"\nTotal common cases: {len(common)}")
    print(f"3-way disagreements: {len(disagreements)}")
    print(f"Output written to: {out_path}")


if __name__ == "__main__":
    main()
