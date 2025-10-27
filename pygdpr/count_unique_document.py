import os
from collections import Counter
from pathlib import Path
import pandas as pd

# country = "united_kingdom/Enforcements"
# base_path = f"../documents/{country}"
# output_file = "/..documents/unique_hash_ids.csv"

# all_hash_ids = []
# for item in os.listdir(base_path):
#     full_path = os.path.join(base_path, item)
#     if os.path.isdir(full_path):
#         all_hash_ids.append(item)

# total_count = len(all_hash_ids)
# counter = Counter(all_hash_ids)
# duplicates = [k for k, v in counter.items() if v > 1]
# unique_hash_ids = list(counter.keys())

# with open(output_file, "a") as f:
#     for hash_id in unique_hash_ids:
#         f.write(f"{country},{hash_id}\n")


# print(f"Country: {country}")
# print(f"Total hash_id folders: {total_count}")
# print(f"Duplicate hash_id folders: {len(duplicates)}")
# if duplicates:
#     print("Duplicate names:", duplicates)
# print(f"Unique hash IDs saved to {output_file}")





# check how many duplicate hash_id values in total
csv_path = Path("../documents/unique_hash_ids.csv")
df = pd.read_csv(csv_path, names=["country", "hash_id"])

duplicate_hashes = df[df.duplicated(subset=["hash_id"], keep=False)]

num_duplicates = duplicate_hashes["hash_id"].nunique()
total_duplicates = len(duplicate_hashes)

print(f"Total duplicate hash_id entries (counting all rows): {total_duplicates}")
print(f"Number of unique duplicated hash_ids: {num_duplicates}")

print("\nDuplicated hash_ids by country:")
print(duplicate_hashes.sort_values("hash_id").to_string(index=False))
