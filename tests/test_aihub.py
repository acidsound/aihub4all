from __future__ import annotations

import importlib.util
import io
import sys
import tarfile
import tempfile
import unittest
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
            self.assertEqual(extracted, [output / "dataset" / "sample.txt"])

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


if __name__ == "__main__":
    unittest.main()
