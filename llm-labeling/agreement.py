#!/usr/bin/env python3
"""
Pairwise agreement for numDataSubjectsAffected between TWO models.

Metrics:
- Krippendorff’s alpha (interval) for 2 raters (squared distance)
- Pearson correlation r
- Exact match rate
"""

import argparse
import csv
import math
from pathlib import Path
from typing import Dict, List, Tuple


def read_counts(path: Path) -> Dict[str, float]:
    """case_path -> numeric count (last row wins if duplicates)."""
    out: Dict[str, float] = {}
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames or "case_path" not in r.fieldnames:
            raise SystemExit(f"[error] {path}: missing 'case_path' column")
        if "numDataSubjectsAffected" not in r.fieldnames:
            raise SystemExit(f"[error] {path}: missing 'numDataSubjectsAffected' column")

        for row in r:
            case = (row.get("case_path") or "").strip()
            val = (row.get("numDataSubjectsAffected") or "").strip()
            if not case or val == "":
                continue
            try:
                out[case] = float(val)
            except Exception:
                continue
    return out


def align(a: Dict[str, float], b: Dict[str, float]) -> List[Tuple[float, float]]:
    common = sorted(set(a.keys()) & set(b.keys()))
    return [(a[k], b[k]) for k in common]


def pearson(x: List[float], y: List[float]) -> float:
    n = len(x)
    if n == 0:
        return float("nan")
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    denx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    deny = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if denx == 0 or deny == 0:
        return float("nan")
    return num / (denx * deny)


def krippendorff_alpha_interval(pairs: List[Tuple[float, float]]) -> float:
    if not pairs:
        return float("nan")

    # Observed disagreement (mean squared difference)
    Do = sum((x - y) ** 2 for x, y in pairs) / len(pairs)

    # Expected disagreement from pooled values
    pool = [x for x, _ in pairs] + [y for _, y in pairs]
    if len(pool) < 2:
        return float("nan")

    De_num = 0.0
    De_den = 0.0
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            De_num += (pool[i] - pool[j]) ** 2
            De_den += 1.0
    De = De_num / De_den if De_den else 0.0

    if abs(De) < 1e-12:
        return 1.0 if abs(Do) < 1e-12 else 0.0
    return 1.0 - (Do / De)


def exact_match_rate(pairs: List[Tuple[float, float]]) -> float:
    if not pairs:
        return float("nan")
    return sum(1 for x, y in pairs if x == y) / len(pairs)


def main():
    ap = argparse.ArgumentParser(description="Agreement for numDataSubjectsAffected between two model CSVs")
    ap.add_argument("--a", required=True, type=Path, help="CSV for model A")
    ap.add_argument("--b", required=True, type=Path, help="CSV for model B")
    ap.add_argument("--a-name", default="ModelA")
    ap.add_argument("--b-name", default="ModelB")
    args = ap.parse_args()

    A = read_counts(args.a)
    B = read_counts(args.b)

    pairs = align(A, B)
    x = [p[0] for p in pairs]
    y = [p[1] for p in pairs]

    print(f"{args.a_name} vs {args.b_name}")
    print(f"  Common cases: {len(pairs)}")
    print(f"  Krippendorff α (interval): {krippendorff_alpha_interval(pairs):.4f}")
    print(f"  Pearson r: {pearson(x, y):.4f}")
    print(f"  Exact match rate: {exact_match_rate(pairs):.4f}")


if __name__ == "__main__":
    main()
