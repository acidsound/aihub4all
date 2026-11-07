#!/usr/bin/env python3
"""AI Hub dataset discovery, download, and archive processing utility.

Uses only the Python standard library. Live API behavior should be verified
against the current AI Hub service before production use.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Iterable

API_BASE = "https://api.aihub.or.kr"
DOWNLOAD_VERSION = "0.6"
USER_AGENT = "AIHub4All/0.1.0 (+https://github.com/acidsound/aihub4all)"
PART_RE = re.compile(r"^(?P<base>.+)\.part(?P<offset>[0-9]+)$")
CHUNK_SIZE = 1024 * 1024


class AIHubError(RuntimeError):
    """An API, archive, or local processing error."""


def _read_text(response: object) -> str:
    return response.read().decode("utf-8-sig", errors="replace")  # type: ignore[attr-defined]


def request_metadata(path: str) -> None:
    url = API_BASE + path
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = _read_text(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AIHubError(f"Metadata request failed (HTTP {exc.code}): {body[:2000]}") from exc
    except urllib.error.URLError as exc:
        raise AIHubError(f"Could not connect to AI Hub: {exc.reason}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        print(body)
    else:
        print(json.dumps(parsed, ensure_ascii=False, indent=2))


def _api_key() -> str:
    key = os.environ.get("AIHUB_API_KEY", "").strip()
    if not key:
        raise AIHubError(
            "AIHUB_API_KEY is not set. Configure it in your own shell environment; "
            "do not paste the key into chat or commit it to a file."
        )
    return key


def _download_url(kind: str, key: str, file_ids: str | None) -> str:
    if not key.isdigit():
        raise AIHubError("Dataset and package keys must contain digits only.")
    if file_ids:
        ids = [item.strip() for item in file_ids.split(",")]
        if not ids or any(not item.isdigit() for item in ids):
            raise AIHubError("File IDs must be comma-separated numeric identifiers.")
        selector = ",".join(ids)
    else:
        selector = "all"

    if kind == "dataset":
        route = f"/down/{DOWNLOAD_VERSION}/{key}.do"
    else:
        route = f"/down/pckage/{DOWNLOAD_VERSION}/{key}.do"
    return API_BASE + route + "?" + urllib.parse.urlencode({"fileSn": selector})


def _stream_download(url: str, destination: Path, api_key: str) -> None:
    request = urllib.request.Request(
        url,
        headers={"apikey": api_key, "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            expected = response.headers.get("Content-Length")
            total = int(expected) if expected and expected.isdigit() else None
            written = 0
            with destination.open("xb") as output:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)
                    written += len(chunk)
                    if total:
                        percent = min(100, written * 100 // total)
                        print(
                            f"\rDownloaded {written:,} / {total:,} bytes ({percent}%)",
                            end="",
                            flush=True,
                        )
                    else:
                        print(f"\rDownloaded {written:,} bytes", end="", flush=True)
        print()
        if total is not None and written != total:
            raise AIHubError(
                f"Download size mismatch: received {written} bytes; expected {total}. "
                f"Partial response retained at {destination}."
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AIHubError(
            f"AI Hub download failed (HTTP {exc.code}): {body[:2000]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise AIHubError(
            f"Download connection failed: {exc.reason}. "
            f"Any partial response is retained for inspection at {destination}."
        ) from exc


def _safe_member_path(root: Path, member_name: str) -> Path:
    if not member_name or "\\" in member_name:
        raise AIHubError(f"Unsafe TAR member path: {member_name!r}")
    relative = PurePosixPath(member_name)
    if relative.is_absolute() or any(part in ("..", ".") for part in relative.parts):
        raise AIHubError(f"Unsafe TAR member path: {member_name!r}")
    if relative.parts and re.match(r"^[A-Za-z]:", relative.parts[0]):
        raise AIHubError(f"Unsafe TAR member path: {member_name!r}")

    root_resolved = root.resolve()
    destination = root.joinpath(*relative.parts).resolve()
    try:
        destination.relative_to(root_resolved)
    except ValueError as exc:
        raise AIHubError(f"TAR member escapes extraction directory: {member_name!r}") from exc
    return destination


def safe_extract(archive: Path, destination: Path) -> None:
    """Extract only regular files/directories and reject path/link attacks."""
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive, mode="r:*") as tar:
            members = tar.getmembers()
            file_paths: set[Path] = set()
            for member in members:
                target = _safe_member_path(destination, member.name)
                if not (member.isdir() or member.isfile()):
                    raise AIHubError(
                        f"Unsupported TAR entry type for {member.name!r}; "
                        "links and special files are rejected."
                    )
                if member.isfile():
                    if target in file_paths:
                        raise AIHubError(f"Duplicate TAR file path: {member.name!r}")
                    file_paths.add(target)

            for member in members:
                target = _safe_member_path(destination, member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    raise AIHubError(f"Could not read TAR member: {member.name!r}")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=CHUNK_SIZE)
    except (tarfile.TarError, OSError) as exc:
        if isinstance(exc, AIHubError):
            raise
        raise AIHubError(f"Could not safely extract {archive}: {exc}") from exc


def merge_parts(directory: Path) -> list[Path]:
    """Merge .part<byte-offset> files recursively and remove parts on success."""
    if not directory.is_dir():
        raise AIHubError(f"Not a directory: {directory}")

    groups: dict[tuple[Path, str], list[tuple[int, Path]]] = {}
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        match = PART_RE.match(path.name)
        if match:
            key = (path.parent, match.group("base"))
            groups.setdefault(key, []).append((int(match.group("offset")), path))

    merged: list[Path] = []
    for (parent, base), parts in sorted(groups.items(), key=lambda item: str(item[0])):
        ordered = sorted(parts, key=lambda item: item[0])
        target = parent / base
        if target.exists():
            raise AIHubError(f"Refusing to overwrite existing merged file: {target}")
        if ordered[0][0] != 0:
            raise AIHubError(
                f"Split file group {target} starts at offset {ordered[0][0]}, not 0. "
                "All parts were retained."
            )

        temporary: Path | None = None
        total_written = 0
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{base}.merge-",
                suffix=".tmp",
                dir=parent,
                delete=False,
            ) as output:
                temporary = Path(output.name)
                for offset, part_path in ordered:
                    if offset != total_written:
                        raise AIHubError(
                            f"Non-contiguous split parts for {target}: "
                            f"{part_path.name} starts at {offset}, expected {total_written}. "
                            "All parts were retained."
                        )
                    with part_path.open("rb") as source:
                        while True:
                            chunk = source.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            output.write(chunk)
                            total_written += len(chunk)
                output.flush()
                os.fsync(output.fileno())

            # The destination was checked above; os.replace commits the completed file.
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

        for _, part_path in ordered:
            part_path.unlink()
        merged.append(target)
        print(f"Merged {len(ordered)} parts -> {target} ({total_written:,} bytes)")

    if not merged:
        print(f"No split-part files found under {directory}")
    return merged


def process_archive(
    archive: Path,
    output_dir: Path,
    *,
    remove_archive: bool = False,
) -> list[Path]:
    archive = archive.expanduser().resolve()
    if not archive.is_file() or not tarfile.is_tarfile(archive):
        raise AIHubError(f"Not a readable TAR archive: {archive}")

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []

    with tempfile.TemporaryDirectory(prefix=".aihub-extract-", dir=output_dir) as temp_name:
        staging = Path(temp_name)
        safe_extract(archive, staging)
        merge_parts(staging)

        staged_items = list(staging.iterdir())
        collisions = [output_dir / item.name for item in staged_items if (output_dir / item.name).exists()]
        if collisions:
            names = ", ".join(str(path) for path in collisions)
            raise AIHubError(f"Refusing to overwrite existing output paths: {names}")

        for item in staged_items:
            destination = output_dir / item.name
            shutil.move(str(item), str(destination))
            moved.append(destination)

    if remove_archive:
        archive.unlink()
    print(f"Extracted {len(moved)} top-level item(s) into {output_dir}")
    return moved


def download(
    kind: str,
    key: str,
    file_ids: str | None,
    output_dir: Path,
    *,
    archive_only: bool,
    keep_archive: bool,
) -> None:
    api_key = _api_key()
    url = _download_url(kind, key, file_ids)
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    archive = output_dir / f"aihub-{kind}-{key}.tar"
    partial = archive.with_suffix(archive.suffix + ".partial")
    if archive.exists() or partial.exists():
        raise AIHubError(
            f"Output archive already exists: {archive} or {partial}. "
            "Choose another output directory or inspect the existing file."
        )

    print(f"Requesting {kind} {key}; file selection: {file_ids or 'all'}")
    print(f"Destination: {archive}")
    _stream_download(url, partial, api_key)

    if not tarfile.is_tarfile(partial):
        preview = partial.read_bytes()[:1000].decode("utf-8", errors="replace")
        raise AIHubError(
            f"The response is not a readable TAR archive. The response was retained at "
            f"{partial}. Response preview:\n{preview}"
        )

    os.replace(partial, archive)
    print(f"Archive downloaded: {archive}")
    if archive_only:
        return

    process_archive(archive, output_dir, remove_archive=not keep_archive)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover, download, and process AI Hub datasets and data packages."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("datasets", help="List datasets")
    dataset = sub.add_parser("dataset", help="Show a dataset's file tree")
    dataset.add_argument("key")

    sub.add_parser("packages", help="List data packages")
    package = sub.add_parser("package", help="Show a data package's file tree")
    package.add_argument("key")

    get_download = sub.add_parser("download", help="Download a dataset or package")
    get_download.add_argument("kind", choices=("dataset", "package"))
    get_download.add_argument("key")
    get_download.add_argument("--file-ids", help="Comma-separated file IDs; omit for all files")
    get_download.add_argument("--output-dir", type=Path, default=Path("."))
    get_download.add_argument("--archive-only", action="store_true", help="Keep TAR without extraction")
    get_download.add_argument("--keep-archive", action="store_true", help="Keep TAR after extraction")

    process = sub.add_parser("process", help="Safely extract a previously downloaded TAR")
    process.add_argument("archive", type=Path)
    process.add_argument("--output-dir", type=Path, default=Path("."))
    process.add_argument("--keep-archive", action="store_true")

    merge = sub.add_parser("merge", help="Merge split files in an extracted directory")
    merge.add_argument("directory", type=Path)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "datasets":
            request_metadata("/info/dataset.do")
        elif args.command == "dataset":
            if not args.key.isdigit():
                raise AIHubError("Dataset key must contain digits only.")
            request_metadata(f"/info/{args.key}.do")
        elif args.command == "packages":
            request_metadata("/info/datapckage.do")
        elif args.command == "package":
            if not args.key.isdigit():
                raise AIHubError("Package key must contain digits only.")
            request_metadata(f"/info/pckage/{args.key}.do")
        elif args.command == "download":
            if not args.key.isdigit():
                raise AIHubError("Dataset/package key must contain digits only.")
            download(
                args.kind,
                args.key,
                args.file_ids,
                args.output_dir,
                archive_only=args.archive_only,
                keep_archive=args.keep_archive,
            )
        elif args.command == "process":
            process_archive(
                args.archive,
                args.output_dir,
                remove_archive=not args.keep_archive,
            )
        elif args.command == "merge":
            merge_parts(args.directory)
        return 0
    except (AIHubError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
