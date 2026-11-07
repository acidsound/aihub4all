# Downloaded data processing

AI Hub's shell downloads a TAR archive. The archive contains the original directory structure and may contain files split into byte-offset parts, for example:

~~~text
dataset/
  training/
    source.zip.part0
    source.zip.part1073741824
    source.zip.part2147483648
~~~

The intended processing sequence is:

1. Download the TAR response.
2. Extract the archive while preserving its directory structure.
3. Group files by their shared name before .part.
4. Concatenate each group's pieces in numeric offset order.
5. Remove the split pieces only after the merged output has been written successfully.

## Storage planning

AI Hub's guide recommends keeping approximately 2–3 times the dataset download size available because download archives and extracted files can coexist during processing. Actual requirements depend on the archive and selected files.

Inspect a dataset's file tree before downloading. Prefer selected file IDs to a whole-dataset download when that satisfies the research task.

## Split-file convention

The observed naming convention uses a numeric suffix after .part. The supplied example includes .part0 and .part1073741824, indicating byte offsets rather than simple part indexes.

AIHub4All validates that:
- The first part starts at offset 0.
- Every later suffix equals the number of bytes already written.
- The destination merged file does not already exist.
- Source parts are removed only after the temporary merged file has been atomically moved into place.

If an offset is missing or inconsistent, merging stops and the parts are retained for inspection. Do not rename or reorder parts manually to force a merge.

## Safe extraction

The downloader extracts into a temporary directory first. It rejects absolute paths, parent-directory traversal, symbolic links, hard links, and special TAR entries. It checks for output-name collisions before moving extracted content into the destination.

This is intentionally stricter than blindly running tar -xvf on an untrusted archive. If AI Hub changes its archive format to require links or special entries, the extractor should be reviewed rather than weakening these checks without evidence.

## Commands

~~~bash
# Download and process immediately
python skills/aihub-access/scripts/aihub.py download dataset 593 \
  --file-ids 51937,51938 --output-dir ./aihub-data

# Download the archive only
python skills/aihub-access/scripts/aihub.py download dataset 593 \
  --archive-only --output-dir ./archives

# Process an existing TAR
python skills/aihub-access/scripts/aihub.py process ./archives/aihub-dataset-593.tar \
  --output-dir ./aihub-data

# Merge split files already extracted
python skills/aihub-access/scripts/aihub.py merge ./aihub-data
~~~

The utility does not delete an existing destination file. Move or rename conflicting outputs yourself after checking their contents.
