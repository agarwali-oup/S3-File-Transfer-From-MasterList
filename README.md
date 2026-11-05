# S3 ISBN and Master Reference File Transfer

This project searches an entire source Amazon S3 bucket for PDF and XML files whose filenames contain an ISBN or Master Reference Number from an Excel file. Matching files are copied to a configured destination prefix, which may be in another S3 bucket, and an audit CSV is produced.

The main script is `main.py`.

## What the script does

1. Reads ISBN and Master Reference Number values from an Excel spreadsheet.
2. Lists objects across the entire source S3 bucket, including objects inside all prefixes or folders.
3. Considers only files ending in `.pdf` or `.xml`, case-insensitively.
4. Matches an ISBN or Master Reference Number within the filename.
5. Allows separators such as hyphens, underscores, or spaces between digits.
6. Copies each matching file to the configured destination S3 bucket and prefix.
7. Writes an audit file named `matched_files.csv`.

The operation uses an S3 copy. The source object remains in place unless explicit delete logic is added after a successful copy.

## Matching examples

| Identifier | Filename | Result |
|---|---|---|
| `9780198883906` | `9780198883906.pdf` | Match |
| `9780198883906` | `978-0-198-88390-6.pdf` | Match |
| `9780198883906` | `contract_978-0-198-88390-6.xml` | Match |
| `9786` | `97-86.pdf` | Match |
| `9786` | `9876.pdf` | No match |
| `9786` | `97-86-0.pdf` | No match |

A valid match must preserve the exact digit order and cannot be part of a longer number.

## Project files

```text
Transfer_files_from_researchbucket/
|-- main.py
|-- filename.xlsx
|-- README.md
`-- matched_files.csv       # Created after a completed run
```

## Requirements

- Python 3.10 or later
- AWS credentials with permission to list the source bucket and copy objects to the destination bucket
- An Excel file containing the expected identifier columns

Install the Python packages:

```powershell
python -m pip install boto3 pandas openpyxl
```

## Excel input

By default, the script expects `filename.xlsx` with these columns:

- `ISBN`
- `Master Reference No.`

Blank cells are allowed and should be skipped by the script.

ISBNs displayed in Excel as scientific notation, such as `9.7802E+12`, may not contain the complete original value. Confirm that the full ISBN is visible in the Excel formula bar or available from the original source data. Exact filename matching is not reliable if digits have already been rounded or lost.

Read identifier columns as strings where possible:

```python
df = pd.read_excel(
    INPUT_XLSX,
    dtype={
        "ISBN": str,
        "Master Reference No.": str,
    },
).fillna("")
```

## Configuration

Update the configuration section in `main.py` before running:

```python
INPUT_XLSX = "filename.xlsx"

SOURCE_BUCKET = "source-bucket"

DEST_BUCKET = "destination-bucket"
DEST_PREFIX = "matched-contracts/"

OUTPUT_AUDIT = "matched_files.csv"
```

The complete source bucket is searched. Do not set a source prefix if all source prefixes and folders must be included.

## AWS authentication

The script uses the standard `boto3` credential chain. A common local setup is the AWS CLI:

```powershell
aws configure
```

Then provide the access key, secret key, default AWS Region, and output format when prompted.

If named AWS profiles are used, set the profile before running:

```powershell
$env:AWS_PROFILE = "your-profile-name"
```

Example minimum permissions:

- `s3:ListBucket` on the source bucket
- `s3:GetObject` on source objects
- `s3:PutObject` on the destination prefix

If source objects use AWS KMS encryption, the identity may also need `kms:Decrypt`. If the destination requires KMS encryption, it may need `kms:Encrypt` and `kms:GenerateDataKey`.

## Run the script

From the project directory:

```powershell
python main.py
```

Or with a specific Python executable:

```powershell
& "C:\Path\To\Python\python.exe" "C:\Path\To\Project\main.py"
```

Example progress output:

```text
Loaded 10,000 search patterns
MATCH | ISBN | 9783318000160 | 9783318000160.pdf
MATCH | ISBN | 9783318000238 | 9783318000238.pdf
```

This confirms that matching is working. If `copy_to_destination()` is called before the message is printed, the matching object has also been copied successfully.

A completed run should report the final match count and audit path, for example:

```text
Matches found: 8250
Audit written: matched_files.csv
```

## Audit output

`matched_files.csv` records fields such as:

- Identifier type, such as `ISBN` or `MR`
- Matched identifier
- Source S3 key
- Destination S3 key
- Filename

Keep the audit file as the transfer record and use it to review duplicate matches, missing XML or PDF counterparts, and destination naming collisions.

## Important behavior and limitations

### Copy versus move

Amazon S3 does not provide a native rename or move operation. A move is implemented as:

1. Copy the source object to the destination.
2. Verify that the copy succeeded.
3. Delete the source object.

The current workflow should be treated as a copy unless `delete_object()` is explicitly included after successful verification. Copy-first behavior is safer for production data.

### Duplicate filenames

If objects in different source prefixes have the same basename and the destination uses only that basename, one destination object can overwrite another.

To avoid collisions, either preserve the source key structure or add a unique suffix to the destination key. For example:

```python
dest_key = f"{DEST_PREFIX.rstrip('/')}/{src_key}"
```

### Re-running the script

S3 copies to an existing destination key replace the destination object's current version, unless bucket versioning is enabled. For safer reruns, check whether the destination key exists and either skip it or record it as already present.

### Performance

The script scans every object in the source bucket. Runtime depends primarily on the number of S3 objects and the number of identifier patterns. With 10,000 patterns, running every regular expression against every filename can become slow for very large buckets.

For large inventories, consider creating an Amazon S3 Inventory report and matching locally, or redesigning the matcher around normalized identifiers and indexed lookup rather than testing all patterns for every object.

### File extensions

Only `.pdf` and `.xml` objects are processed. ZIP files are not transferred unless `.zip` is added explicitly to the extension filter.

## Removing the Python syntax warning

If Python reports:

```text
SyntaxWarning: "\d" is an invalid escape sequence
```

make the regex example docstring raw:

```python
def build_pattern(number: str):
    r"""Create a regex allowing separators between digits."""
```

Alternatively, remove the regex example from the docstring. The actual regular-expression strings should use raw-string notation, such as `r"(?<!\d)"`.

## Recommended validation before a full transfer

1. Test with a small Excel file containing 5 to 10 identifiers.
2. Use a temporary destination prefix.
3. Confirm exact, hyphenated, PDF, XML, and non-match cases.
4. Inspect `matched_files.csv`.
5. Check for duplicate destination keys.
6. Run the full spreadsheet only after the sample is correct.

## Troubleshooting

### `AttributeError: 'float' object has no attribute 'lower'`

An empty Excel cell was read as `NaN`. Clean the columns before processing:

```python
df["ISBN"] = df["ISBN"].fillna("").astype(str).str.strip()
df["Master Reference No."] = (
    df["Master Reference No."]
    .fillna("")
    .astype(str)
    .str.strip()
)
```

Then use `if isbn:` and `if mr:` instead of calling `.lower()` on an uncleaned value.

### No XML matches

Check whether XML objects exist in the source bucket, whether their names contain the ISBN or Master Reference Number, and whether the extension is exactly `.xml` apart from letter case.

### `AccessDenied`

Confirm the active AWS identity and S3 permissions:

```powershell
aws sts get-caller-identity
```

The identity must be able to list the source bucket, read its objects, and write to the destination bucket and prefix.

### The script appears to keep running

Listing the entire bucket and evaluating 10,000 patterns can take time. The run is complete only when the final match count is printed and the PowerShell prompt returns.
