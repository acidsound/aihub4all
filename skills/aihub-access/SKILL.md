---
name: aihub-access
description: Discover Korean AI Hub datasets and data packages, inspect file trees and file IDs, check download prerequisites, download approved data, and safely extract or merge AI Hub split archives. Use when a researcher asks to find, retrieve, or prepare data from aihub.or.kr.
license: MIT
compatibility: Requires Python 3.10+ for the bundled standard-library utility and an AI Hub API key for downloads.
metadata:
  author: AIHub4All
  version: "0.1.0"
---

# AI Hub access

Use this skill to help a researcher discover and prepare datasets from [AI Hub](https://aihub.or.kr). The bundled utility is the deterministic interface for metadata queries, downloads, extraction, and split-file merging.

## Required safeguards

1. **Respect AI Hub authorization.** A dataset or package may be publicly listed but still require an approved download request. Never imply that listing visibility grants download permission. Before downloading, ensure the user confirms that approval has been granted through the AI Hub website. Do not attempt to bypass approval.
2. **Protect the API key.** The utility reads AIHUB_API_KEY from the environment. Never ask the user to paste the key into chat, put it in a command recorded in shell history, save it in a repository, or print it. If the key is not configured, explain how the user can set it in their own environment.
3. **Prevent surprise bulk transfers.** Inspect dataset/package details and selected file sizes first. Before a large download, summarize the selected files, estimated size if available, destination, and the official guidance to reserve about 2–3 times the download size. Obtain explicit user confirmation before starting a substantial transfer.
4. **Preserve user data.** The utility refuses to overwrite existing output files, extracts into a temporary directory, rejects unsafe TAR paths and special entries, and removes split parts only after a successful merge. Do not manually delete user files to make a command succeed.
5. **Report uncertainty.** AI Hub's public guide does not provide complete metadata JSON schemas. Treat unknown fields and undocumented server behavior as unknown; inspect actual responses rather than inventing fields.

## Workflow

### 1. Discover

Use the bundled script from this skill directory:

~~~bash
python <skill-directory>/scripts/aihub.py datasets
python <skill-directory>/scripts/aihub.py dataset DATASET_KEY
python <skill-directory>/scripts/aihub.py packages
python <skill-directory>/scripts/aihub.py package PACKAGE_KEY
~~~

Start with a list query if the user has not supplied an identifier. Narrow candidates using the returned names and descriptions, then inspect the chosen dataset/package file tree. Capture file IDs and sizes from the actual response; do not guess identifiers.

### 2. Plan

Present the dataset or package identifier, chosen file IDs (or all files), known sizes, output location, and the approval requirement. If sizes are absent, say the transfer size is unknown. Ask for confirmation before initiating a large or complete dataset download.

### 3. Download

Confirm that AIHUB_API_KEY is configured in the execution environment, without reading or displaying its value. The user must already have the relevant AI Hub download approval.

~~~bash
python <skill-directory>/scripts/aihub.py download dataset DATASET_KEY \
  --file-ids 123,456 --output-dir ./aihub-data
~~~

Omit --file-ids to request all files. For a package, replace dataset with package and use its package key.

Options:
- --archive-only downloads the TAR without extracting it.
- --keep-archive retains the TAR after successful extraction and merging.
- Existing files are never overwritten.

If shell execution is unavailable, provide the exact command for the user to run locally. Do not claim the data was downloaded unless the command actually completed and the output files were verified.

### 4. Process existing files

~~~bash
python <skill-directory>/scripts/aihub.py process /path/to/archive.tar \
  --output-dir ./aihub-data
python <skill-directory>/scripts/aihub.py merge ./aihub-data
~~~

The merge operation expects names such as filename.zip.part0 and filename.zip.part1073741824. Parts are concatenated in numeric byte-offset order. If offsets are inconsistent, stop and retain all parts.

### 5. Report the result

Report the output directory, archive and processing status, merged files, and any errors. Do not claim dataset contents were inspected unless they were actually inspected. Remind the user that dataset license and use conditions still apply.

## Reference

Read references/api-reference.md for the observed HTTP routes, authentication, file selection, and known unknowns. The repository-level OpenAPI document is openapi/aihub.openapi.yaml when the full repository is available.
