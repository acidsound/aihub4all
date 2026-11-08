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
MCP_BASE = "https://aihub.or.kr/mcp/"
MCP_KEY_HEADER = "X-API-KEY"
# The backend rejects requests that do not carry one of the official MCP
# tool names in X-MCP-Tool ("잘못된 접근입니다", live-tested 2026-11-08).
MCP_TOOL_HEADER = "X-MCP-Tool"
MCP_TOOL_NAMES = {
    "list": "searchDataSets",
    "count": "countDataSets",
    "detail": "getDataSet",
    "guides": "getDataSetsWithGuide",
}
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


def request_mcp(path: str, params: dict[str, Any], mcp_tool: str) -> dict[str, Any]:
    """Call an AI Hub MCP metadata endpoint and return the raw envelope.

    mcp_tool must be one of the official tool names; the backend rejects
    requests whose X-MCP-Tool value it does not recognize.
    """
    api_key = _api_key()
    url = MCP_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            MCP_KEY_HEADER: api_key,
            MCP_TOOL_HEADER: mcp_tool,
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = _read_text(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AIHubError(
            f"MCP request failed (HTTP {exc.code}): {body[:2000]}",
            code="mcp_http_error",
            http_status=exc.code,
            response_excerpt=body[:1000] or None,
        ) from exc
    except urllib.error.URLError as exc:
        raise AIHubError(
            f"Could not connect to AI Hub MCP: {exc.reason}",
            code="network_error",
        ) from exc

    try:
        envelope = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AIHubError(
            f"MCP response was not valid JSON: {body[:500]}",
            code="unexpected_response",
        ) from exc
    if not isinstance(envelope, dict):
        raise AIHubError(
            f"Unexpected MCP response shape: {body[:500]}",
            code="unexpected_response",
        )

    if str(envelope.get("result", "")).strip().upper() == "FAIL":
        message = str(envelope.get("message") or "AI Hub MCP request failed")
        guide_url = envelope.get("guide_url") or envelope.get("guideUrl")
        raise AIHubError(
            f"{message}{' See ' + str(guide_url) if guide_url else ''}",
            code="mcp_request_failed",
            api_key_check_recommended="키" in message or "접근" in message,
            response_excerpt=str(guide_url) if guide_url else None,
        )
    return envelope


def unwrap_field(node: Any) -> Any:
    """Strip the {value, label, description} wrappers the MCP API uses."""
    if isinstance(node, dict):
        if "value" in node and set(node) <= {"value", "label", "description"}:
            return unwrap_field(node["value"])
        return {key: unwrap_field(value) for key, value in node.items()}
    if isinstance(node, list):
        return [unwrap_field(item) for item in node]
    return node


def _mcp_total_count(envelope: dict[str, Any]) -> int | None:
    total = envelope.get("totalCount")
    if isinstance(total, dict):
        count = total.get("총 개수")
        if isinstance(count, int):
            return count
    return None


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


MCP_SEARCH_PARAMS = (
    ("keyword", "searchKeyword"),
    ("realm_code", "srchDataRealmCode"),
    ("class_code", "srchdataClCode"),
    ("class_detail_code", "srchDataClDetailCode"),
    ("data_type", "srchOneDataTy"),
    ("year", "srchOneDataCnstcYear"),
    ("detail_condition", "srchDetailCnd"),
)
GUIDE_FILE_SE = {"manual": "FILESE001", "guide": "FILESE002", "any": "ANY"}
_HTML_TAG_RE = re.compile(r"(?s)<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _search_params(filters: dict[str, Any]) -> dict[str, str]:
    params: dict[str, str] = {}
    for arg_name, query_name in MCP_SEARCH_PARAMS:
        value = filters.get(arg_name)
        if value:
            params[query_name] = str(value)
    return params


def mcp_search(
    filters: dict[str, Any],
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    params = _search_params(filters)
    if limit is not None:
        params["recordCountPerPage"] = str(limit)
    if offset is not None:
        params["firstIndex"] = str(offset)
    envelope = request_mcp("dataSetList.do", params, MCP_TOOL_NAMES["list"])
    data = envelope.get("data")
    rows = data.get("list") if isinstance(data, dict) else None
    items = rows.get("value") if isinstance(rows, dict) else None
    return {
        "total_count": _mcp_total_count(envelope),
        "items": unwrap_field(items or []),
    }


def mcp_count(filters: dict[str, Any]) -> dict[str, Any]:
    envelope = request_mcp("dataSetCnt.do", _search_params(filters), MCP_TOOL_NAMES["count"])
    return {"total_count": _mcp_total_count(envelope)}


def mcp_detail(data_set_sn: str) -> dict[str, Any]:
    if not data_set_sn.isdigit():
        raise AIHubError("dataSetSn must contain digits only.", code="invalid_identifier")
    envelope = request_mcp("dataSetDetail.do", {"dataSetSn": data_set_sn}, MCP_TOOL_NAMES["detail"])
    return unwrap_field(envelope.get("data") or {})


def _plain_text(value: Any, cap: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value
    for _ in range(2):
        text = _HTML_TAG_RE.sub(" ", text)
        text = (
            text.replace("&nbsp;", " ")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&amp;", "&")
        )
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if len(text) > cap:
        text = text[:cap].strip() + "…"
    return text or None


def mcp_describe(name: str) -> dict[str, Any] | None:
    """Find the best-matching dataset by name and return a compact summary."""
    cleaned = (name or "").strip()
    if not cleaned:
        raise AIHubError("Dataset name is required.", code="invalid_argument")
    keyword = _WHITESPACE_RE.sub("%", cleaned)
    search = mcp_search({"keyword": keyword}, limit=8, offset=0)
    items = search["items"]
    if not items:
        return None
    normalized = _WHITESPACE_RE.sub(" ", cleaned).lower()
    best = next(
        (
            item
            for item in items
            if isinstance(item, dict)
            and _WHITESPACE_RE.sub(" ", str(item.get("dataNm") or "")).lower() == normalized
        ),
        items[0],
    )
    sn = str(best.get("dataSetSn") or "").strip() if isinstance(best, dict) else ""
    if not sn.isdigit():
        raise AIHubError("Search hit did not carry a numeric dataSetSn.", code="unexpected_response")
    detail = mcp_detail(sn)
    core = detail.get("주요 정보") or {}
    summary = detail.get("데이터 개요") or {}
    annotation = detail.get("어노테이션 포맷 및 데이터 구조") or {}
    return {
        "dataSetSn": sn,
        "url": core.get("url"),
        "dataNm": core.get("dataNm"),
        "dataIntrcn": _plain_text(summary.get("dataIntrcn"), 1000),
        "cnstcPurps": _plain_text(summary.get("cnstcPurps"), 1000),
        "detailDataDc": _plain_text(annotation.get("detailDataDc"), 1500),
        "dataRealmNm": core.get("dataRealmNm"),
        "main_keywords": core.get("aiLrnDataMainKwrds"),
        "data_types": core.get("dataTys"),
        "data_cnstc_year": core.get("dataCnstcYear"),
        "read_count": core.get("rdcnt"),
    }


def mcp_guides(guide_type: str = "any", limit: int = 10) -> dict[str, Any]:
    file_se = GUIDE_FILE_SE.get(guide_type, "ANY")
    params = {
        "srchGuideFileSe": file_se,
        "firstIndex": "0",
        "recordCountPerPage": str(max(1, min(limit, 200))),
    }
    envelope = request_mcp("getDataSetsWithGuide.do", params, MCP_TOOL_NAMES["guides"])
    raw_data = envelope.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    counts: dict[str, Any] = {}
    cnt_node = data.get("cnt")
    raw_counts = cnt_node.get("value") if isinstance(cnt_node, dict) else None
    for entry in raw_counts or []:
        if isinstance(entry, dict):
            for key, field in entry.items():
                if key in GUIDE_FILE_SE.values() and isinstance(field, dict):
                    counts[key] = field.get("value")
    list_node = data.get("list")
    items = list_node.get("value") if isinstance(list_node, dict) else None
    return {
        "counts": {
            "manual": counts.get("FILESE001"),
            "guide": counts.get("FILESE002"),
        },
        "items": unwrap_field(items or []),
    }


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

    search = sub.add_parser(
        "search",
        help="Search datasets by keyword and filters (AI Hub MCP metadata API)",
    )
    _add_search_filters(search)
    search.add_argument("--limit", type=int, default=10, help="Rows per page (default 10)")
    search.add_argument("--offset", type=int, default=0, help="Paging offset (default 0)")

    count = sub.add_parser(
        "count",
        help="Count datasets matching keyword and filters (AI Hub MCP metadata API)",
    )
    _add_search_filters(count)

    mcp_detail_parser = sub.add_parser(
        "detail",
        help="Show full metadata for one dataset by dataSetSn (AI Hub MCP metadata API)",
    )
    mcp_detail_parser.add_argument("data_set_sn")

    describe = sub.add_parser(
        "describe",
        help="Look up a dataset by name and summarize it (AI Hub MCP metadata API)",
    )
    describe.add_argument("name")

    guides = sub.add_parser(
        "guides",
        help="List datasets that ship data manuals or build guides (AI Hub MCP metadata API)",
    )
    guides.add_argument("--type", choices=("manual", "guide", "any"), default="any")
    guides.add_argument("--limit", type=int, default=10)

    return parser


def _add_search_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--keyword", help="Free-text keyword (name, content, keyword fields)")
    parser.add_argument("--realm-code", help="Data realm code (e.g. Korean, culture/tourism)")
    parser.add_argument("--class-code", help="Data classification code")
    parser.add_argument("--class-detail-code", help="Data detail classification code")
    parser.add_argument("--data-type", help="Data type (e.g. text, image)")
    parser.add_argument("--year", help="Construction year")
    parser.add_argument("--detail-condition", help="Detail condition (sample data, safety zone)")


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
        elif args.command in ("search", "count"):
            filters = {
                "keyword": args.keyword,
                "realm_code": args.realm_code,
                "class_code": args.class_code,
                "class_detail_code": args.class_detail_code,
                "data_type": args.data_type,
                "year": args.year,
                "detail_condition": args.detail_condition,
            }
            if args.command == "search":
                data = mcp_search(filters, limit=args.limit, offset=args.offset)
            else:
                data = mcp_count(filters)
            result = {"command": args.command, **data}
        elif args.command == "detail":
            data = mcp_detail(args.data_set_sn)
            result = {"command": args.command, "data_set_sn": args.data_set_sn, "data": data}
        elif args.command == "describe":
            data = mcp_describe(args.name)
            result = {"command": args.command, "found": data is not None, "data": data}
        elif args.command == "guides":
            data = mcp_guides(args.type, args.limit)
            result = {"command": args.command, **data}
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
        elif args.command in ("download", "process", "search", "count", "detail", "describe", "guides"):
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
