import os
import re
import pandas as pd
from collections import Counter

FILE_PATH = "/Users/venya/Desktop/GDPRxiv/llm-labeling/rtbf_results/articles/combined_rtbf_articles_with_all_match.csv"

# ---------- Helpers ----------
def to_int_set(x):
    """
    Extract ALL integer IDs from the cell (works even if it contains quotes, semicolons, etc.)
    Returns a set of ints => guaranteed unique.
    """
    if pd.isna(x):
        return set()
    s = str(x)
    nums = re.findall(r"\d+", s)  
    return {int(n) for n in nums}

def majority_vote(a, b, c):
    """Items that appear in at least 2 of the 3 sets."""
    counts = Counter(list(a) + list(b) + list(c))
    return {k for k, v in counts.items() if v >= 2}

def stringify_int_set(s):
    """Set[int] -> sorted comma-separated string."""
    if not s:
        return ""
    return ",".join(str(n) for n in sorted(s))

# ---------- Main ----------
if not os.path.exists(FILE_PATH):
    raise FileNotFoundError(f"File not found: {FILE_PATH}")

df = pd.read_csv(FILE_PATH)

required = ["new_articles_gpt", "new_articles_gemini", "new_articles_grok"]
missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"Missing required columns: {missing}")

# Parse as sets of INTS (normalizes quotes/semicolons/etc.)
gpt = df["new_articles_gpt"].apply(to_int_set)
gemini = df["new_articles_gemini"].apply(to_int_set)
grok = df["new_articles_grok"].apply(to_int_set)

# Compute row-wise
df["union_all_llm"] = [a | b | c for a, b, c in zip(gpt, gemini, grok)]
df["intersection_all_llm"] = [a & b & c for a, b, c in zip(gpt, gemini, grok)]
df["majority_2_of_3"] = [majority_vote(a, b, c) for a, b, c in zip(gpt, gemini, grok)]

# Stringify for CSV (unique + sorted)
df["union_all_llm"] = df["union_all_llm"].apply(stringify_int_set)
df["intersection_all_llm"] = df["intersection_all_llm"].apply(stringify_int_set)
df["majority_2_of_3"] = df["majority_2_of_3"].apply(stringify_int_set)

# Save (overwrite)
df.to_csv(FILE_PATH, index=False)

print(" Updated CSV saved with unique union/intersection/majority columns.")
print("File:", FILE_PATH)