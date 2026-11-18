import re
import boto3
import pandas as pd
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================

INPUT_XLSX = "C:/Users/agarwais/Downloads/JiraTasks/Transfer_files_from_researchbucket/filename.xlsx"

SOURCE_BUCKET = "ol-research-data-prod"
# uncomment to specify the folder, by default it looks up the entire bucket
# SOURCE_PREFIX = "contracts/"

DEST_BUCKET = "ol-rd4ai-multimodal-prod"
DEST_PREFIX = "input/client-c/delivery-files-for-image-redaction/"

OUTPUT_AUDIT = "C:/Users/agarwais/Downloads/JiraTasks/Transfer_files_from_researchbucket/matched_files.csv"

# ============================================================
# AWS
# ============================================================

s3 = boto3.client("s3")


# ============================================================
# HELPERS
# ============================================================

def build_pattern(number: str):
    """
    Create regex allowing separators between digits.

    Example:
    9780198 ->
    (?<!\d)9[-_\s]*7[-_\s]*8[-_\s]*0[-_\s]*1[-_\s]*9[-_\s]*8(?![-_\s]*\d)
    """

    number = str(number).strip()

    regex = r"(?<!\d)"

    for i, d in enumerate(number):
        regex += re.escape(d)

        if i < len(number) - 1:
            regex += r"[-_\s]*"

    regex += r"(?![-_\s]*\d)"

    return re.compile(regex)


def list_s3_objects(bucket, prefix):
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(
        Bucket=bucket,
        Prefix=prefix
    ):
        for obj in page.get("Contents", []):
            yield obj["Key"]


def copy_to_destination(src_bucket, src_key):
    file_name = Path(src_key).name

    dest_key = f"{DEST_PREFIX.rstrip('/')}/{file_name}"

    s3.copy(
        {"Bucket": src_bucket, "Key": src_key},
        DEST_BUCKET,
        dest_key,
    )

    return dest_key


# ============================================================
# LOAD ISBN / MR NUMBERS
# ============================================================

df = pd.read_excel(INPUT_XLSX)

df["ISBN"] = df["ISBN"].astype(str).str.strip()
df["Master Reference No."] = (
    df["Master Reference No."]
    .astype(str)
    .str.strip()
)

patterns = []

for _, row in df.iterrows():

    isbn = row["ISBN"]
    mr = row["Master Reference No."]

    if pd.notna(isbn) and str(isbn).strip():
        isbn = str(isbn).strip()

        # Remove .0 added when Excel values are read as floats
        if isbn.endswith(".0"):
            isbn = isbn[:-2]

        patterns.append({
            "identifier": isbn,
            "type": "ISBN",
            "regex": build_pattern(isbn)
        })

    if pd.notna(mr) and str(mr).strip():
        mr = str(mr).strip()

        if mr.endswith(".0"):
            mr = mr[:-2]

        patterns.append({
            "identifier": mr,
            "type": "MR",
            "regex": build_pattern(mr)
        })

print(f"Loaded {len(patterns):,} search patterns")

# ============================================================
# SEARCH S3
# ============================================================

results = []

for key in list_s3_objects(
    SOURCE_BUCKET,
    ""
):

    lower_key = key.lower()

    if not (
        lower_key.endswith(".pdf")
        or lower_key.endswith(".xml")
    ):
        continue

    filename = Path(key).name

    for p in patterns:

        if p["regex"].search(filename):

            dest_key = copy_to_destination(
                SOURCE_BUCKET,
                key
            )

            results.append({
                "identifier_type": p["type"],
                "identifier": p["identifier"],
                "source_key": key,
                "destination_key": dest_key,
                "filename": filename
            })

            print(
                f"MATCH | {p['type']} | "
                f"{p['identifier']} | {filename}"
            )

            break


# ============================================================
# OUTPUT AUDIT
# ============================================================

audit_df = pd.DataFrame(results)

audit_df.to_csv(
    OUTPUT_AUDIT,
    index=False
)

print()
print(f"Matches found: {len(audit_df):,}")
print(f"Audit written: {OUTPUT_AUDIT}")
