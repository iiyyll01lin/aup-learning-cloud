# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for CLI/TUI parity helpers (summary + install image-source resolution)."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from auplc_installer.catalog import COURSE_PRESET_ALL, CourseSelection
from auplc_installer.cli import _apply_global_flags, _build_parser, cmd_install_plan, main
from auplc_installer.state import InstallerState
from auplc_installer.summary import (
    IMAGE_SOURCE_BUILD,
    IMAGE_SOURCE_PULL,
    format_configuration_summary,
    normalize_image_source,
    resolve_install_image_source,
)
from auplc_installer.util import InstallerError


class NormalizeImageSourceTests(unittest.TestCase):
    def test_pull_and_ghcr_alias(self) -> None:
        self.assertEqual(normalize_image_source("pull"), IMAGE_SOURCE_PULL)
        self.assertEqual(normalize_image_source("ghcr"), IMAGE_SOURCE_PULL)

    def test_build(self) -> None:
        self.assertEqual(normalize_image_source("build"), IMAGE_SOURCE_BUILD)

    def test_unknown_raises(self) -> None:
        with self.assertRaises(InstallerError):
            normalize_image_source("nope")


class ResolveInstallImageSourceTests(unittest.TestCase):
    def test_default_is_pull(self) -> None:
        pull, label = resolve_install_image_source(image_source=None, legacy_pull=False)
        self.assertTrue(pull)
        self.assertEqual(label, IMAGE_SOURCE_PULL)

    def test_legacy_pull_flag(self) -> None:
        pull, label = resolve_install_image_source(image_source=None, legacy_pull=True)
        self.assertTrue(pull)
        self.assertEqual(label, IMAGE_SOURCE_PULL)

    def test_explicit_pull(self) -> None:
        pull, label = resolve_install_image_source(image_source="pull", legacy_pull=False)
        self.assertTrue(pull)
        self.assertEqual(label, IMAGE_SOURCE_PULL)

    def test_explicit_ghcr_alias(self) -> None:
        pull, label = resolve_install_image_source(image_source="ghcr", legacy_pull=False)
        self.assertTrue(pull)
        self.assertEqual(label, IMAGE_SOURCE_PULL)

    def test_explicit_build(self) -> None:
        pull, label = resolve_install_image_source(image_source="build", legacy_pull=True)
        self.assertFalse(pull)
        self.assertEqual(label, IMAGE_SOURCE_BUILD)

    def test_explicit_build_overrides_legacy_pull(self) -> None:
        pull, label = resolve_install_image_source(image_source="build", legacy_pull=True)
        self.assertFalse(pull)
        self.assertEqual(label, IMAGE_SOURCE_BUILD)

    def test_offline_bundle(self) -> None:
        pull, label = resolve_install_image_source(
            image_source="pull",
            legacy_pull=False,
            offline_mode=True,
            bundle_dir=Path("/tmp/bundle"),
        )
        self.assertFalse(pull)
        self.assertIn("Offline bundle", label)

    def test_unknown_source_raises(self) -> None:
        with self.assertRaises(InstallerError):
            resolve_install_image_source(image_source="nope", legacy_pull=False)


class FormatConfigurationSummaryTests(unittest.TestCase):
    def test_includes_core_fields(self) -> None:
        state = InstallerState(
            gpu_type="strix-halo",
            use_docker=True,
            image_registry="ghcr.io/example",
            image_tag="develop",
            courses=CourseSelection(picks=list(COURSE_PRESET_ALL)),
        )
        text = format_configuration_summary(state, image_source_label=IMAGE_SOURCE_PULL)
        self.assertIn("Configuration summary", text)
        self.assertIn("strix-halo", text)
        self.assertIn("Docker", text)
        self.assertIn("  Image source     : pull", text)
        self.assertIn("ghcr.io/example", text)
        self.assertIn("develop", text)
        self.assertIn("Course-CV", text)


class ApplyGlobalFlagsTests(unittest.TestCase):
    def test_gpu_auto_clears_override(self) -> None:
        state = InstallerState(gpu_type="strix")
        parser = _build_parser()
        args = parser.parse_args(["--gpu=auto"])
        _apply_global_flags(state, args)
        self.assertEqual(state.gpu_type, "")

    def test_runtime_containerd(self) -> None:
        state = InstallerState(use_docker=True)
        parser = _build_parser()
        args = parser.parse_args(["--runtime=containerd"])
        _apply_global_flags(state, args)
        self.assertFalse(state.use_docker)

    def test_runtime_wins_over_docker_flag(self) -> None:
        state = InstallerState(use_docker=True)
        parser = _build_parser()
        args = parser.parse_args(["--runtime=containerd", "--docker=1"])
        _apply_global_flags(state, args)
        self.assertFalse(state.use_docker)

    def test_image_flags(self) -> None:
        state = InstallerState()
        parser = _build_parser()
        args = parser.parse_args(
            [
                "--image-source=pull",
                "--image-registry=registry.example.com/org",
                "--image-tag=develop",
            ]
        )
        _apply_global_flags(state, args)
        self.assertEqual(state.image_source, "pull")
        self.assertEqual(state.image_registry, "registry.example.com/org")
        self.assertEqual(state.image_tag, "develop")


class InstallDryRunTests(unittest.TestCase):
    def test_install_dry_run_prints_summary(self) -> None:
        state = InstallerState(
            image_source="pull",
            image_tag="develop",
            courses=CourseSelection(picks=list(COURSE_PRESET_ALL)),
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_install_plan(state, legacy_pull=False)
        out = buf.getvalue()
        self.assertIn("Configuration summary", out)
        self.assertIn("develop", out)
        self.assertIn("  Image source     : pull", out)

    def test_install_dry_run_defaults_to_pull(self) -> None:
        state = InstallerState()
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_install_plan(state, legacy_pull=False)
        out = buf.getvalue()
        self.assertIn("  Image source     : pull", out)

    def test_help_flag_prints_usage(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["--help"])
        out = buf.getvalue()
        self.assertIn("Usage: ./auplc-installer", out)
        self.assertIn("install --dry-run", out)

    @patch("auplc_installer.cli._resolve_source_root")
    @patch("auplc_installer.cli.InstallerState.from_environment")
    def test_main_install_dry_run(self, mock_from_env, mock_root) -> None:
        mock_root.return_value = Path("/repo")
        mock_from_env.return_value = InstallerState(image_tag="develop")
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["install", "--dry-run", "--image-tag=develop"])
        out = buf.getvalue()
        self.assertIn("Configuration summary", out)
        self.assertIn("develop", out)
        self.assertIn("  Image source     : pull", out)

    @patch("auplc_installer.cli._resolve_source_root")
    @patch("auplc_installer.cli.InstallerState.from_environment")
    def test_dry_run_without_install_errors(self, mock_from_env, mock_root) -> None:
        mock_root.return_value = Path("/repo")
        mock_from_env.return_value = InstallerState()
        with self.assertRaises(SystemExit) as ctx:
            main(["detect-gpu", "--dry-run"])
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
