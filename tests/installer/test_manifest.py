# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for :mod:`auplc_installer.manifest`.

manifest.json is what flips a tarball into "this is an air-gapped bundle";
making sure read/write stays a faithful round-trip protects offline users
who can't easily roll back a broken bundle.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from auplc_installer.manifest import BundleManifest, detect_offline_bundle


class BundleManifestRoundTripTests(unittest.TestCase):
    def _sample(self) -> BundleManifest:
        return BundleManifest(
            format_version="1",
            build_date="2026-04-29T06:00:00Z",
            gpu_target="gfx1151",
            accel_key="strix-halo",
            accel_env="",
            image_registry="ghcr.io/amdresearch",
            image_tag="v1.0",
            k3s_version="v1.32.3+k3s1",
            helm_version="v3.17.2",
            k9s_version="v0.32.7",
        )

    def test_write_then_from_path_recovers_every_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            original = self._sample()
            original.write(path)
            loaded = BundleManifest.from_path(path)
            self.assertEqual(loaded, original)

    def test_write_emits_4_space_indent(self) -> None:
        """Bash version layout is contractual for human-diff readability."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            self._sample().write(path)
            text = path.read_text(encoding="utf-8")
            # Every continuation line should start with at least 4 spaces of indent
            for line in text.splitlines()[1:-1]:
                if line.strip():
                    self.assertTrue(line.startswith("    "), f"bad indent: {line!r}")

    def test_write_appends_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            self._sample().write(path)
            self.assertTrue(path.read_text(encoding="utf-8").endswith("}\n"))

    def test_from_path_tolerates_missing_optional_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps({"format_version": "1"}), encoding="utf-8")
            m = BundleManifest.from_path(path)
            self.assertEqual(m.format_version, "1")
            self.assertEqual(m.gpu_target, "")
            self.assertEqual(m.image_registry, "")


class DetectOfflineBundleTests(unittest.TestCase):
    def test_returns_none_when_manifest_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(detect_offline_bundle(tmp))

    def test_returns_parsed_manifest_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "manifest.json").write_text(
                json.dumps(
                    {
                        "format_version": "1",
                        "gpu_target": "gfx1151",
                        "image_registry": "ghcr.io/amdresearch",
                        "image_tag": "v1.0",
                    }
                ),
                encoding="utf-8",
            )
            m = detect_offline_bundle(tmp)
            self.assertIsNotNone(m)
            assert m is not None  # narrow for type checkers
            self.assertEqual(m.gpu_target, "gfx1151")
            self.assertEqual(m.image_tag, "v1.0")


if __name__ == "__main__":
    unittest.main()
