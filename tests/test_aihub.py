from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
import unittest.mock
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "aihub-access"
    / "scripts"
    / "aihub.py"
)
spec = importlib.util.spec_from_file_location("aihub", SCRIPT)
assert spec and spec.loader
aihub = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = aihub
spec.loader.exec_module(aihub)


class DownloadErrorHintTests(unittest.TestCase):
    def test_http_403_recommends_manual_approval_check(self) -> None:
        self.assertTrue(aihub._approval_check_recommended(403, ""))

    def test_permission_text_recommends_manual_approval_check(self) -> None:
        self.assertTrue(
            aihub._approval_check_recommended(400, "Dataset download approval required")
        )

    def test_server_error_does_not_suggest_approval_without_evidence(self) -> None:
        self.assertFalse(aihub._approval_check_recommended(500, "Internal server error"))

    def test_http_401_points_to_api_key_first(self) -> None:
        error = aihub.AIHubError(
            "Unauthorized",
            code="download_http_error",
            http_status=401,
            api_key_check_recommended=True,
        )
        payload = error.as_dict()
        self.assertTrue(payload["api_key_check_recommended"])
        self.assertFalse(payload["approval_check_recommended"])
        self.assertIn("AIHUB_API_KEY", payload["next_action"])

    def test_approval_hint_is_explicitly_not_an_approval_status_result(self) -> None:
        error = aihub.AIHubError(
            "Forbidden",
            code="download_access_denied",
            http_status=403,
            approval_check_recommended=True,
        )
        payload = error.as_dict()
        self.assertTrue(payload["approval_check_recommended"])
        self.assertIn("does not currently verify approval status", payload["next_action"])


class MergeTests(unittest.TestCase):
    def test_merges_numeric_offsets_and_removes_parts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "sample.zip.part3").write_bytes(b"def")
            (root / "sample.zip.part0").write_bytes(b"abc")

            outputs = aihub.merge_parts(root)

            self.assertEqual(outputs, [root / "sample.zip"])
            self.assertEqual((root / "sample.zip").read_bytes(), b"abcdef")
            self.assertFalse((root / "sample.zip.part0").exists())
            self.assertFalse((root / "sample.zip.part3").exists())

    def test_rejects_gap_and_retains_parts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "sample.bin.part0"
            second = root / "sample.bin.part9"
            first.write_bytes(b"abc")
            second.write_bytes(b"def")

            with self.assertRaises(aihub.AIHubError):
                aihub.merge_parts(root)

            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertFalse((root / "sample.bin").exists())

    def test_refuses_to_overwrite_merged_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "sample.bin.part0").write_bytes(b"abc")
            target = root / "sample.bin"
            target.write_bytes(b"existing")

            with self.assertRaises(aihub.AIHubError):
                aihub.merge_parts(root)

            self.assertEqual(target.read_bytes(), b"existing")
            self.assertTrue((root / "sample.bin.part0").exists())


class ExtractionTests(unittest.TestCase):
    def test_extracts_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "sample.tar"
            payload = b"hello AI Hub"
            with tarfile.open(archive, "w") as tar:
                info = tarfile.TarInfo("dataset/sample.txt")
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))

            output = root / "out"
            extracted = aihub.safe_extract(archive, output)

            self.assertEqual((output / "dataset" / "sample.txt").read_bytes(), payload)
            self.assertEqual(extracted, [(output / "dataset" / "sample.txt").resolve()])

    def test_extracts_byte_identical_duplicate_member_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "sample.tar"
            payload = b"hello AI Hub"
            with tarfile.open(archive, "w") as tar:
                for _ in range(2):
                    info = tarfile.TarInfo("dataset/sample.txt")
                    info.size = len(payload)
                    tar.addfile(info, io.BytesIO(payload))

            extracted = aihub.safe_extract(archive, root / "out")

            self.assertEqual((root / "out" / "dataset" / "sample.txt").read_bytes(), payload)
            self.assertEqual(len(extracted), 1)

    def test_rejects_conflicting_duplicate_member(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "conflicting.tar"
            with tarfile.open(archive, "w") as tar:
                info = tarfile.TarInfo("dataset/sample.txt")
                info.size = len(b"first")
                tar.addfile(info, io.BytesIO(b"first"))
                info = tarfile.TarInfo("dataset/sample.txt")
                info.size = len(b"second")
                tar.addfile(info, io.BytesIO(b"second"))

            with self.assertRaises(aihub.AIHubError) as context:
                aihub.safe_extract(archive, root / "out")

            self.assertEqual(context.exception.code, "duplicate_archive_path")

    def test_rejects_parent_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "malicious.tar"
            payload = b"do not write"
            with tarfile.open(archive, "w") as tar:
                info = tarfile.TarInfo("../escaped.txt")
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))

            with self.assertRaises(aihub.AIHubError):
                aihub.safe_extract(archive, root / "out")

            self.assertFalse((root / "escaped.txt").exists())


