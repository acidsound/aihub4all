#!/usr/bin/env python3
"""AI Hub dataset discovery, download, and archive processing utility.

Uses only the Python standard library. Live API behavior should be verified
against the current AI Hub service before production use.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
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
from typing import Any, Iterable, TextIO

API_BASE = "https://api.aihub.or.kr"
DOWNLOAD_VERSION = "0.6"
USER_AGENT = "AIHub4All/0.1.0 (+https://github.com/acidsound/aihub4all)"
PART_RE = re.compile(r"^(?P<base>.+)\.part(?P<offset>[0-9]+)$")
CHUNK_SIZE = 1024 * 1024
APPROVAL_HINT_RE = re.compile(
    r"approval|approved|permission|authorized|forbidden|access.denied|"
    r"not.allowed|not.permitted|승인|권한|신청|허가",
    re.IGNORECASE,
)


class AIHubError(RuntimeError):
    """An API, archive, or local processing error with machine-readable context."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "aihub_error",
        http_status: int | None = None,
        approval_check_recommended: bool = False,
        api_key_check_recommended: bool = False,
        response_excerpt: str | None = None,
        partial_file: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.approval_check_recommended = approval_check_recommended
        self.api_key_check_recommended = api_key_check_recommended
        self.response_excerpt = response_excerpt
        self.partial_file = partial_file

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
        }
        if self.http_status is not None:
            result["http_status"] = self.http_status
        result["approval_check_recommended"] = self.approval_check_recommended
        result["api_key_check_recommended"] = self.api_key_check_recommended
        if self.response_excerpt:
            result["response_excerpt"] = self.response_excerpt
        if self.partial_file:
            result["partial_file"] = str(self.partial_file)
        if self.approval_check_recommended:
            result["next_action"] = (
                "Check in your AI Hub account whether the download request for this "
                "dataset or package has been submitted and approved. AIHub4All does "
                "not currently verify approval status through an API."
            )
        elif self.api_key_check_recommended:
            result["next_action"] = (
                "Check that AIHUB_API_KEY is present, valid, and belongs to the "
                "intended AI Hub account."
            )
        return result


def _approval_check_recommended(http_status: int | None, response_text: str) -> bool:
    """Return a cautious hint, not a determination that approval is missing."""
    return http_status == 403 or bool(APPROVAL_HINT_RE.search(response_text or ""))


def _read_text(response: object) -> str:
    return response.read().decode("utf-8-sig", errors="replace")  # type: ignore[attr-defined]


def _print_progress(message: str, stream: TextIO) -> None:
    print(message, file=stream, flush=True)


def _looks_like_generated_error_page(body: str) -> bool:
    """Heuristic: gateway error pages are HTML; AI Hub payloads are plain text."""
    head = (body or "").lstrip()[:512].lower()
    return head.startswith("<") or "<html" in head or "<!doctype" in head


