#!/usr/bin/env python3
import csv
import argparse
from pathlib import Path
from typing import Dict, Optional, Tuple, List


UNKNOWN_TOKEN = "unknown" 


def parse_count(raw: str) -> Optional[int]:
    if raw is None:
        return None

    s = raw.strip()

    if s == "" or s == UNKNOWN_TOKEN:
        return None

    return int(s)  # raises ValueError if invalid


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

            raw = row.get("numDataSubjectsAffected")

            try:
                value = parse_count(raw)
            except ValueError:
                continue  # skip invalid rows

            data[case] = value

    return data


def main():
    ap = argparse.ArgumentParser(
        description="Save disagreement cases for numDataSubjectsAffected to CSV."
    )
    ap.add_argument("--a", required=True, help="CSV file for model A")
    ap.add_argument("--b", required=True, help="CSV file for model B")
    ap.add_argument("--out", required=True, help="Output CSV file")
    args = ap.parse_args()

    A = read_counts(Path(args.a))
    B = read_counts(Path(args.b))

    common = sorted(set(A.keys()) & set(B.keys()))
    disagreements: List[Tuple[str, Optional[int], Optional[int], Optional[int]]] = []
    # counters for pairwise disagreement scores ---
    total_common = len(common)
    overall_disagree = 0 

    known_known_total = 0
    known_known_disagree = 0

    for case in common:
        av = A[case]
        bv = B[case]

        if av != bv:
            overall_disagree += 1
        if av is not None and bv is not None:
            known_known_total += 1
            if av != bv:
                known_known_disagree += 1



    for case in common:
        av = A[case]
        bv = B[case]

        if av != bv:
            diff = abs(av - bv) if (av is not None and bv is not None) else None
            disagreements.append((case, av, bv, diff))

    # Write to CSV
    out_path = Path(args.out)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case_path", "model_A", "model_B", "abs_difference"])

        for case, av, bv, diff in disagreements:
            writer.writerow([
                case,
                "unknown" if av is None else av,
                "unknown" if bv is None else bv,
                diff if diff is not None else ""
            ])

    # Print summary
    print(f"\nTotal common cases: {len(common)}")
    print(f"Disagreement cases saved: {len(disagreements)}")
    print(f"Output written to: {out_path}")

    numeric_diffs = [d[3] for d in disagreements if d[3] is not None]
    if numeric_diffs:
        print("\nNumeric-only summary (both integers):")
        print(f"Max difference: {max(numeric_diffs)}")
        print(f"Min difference: {min(numeric_diffs)}")
        print(f"Average difference: {sum(numeric_diffs)/len(numeric_diffs):.2f}")
    
    overall_rate = (overall_disagree / total_common) if total_common else 0.0
    known_known_rate = (known_known_disagree / known_known_total) if known_known_total else 0.0

    print("\nPairwise disagreement scores:")
    print(f"Overall disagreement rate (all common cases): {overall_rate:.4f} ({overall_disagree}/{total_common})")
    print(f"Known-known disagreement rate (both integers only): {known_known_rate:.4f} ({known_known_disagree}/{known_known_total})")


if __name__ == "__main__":
    main()

# #!/usr/bin/env python3
# import csv
# import argparse
# from pathlib import Path


# def read_counts(path: Path):
#     data = {}
#     with path.open("r", encoding="utf-8", errors="ignore") as f:
#         reader = csv.DictReader(f)
#         for row in reader:
#             case = row["case_path"].strip()
#             try:
#                 value = int(row["numDataSubjectsAffected"])
#             except Exception:
#                 continue
#             data[case] = value
#     return data


# def main():
#     ap = argparse.ArgumentParser(description="Show disagreement cases for numDataSubjectsAffected.")
#     ap.add_argument("--a", required=True, help="CSV file for model A")
#     ap.add_argument("--b", required=True, help="CSV file for model B")
#     args = ap.parse_args()

#     path_a = Path(args.a)
#     path_b = Path(args.b)

#     A = read_counts(path_a)
#     B = read_counts(path_b)

#     common = sorted(set(A.keys()) & set(B.keys()))

#     disagreements = []

#     for case in common:
#         if A[case] != B[case]:
#             disagreements.append(
#                 (case, A[case], B[case], abs(A[case] - B[case]))
#             )

#     print(f"\nTotal common cases: {len(common)}")
#     print(f"Disagreement cases: {len(disagreements)}\n")

#     if not disagreements:
#         print("No disagreements found.")
#         return

#     print("case_path | model_A | model_B | abs_difference")
#     print("-" * 80)

#     for case, a_val, b_val, diff in disagreements:
#         print(f"{case} | {a_val} | {b_val} | {diff}")

#     print("\nSummary:")
#     diffs = [d[3] for d in disagreements]
#     print(f"Max difference: {max(diffs)}")
#     print(f"Min difference: {min(diffs)}")
#     print(f"Average difference: {sum(diffs)/len(diffs):.2f}")


# if __name__ == "__main__":
#     main()
