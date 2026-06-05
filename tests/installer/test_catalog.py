# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for :mod:`auplc_installer.catalog`.

Covers the user-facing CLI selection grammar (``--courses=…`` /
``AUPLC_COURSES``) and the helper methods on :class:`CourseSelection` that
the rest of the installer relies on for image filtering and team-mapping
overrides.
"""

from __future__ import annotations

import unittest

from auplc_installer.catalog import (
    COURSE_KEYS_ALL,
    COURSE_PRESET_ALL,
    COURSE_PRESET_BASIC,
    NONE_SENTINEL,
    CourseSelection,
    parse_selection_spec,
)
from auplc_installer.util import InstallerError


class ParseSelectionSpecTests(unittest.TestCase):
    def test_empty_string_is_default(self) -> None:
        self.assertTrue(parse_selection_spec("").is_default())

    def test_all_keyword_picks_every_course(self) -> None:
        sel = parse_selection_spec("all")
        self.assertEqual(sel.picks, list(COURSE_PRESET_ALL))
        self.assertFalse(sel.is_default())  # explicit selection, not the default sentinel

    def test_basic_keyword_picks_cpu_gpu_and_code_server(self) -> None:
        self.assertEqual(parse_selection_spec("basic").picks, list(COURSE_PRESET_BASIC))

    def test_none_keyword_uses_sentinel(self) -> None:
        sel = parse_selection_spec("none")
        self.assertTrue(sel.is_none())
        self.assertEqual(sel.picks, [NONE_SENTINEL])

    def test_keyword_is_case_insensitive(self) -> None:
        for spec in ("ALL", "All", "Basic", "NONE"):
            with self.subTest(spec=spec):
                # Should not raise
                parse_selection_spec(spec)

    def test_explicit_keys_round_trip(self) -> None:
        sel = parse_selection_spec("cpu,gpu,Course-CV")
        self.assertEqual(sel.picks, ["cpu", "gpu", "Course-CV"])

    def test_tolerates_whitespace_and_blank_entries(self) -> None:
        sel = parse_selection_spec("  cpu , ,Course-CV ")
        self.assertEqual(sel.picks, ["cpu", "Course-CV"])

    def test_unknown_key_raises(self) -> None:
        with self.assertRaises(InstallerError):
            parse_selection_spec("not-a-real-course")

    def test_unknown_key_message_lists_valid_keys(self) -> None:
        try:
            parse_selection_spec("nope")
        except InstallerError as exc:
            msg = str(exc)
            self.assertIn("nope", msg)
            for key in COURSE_KEYS_ALL:
                self.assertIn(key, msg)
        else:
            self.fail("expected InstallerError")


class CourseSelectionTests(unittest.TestCase):
    def test_default_returns_all_keys(self) -> None:
        sel = CourseSelection.default()
        self.assertEqual(sel.effective_keys(), list(COURSE_KEYS_ALL))
        self.assertTrue(sel.is_selected("cpu"))
        self.assertTrue(sel.is_selected("Course-LLM"))

    def test_none_selects_no_keys(self) -> None:
        sel = CourseSelection(picks=[NONE_SENTINEL])
        self.assertEqual(sel.effective_keys(), [])
        self.assertFalse(sel.is_selected("cpu"))

    def test_explicit_picks_preserves_order(self) -> None:
        sel = CourseSelection(picks=["Course-LLM", "cpu"])
        self.assertEqual(sel.effective_keys(), ["Course-LLM", "cpu"])

    def test_gpu_image_basenames_only_returns_gpu_required(self) -> None:
        sel = CourseSelection(picks=["cpu", "gpu", "code-gpu", "Course-CV"])
        # cpu/code-cpu are plain-tagged; gpu/code-gpu/Course-CV are GPU-tagged
        self.assertEqual(
            sel.gpu_image_basenames(),
            ["auplc-base", "auplc-code-gpu", "auplc-cv"],
        )
        self.assertEqual(sel.plain_image_basenames(), ["auplc-default"])

    def test_make_targets_includes_every_selected_course(self) -> None:
        sel = CourseSelection(picks=["cpu", "code-cpu", "Course-DL"])
        self.assertEqual(sel.make_targets(), ["base-cpu", "code-cpu", "dl"])

    def test_description_default(self) -> None:
        self.assertEqual(CourseSelection.default().description(), "all (default)")

    def test_description_none(self) -> None:
        self.assertEqual(CourseSelection(picks=[NONE_SENTINEL]).description(), "none")

    def test_description_custom(self) -> None:
        sel = CourseSelection(picks=["cpu", "Course-CV"])
        self.assertEqual(sel.description(), "cpu, Course-CV")


if __name__ == "__main__":
    unittest.main()