def request_metadata(path: str) -> Any:
    url = API_BASE + path
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = _read_text(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        # The AI Hub front proxy answers /info metadata requests with HTTP
        # 502 or 503 while still delivering the complete response body. The
        # status alone is therefore not proof of failure; accept the body
        # only when it is clearly content rather than a generated error page.
        if (
            exc.code not in (502, 503)
            or not body.strip()
            or _looks_like_generated_error_page(body)
        ):
            raise AIHubError(
                f"Metadata request failed (HTTP {exc.code}): {body[:2000]}",
                code="metadata_http_error",
                http_status=exc.code,
                response_excerpt=body[:1000] or None,
            ) from exc
    except urllib.error.URLError as exc:
        raise AIHubError(
            f"Could not connect to AI Hub: {exc.reason}",
            code="network_error",
        ) from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def _api_key() -> str:
    key = os.environ.get("AIHUB_API_KEY", "").strip()
    if not key:
        raise AIHubError(
            "AIHUB_API_KEY is not set. Configure it in your own shell environment; "
            "do not paste the key into chat or commit it to a file.",
            code="missing_api_key",
            api_key_check_recommended=True,
        )
    return key


def _download_url(kind: str, key: str, file_ids: str | None) -> str:
    if not key.isdigit():
        raise AIHubError("Dataset and package keys must contain digits only.", code="invalid_identifier")
    if file_ids:
        ids = [item.strip() for item in file_ids.split(",")]
        if not ids or any(not item.isdigit() for item in ids):
            raise AIHubError(
                "File IDs must be comma-separated numeric identifiers.",
                code="invalid_file_selection",
            )
        selector = ",".join(ids)
    else:
        selector = "all"

    if kind == "dataset":
        route = f"/down/{DOWNLOAD_VERSION}/{key}.do"
    else:
        route = f"/down/pckage/{DOWNLOAD_VERSION}/{key}.do"
    return API_BASE + route + "?" + urllib.parse.urlencode({"fileSn": selector})


def _stream_download(
    url: str,
    destination: Path,
    api_key: str,
    *,
    progress_stream: TextIO,
) -> int:
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
                            file=progress_stream,
                            flush=True,
                        )
                    else:
                        print(
                            f"\rDownloaded {written:,} bytes",
                            end="",
                            file=progress_stream,
                            flush=True,
                        )
        _print_progress("", progress_stream)
        if total is not None and written != total:
            raise AIHubError(
                f"Download size mismatch: received {written} bytes; expected {total}.",
                code="incomplete_download",
                partial_file=destination,
            )
        return written
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        approval_hint = _approval_check_recommended(exc.code, body)
        raise AIHubError(
            f"AI Hub download request failed (HTTP {exc.code}).",
            code="download_access_denied" if approval_hint else "download_http_error",
            http_status=exc.code,
            approval_check_recommended=approval_hint,
            api_key_check_recommended=exc.code == 401,
            response_excerpt=body[:1000] or None,
        ) from exc
    except urllib.error.URLError as exc:
        raise AIHubError(
            f"Download connection failed: {exc.reason}.",
            code="download_network_error",
            partial_file=destination if destination.exists() else None,
        ) from exc
    except http.client.HTTPException as exc:
        raise AIHubError(
            f"Download stream was interrupted: {exc}.",
            code="download_interrupted",
            partial_file=destination if destination.exists() else None,
        ) from exc


def _safe_member_path(root: Path, member_name: str) -> Path:
    if not member_name or "\\" in member_name:
        raise AIHubError(f"Unsafe TAR member path: {member_name!r}", code="unsafe_archive")
    relative = PurePosixPath(member_name)
    if relative.is_absolute() or any(part in ("..", ".") for part in relative.parts):
        raise AIHubError(f"Unsafe TAR member path: {member_name!r}", code="unsafe_archive")
    if relative.parts and re.match(r"^[A-Za-z]:", relative.parts[0]):
        raise AIHubError(f"Unsafe TAR member path: {member_name!r}", code="unsafe_archive")

    root_resolved = root.resolve()
    destination = root.joinpath(*relative.parts).resolve()
    try:
        destination.relative_to(root_resolved)
    except ValueError as exc:
        raise AIHubError(
            f"TAR member escapes extraction directory: {member_name!r}",
            code="unsafe_archive",
        ) from exc
    return destination