class McpApiTests(unittest.TestCase):
    def setUp(self) -> None:
        # The MCP metadata API requires AIHUB_API_KEY; provide a dummy so the
        # request layer gets past the key check in every test here.
        self._env = unittest.mock.patch.dict(os.environ, {"AIHUB_API_KEY": "test-key"})
        self._env.start()
        self.addCleanup(self._env.stop)

    def _envelope(self, payload: dict) -> "io.BytesIO":
        return io.BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _patch_urlopen(self, payloads: list) -> "unittest.mock._patch":
        responses = [self._envelope(p) for p in payloads]
        return unittest.mock.patch.object(
            aihub.urllib.request,
            "urlopen",
            side_effect=responses,
        )

    def test_search_parses_envelope_and_unwraps_fields(self) -> None:
        envelope = {
            "result": "SUCCESS",
            "data": {"list": {"value": [
                {"dataSetSn": {"value": "71349"}, "dataNm": {"value": "감성 음성합성"}},
            ]}},
            "totalCount": {"총 개수": 412},
        }
        with self._patch_urlopen([envelope]) as mock_open:
            result = aihub.mcp_search({"keyword": "음성"}, limit=2, offset=0)
        self.assertEqual(result["total_count"], 412)
        self.assertEqual(result["items"], [{"dataSetSn": "71349", "dataNm": "감성 음성합성"}])
        called_url = mock_open.call_args[0][0].full_url
        self.assertIn("dataSetList.do", called_url)
        self.assertIn("searchKeyword=%EC%9D%8C%EC%84%B1", called_url)
        self.assertIn("recordCountPerPage=2", called_url)

    def test_request_mcp_sends_official_tool_name_header(self) -> None:
        # The backend rejects requests without a recognized X-MCP-Tool value
        # ("잘못된 접근입니다"), so every call must carry one.
        envelope = {"result": "SUCCESS", "totalCount": {"총 개수": 1}}
        with self._patch_urlopen([envelope]) as mock_open:
            aihub.mcp_count({})
        request = mock_open.call_args[0][0]
        self.assertEqual(request.headers.get("X-mcp-tool"), "countDataSets")

    def test_count_uses_count_endpoint_without_paging(self) -> None:
        envelope = {"result": "SUCCESS", "totalCount": {"총 개수": 7}}
        with self._patch_urlopen([envelope]) as mock_open:
            result = aihub.mcp_count({"keyword": "음성"})
        self.assertEqual(result, {"total_count": 7})
        called_url = mock_open.call_args[0][0].full_url
        self.assertIn("dataSetCnt.do", called_url)
        self.assertNotIn("recordCountPerPage", called_url)

    def test_fail_envelope_raises_and_points_at_key(self) -> None:
        envelope = {
            "result": "FAIL",
            "message": "잘못된 접근입니다.",
            "guideUrl": "https://aihub.or.kr/devsport/apishell/list.do",
        }
        with self._patch_urlopen([envelope]):
            with self.assertRaises(aihub.AIHubError) as context:
                aihub.mcp_search({})
        self.assertEqual(context.exception.code, "mcp_request_failed")
        self.assertTrue(context.exception.api_key_check_recommended)

    def test_missing_key_is_rejected_before_any_request(self) -> None:
        self._env.stop()
        self._env = unittest.mock.patch.dict(os.environ, {}, clear=True)
        self._env.start()
        with unittest.mock.patch.object(aihub.urllib.request, "urlopen") as mock_open:
            with self.assertRaises(aihub.AIHubError) as context:
                aihub.mcp_search({})
        self.assertEqual(context.exception.code, "missing_api_key")
        mock_open.assert_not_called()

    def test_detail_unwraps_korean_sections(self) -> None:
        envelope = {
            "result": "SUCCESS",
            "data": {
                "주요 정보": {"dataNm": {"value": "감성 음성합성"}, "url": {"value": "https://aihub.or.kr/"}},
                "데이터 개요": {"dataIntrcn": {"value": "<p>소개</p>"}},
            },
        }
        with self._patch_urlopen([envelope]):
            result = aihub.mcp_detail("71349")
        self.assertEqual(result["주요 정보"]["dataNm"], "감성 음성합성")
        self.assertEqual(result["데이터 개요"]["dataIntrcn"], "<p>소개</p>")

    def test_detail_rejects_non_numeric_sn(self) -> None:
        with self.assertRaises(aihub.AIHubError) as context:
            aihub.mcp_detail("abc")
        self.assertEqual(context.exception.code, "invalid_identifier")

    def test_describe_strips_html_and_picks_exact_name(self) -> None:
        list_envelope = {
            "result": "SUCCESS",
            "data": {"list": {"value": [
                {"dataSetSn": {"value": "1"}, "dataNm": {"value": "다른 데이터"}},
                {"dataSetSn": {"value": "71349"}, "dataNm": {"value": "감성 및 발화 스타일 음성합성"}},
            ]}},
        }
        detail_envelope = {
            "result": "SUCCESS",
            "data": {
                "주요 정보": {
                    "dataNm": {"value": "감성 및 발화 스타일 음성합성"},
                    "url": {"value": "https://aihub.or.kr/71349"},
                    "dataRealmNm": {"value": "음성"},
                    "rdcnt": {"value": "123"},
                },
                "데이터 개요": {"dataIntrcn": {"value": "&nbsp;<b>오디오</b>&nbsp;데이터"}},
            },
        }
        with self._patch_urlopen([list_envelope, detail_envelope]) as mock_open:
            result = aihub.mcp_describe("감성 및 발화 스타일 음성합성")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["dataSetSn"], "71349")
        self.assertEqual(result["dataIntrcn"], "오디오 데이터")
        self.assertEqual(mock_open.call_count, 2)

    def test_describe_returns_none_without_hits(self) -> None:
        envelope = {"result": "SUCCESS", "data": {"list": {"value": []}}}
        with self._patch_urlopen([envelope]):
            self.assertIsNone(aihub.mcp_describe("없는 데이터"))

    def test_guides_maps_manual_and_guide_counts(self) -> None:
        envelope = {
            "result": "SUCCESS",
            "data": {
                "cnt": {"value": [
                    {"FILESE001": {"value": 210}, "FILESE002": {"value": 95}},
                ]},
                "list": {"value": [{"dataNm": {"value": "데이터 설명서 보유"}}]},
            },
        }
        with self._patch_urlopen([envelope]) as mock_open:
            result = aihub.mcp_guides("any", limit=5)
        self.assertEqual(result["counts"], {"manual": 210, "guide": 95})
        self.assertEqual(result["items"], [{"dataNm": "데이터 설명서 보유"}])
        called_url = mock_open.call_args[0][0].full_url
        self.assertIn("srchGuideFileSe=ANY", called_url)


if __name__ == "__main__":
    unittest.main()