def _member_md5(tar: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    source = tar.extractfile(member)
    if source is None:
        raise AIHubError(f"Could not read TAR member: {member.name!r}", code="archive_read_error")
    digest = hashlib.md5()
    while True:
        chunk = source.read(CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def safe_extract(archive: Path, destination: Path) -> list[Path]:
    """Extract only regular files/directories and reject path/link attacks."""
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    try:
        with tarfile.open(archive, mode="r:*") as tar:
            members = tar.getmembers()
            first_by_path: dict[Path, tarfile.TarInfo] = {}
            skipped: set[int] = set()
            for index, member in enumerate(members):
                target = _safe_member_path(destination, member.name)
                if not (member.isdir() or member.isfile()):
                    raise AIHubError(
                        f"Unsupported TAR entry type for {member.name!r}; "
                        "links and special files are rejected.",
                        code="unsupported_archive_entry",
                    )
                if not member.isfile():
                    continue
                previous = first_by_path.get(target)
                if previous is None:
                    first_by_path[target] = member
                    continue
                # AI Hub TARs list the same file more than once. Accept the
                # duplicate only when both copies are byte-identical; content
                # that differs under one path stays an error.
                if previous.size != member.size or _member_md5(tar, previous) != _member_md5(tar, member):
                    raise AIHubError(
                        f"Duplicate TAR file path with conflicting content: {member.name!r}",
                        code="duplicate_archive_path",
                    )
                skipped.add(index)

            for index, member in enumerate(members):
                if index in skipped:
                    continue
                target = _safe_member_path(destination, member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    raise AIHubError(
                        f"Could not read TAR member: {member.name!r}",
                        code="archive_read_error",
                    )
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=CHUNK_SIZE)
                extracted.append(target)
    except (tarfile.TarError, OSError) as exc:
        raise AIHubError(
            f"Could not safely extract {archive}: {exc}",
            code="archive_extraction_error",
        ) from exc
    return extracted


def merge_parts(directory: Path) -> list[Path]:
    """Merge .part<byte-offset> files recursively and remove parts on success."""
    if not directory.is_dir():
        raise AIHubError(f"Not a directory: {directory}", code="invalid_directory")

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
            raise AIHubError(
                f"Refusing to overwrite existing merged file: {target}",
                code="output_exists",
            )
        if ordered[0][0] != 0:
            raise AIHubError(
                f"Split file group {target} starts at offset {ordered[0][0]}, not 0. "
                "All parts were retained.",
                code="split_part_gap",
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
                            "All parts were retained.",
                            code="split_part_gap",
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

    return merged


def process_archive(
    archive: Path,
    output_dir: Path,
    *,
    remove_archive: bool = False,
) -> dict[str, Any]:
    archive = archive.expanduser().resolve()
    if not archive.is_file() or not tarfile.is_tarfile(archive):
        raise AIHubError(f"Not a readable TAR archive: {archive}", code="invalid_archive")

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted_paths: list[Path] = []
    merged_paths: list[Path] = []

    with tempfile.TemporaryDirectory(prefix=".aihub-extract-", dir=output_dir) as temp_name:
        staging = Path(temp_name)
        safe_extract(archive, staging)
        merged_paths = merge_parts(staging)

        staged_items = list(staging.iterdir())
        collisions = [output_dir / item.name for item in staged_items if (output_dir / item.name).exists()]
        if collisions:
            names = ", ".join(str(path) for path in collisions)
            raise AIHubError(
                f"Refusing to overwrite existing output paths: {names}",
                code="output_exists",
            )

        for item in staged_items:
            destination = output_dir / item.name
            shutil.move(str(item), str(destination))
            extracted_paths.append(destination)

    if remove_archive:
        archive.unlink()
    return {
        "archive": str(archive),
        "archive_removed": remove_archive,
        "output_dir": str(output_dir),
        "extracted_paths": [str(path) for path in extracted_paths],
        "merged_files": [str(output_dir / path.relative_to(staging)) for path in merged_paths],
    }


def download(
    kind: str,
    key: str,
    file_ids: str | None,
    output_dir: Path,
    *,
    archive_only: bool,
    keep_archive: bool,
    progress_stream: TextIO,
) -> dict[str, Any]:
    api_key = _api_key()
    url = _download_url(kind, key, file_ids)
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    archive = output_dir / f"aihub-{kind}-{key}.tar"
    partial = archive.with_suffix(archive.suffix + ".partial")
    if archive.exists() or partial.exists():
        raise AIHubError(
            f"Output archive already exists: {archive} or {partial}. "
            "Choose another output directory or inspect the existing file.",
            code="output_exists",
        )

    _print_progress(
        f"Requesting {kind} {key}; file selection: {file_ids or 'all'}",
        progress_stream,
    )
    _print_progress(f"Destination: {archive}", progress_stream)
    size = _stream_download(url, partial, api_key, progress_stream=progress_stream)

    if not tarfile.is_tarfile(partial):
        with partial.open("rb") as response_file:
            preview = response_file.read(1000).decode("utf-8", errors="replace")
        approval_hint = _approval_check_recommended(None, preview)
        raise AIHubError(
            "AI Hub returned a successful HTTP response, but it was not a readable TAR archive.",
            code="unexpected_download_response",
            approval_check_recommended=approval_hint,
            response_excerpt=preview[:1000] or None,
            partial_file=partial,
        )

    os.replace(partial, archive)
    result: dict[str, Any] = {
        "kind": kind,
        "key": key,
        "file_ids": file_ids.split(",") if file_ids else "all",
        "archive": str(archive),
        "downloaded_bytes": size,
        "archive_only": archive_only,
    }
    _print_progress(f"Archive downloaded: {archive} ({size:,} bytes)", progress_stream)

    if not archive_only:
        processed = process_archive(
            archive,
            output_dir,
            remove_archive=not keep_archive,
        )
        result["processing"] = processed
    else:
        result["processing"] = None
    result["archive_retained"] = archive.exists()
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover, download, and process AI Hub datasets and data packages."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON result (progress is written to stderr).",
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
    get_download.add_argument("--archive-only", action="store_true", help="Keep TAR without extracting")
    get_download.add_argument("--keep-archive", action="store_true", help="Keep TAR after extraction")

    process = sub.add_parser("process", help="Safely extract a previously downloaded TAR")
    process.add_argument("archive", type=Path)
    process.add_argument("--output-dir", type=Path, default=Path("."))
    process.add_argument("--remove-archive", action="store_true", help="Delete the source TAR after successful processing")

    merge = sub.add_parser("merge", help="Merge split files in an extracted directory")
    merge.add_argument("directory", type=Path)

    return parser


def _emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    progress_stream = sys.stderr if args.json else sys.stdout

    try:
        if args.command == "datasets":
            data = request_metadata("/info/dataset.do")
            result: dict[str, Any] = {"command": args.command, "data": data}
        elif args.command == "dataset":
            if not args.key.isdigit():
                raise AIHubError("Dataset key must contain digits only.", code="invalid_identifier")
            data = request_metadata(f"/info/{args.key}.do")
            result = {"command": args.command, "dataset_key": args.key, "data": data}
        elif args.command == "packages":
            data = request_metadata("/info/datapckage.do")
            result = {"command": args.command, "data": data}
        elif args.command == "package":
            if not args.key.isdigit():
                raise AIHubError("Package key must contain digits only.", code="invalid_identifier")
            data = request_metadata(f"/info/pckage/{args.key}.do")
            result = {"command": args.command, "package_key": args.key, "data": data}
        elif args.command == "download":
            if not args.key.isdigit():
                raise AIHubError("Dataset/package key must contain digits only.", code="invalid_identifier")
            data = download(
                args.kind,
                args.key,
                args.file_ids,
                args.output_dir,
                archive_only=args.archive_only,
                keep_archive=args.keep_archive,
                progress_stream=progress_stream,
            )
            result = {"command": args.command, **data}
        elif args.command == "process":
            data = process_archive(
                args.archive,
                args.output_dir,
                remove_archive=args.remove_archive,
            )
            result = {"command": args.command, **data}
        elif args.command == "merge":
            merged = merge_parts(args.directory)
            result = {
                "command": args.command,
                "directory": str(args.directory.expanduser().resolve()),
                "merged_files": [str(path) for path in merged],
            }
        else:
            parser.error(f"Unknown command: {args.command}")
            return 2

        if args.json:
            _emit_json({"ok": True, **result})
        elif args.command in ("datasets", "dataset", "packages", "package"):
            if isinstance(result["data"], str):
                print(result["data"])
            else:
                print(json.dumps(result["data"], ensure_ascii=False, indent=2))
        elif args.command == "download":
            print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        elif args.command == "process":
            print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
        elif args.command == "merge":
            for path in result["merged_files"]:
                print(f"Merged: {path}")
        return 0
    except AIHubError as exc:
        if args.json:
            _emit_json({
                "ok": False,
                "command": args.command,
                "error": exc.as_dict(),
            })
        else:
            print(f"Error [{exc.code}]: {exc}", file=sys.stderr)
            if exc.approval_check_recommended:
                print(
                    "Next step: check this dataset/package's download approval in your AI Hub account. "
                    "AIHub4All cannot query approval status.",
                    file=sys.stderr,
                )
            elif exc.api_key_check_recommended:
                print("Next step: check your AI Hub API key.", file=sys.stderr)
        return 1
    except OSError as exc:
        error = AIHubError(str(exc), code="local_io_error")
        if args.json:
            _emit_json({"ok": False, "command": args.command, "error": error.as_dict()})
        else:
            print(f"Error [{error.code}]: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
