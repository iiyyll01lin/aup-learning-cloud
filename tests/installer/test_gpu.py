# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for :mod:`auplc_installer.gpu` SKU resolution.

Avoids hitting the host (no rocminfo, no ``/sys/class/drm`` reads); instead
exercises the curated/fallback tables and the dataclasses that the rest of
the installer reads from.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from auplc_installer.gpu import (
    _GFX_FALLBACK,
    GPU_CURATED_SKU_KEYS,
    PRODUCT_NAME_TO_SKU,
    GpuConfig,
    SkuEntry,
    _rocminfo_gpu_agent_records,
    append_product,
    detect_and_configure_gpu,
    detect_gpu_gfx_family,
    detect_gpu_product_names,
    is_curated_sku,
    normalise_gpu_type_key,
    normalise_product_name,
    refine_gpu_config_from_node_labels,
    resolve_gpu_config,
    sku_for_detected_product,
    sku_for_product_name,
)
from auplc_installer.util import InstallerError


class NormaliseProductNameTests(unittest.TestCase):
    def test_collapses_internal_whitespace(self) -> None:
        self.assertEqual(normalise_product_name("AMD Radeon  890M Graphics"), "AMD_Radeon_890M_Graphics")

    def test_strips_special_chars_keeping_dot_dash_underscore(self) -> None:
        # Whitespace becomes "_" first, then non-[A-Za-z0-9._-] chars are
        # dropped — so the space between "Foo" and "(Bar)" survives as "_".
        self.assertEqual(normalise_product_name("Foo (Bar)/Baz!"), "Foo_BarBaz")
        self.assertEqual(normalise_product_name("v1.2-rc3"), "v1.2-rc3")

    def test_strips_outer_underscores(self) -> None:
        self.assertEqual(normalise_product_name("  Foo Bar  "), "Foo_Bar")

    def test_empty_input_yields_empty(self) -> None:
        self.assertEqual(normalise_product_name(""), "")
        self.assertEqual(normalise_product_name("   "), "")

    def test_normalises_ryzen_ai_890m_marketing_name(self) -> None:
        self.assertEqual(
            normalise_product_name("AMD Ryzen AI 9 HX 370 w/ Radeon 890M"),
            "AMD_Ryzen_AI_9_HX_370_w_Radeon_890M",
        )


ROCMINFO_WITH_STRIX_CPU_AND_GPU = """
Agent 1
Name:                    AMD Ryzen AI 9 HX 370 w/ Radeon 890M
Marketing Name:          AMD Ryzen AI 9 HX 370 w/ Radeon 890M
Device Type:             CPU
ISA Info:
Agent 2
Name:                    gfx1150
Marketing Name:          AMD Radeon Graphics
Device Type:             GPU
ISA Info:
ISA 1
Name:                    amdgcn-amd-amdhsa--gfx1150
ISA 2
Name:                    amdgcn-amd-amdhsa--gfx11-generic
"""


class RocminfoGpuAgentParserTests(unittest.TestCase):
    def test_records_ignore_cpu_marketing_name_and_keep_gpu_gfx_target(self) -> None:
        self.assertEqual(
            _rocminfo_gpu_agent_records(ROCMINFO_WITH_STRIX_CPU_AND_GPU), [("AMD Radeon Graphics", ["gfx1150"])]
        )

    @patch("auplc_installer.gpu.command_exists", return_value=True)
    @patch("auplc_installer.gpu.run_capture", return_value=SimpleNamespace(stdout=ROCMINFO_WITH_STRIX_CPU_AND_GPU))
    def test_detect_gpu_product_names_reads_gpu_agent_marketing_only(self, *_: object) -> None:
        self.assertEqual(detect_gpu_product_names(), ["AMD_Radeon_Graphics"])

    @patch("auplc_installer.gpu.command_exists", return_value=True)
    @patch("auplc_installer.gpu.run_capture", return_value=SimpleNamespace(stdout=ROCMINFO_WITH_STRIX_CPU_AND_GPU))
    def test_detect_gpu_gfx_family_prefers_gpu_agent_target(self, *_: object) -> None:
        self.assertEqual(detect_gpu_gfx_family(), "gfx1150")


class CuratedSkuLookupTests(unittest.TestCase):
    def test_known_product_name_resolves_to_curated_row(self) -> None:
        row = sku_for_product_name("AMD_Radeon_8060S_Graphics")
        self.assertEqual(row[0], "strix-halo")
        self.assertEqual(row[1], "gfx1151")

    def test_unknown_product_name_synthesises_row(self) -> None:
        row = sku_for_product_name("AMD_Mystery_GPU")
        # Default fallback: gfx120x, no HSA env, quotaRate 4
        self.assertEqual(row[1], "gfx120x")
        self.assertEqual(row[2], "")
        self.assertEqual(row[3], 4)
        # Synthesised key sanitised to a valid kebab-cased token
        self.assertEqual(row[0], "amd-mystery-gpu")
        self.assertEqual(row[4], "AMD Mystery GPU")

    def test_is_curated_sku(self) -> None:
        for key in GPU_CURATED_SKU_KEYS:
            with self.subTest(key=key):
                self.assertTrue(is_curated_sku(key))
        self.assertFalse(is_curated_sku("9600gre"))


class ResolveGpuConfigTests(unittest.TestCase):
    def test_known_short_name(self) -> None:
        accel_key, gpu_target, env, _, _ = resolve_gpu_config("strix-halo")
        self.assertEqual((accel_key, gpu_target, env), ("strix-halo", "gfx1151", ""))

    def test_known_gfx_alias(self) -> None:
        accel_key, gpu_target, _, _, _ = resolve_gpu_config("gfx1151")
        self.assertEqual((accel_key, gpu_target), ("strix-halo", "gfx1151"))

    def test_hyphenated_gfx_alias(self) -> None:
        accel_key, gpu_target, _, _, _ = resolve_gpu_config("gfx-1150")
        self.assertEqual((accel_key, gpu_target), ("strix", "gfx1150"))

    def test_normalise_gpu_type_key(self) -> None:
        self.assertEqual(normalise_gpu_type_key(" GFX-1150 "), "gfx1150")
        self.assertEqual(normalise_gpu_type_key("strix_halo"), "strix-halo")

    def test_unsupported_input_raises(self) -> None:
        with self.assertRaises(InstallerError):
            resolve_gpu_config("totally-not-a-gpu")


class DetectedProductFallbackTests(unittest.TestCase):
    def test_unknown_product_uses_detected_gfx_family_before_generic_fallback(self) -> None:
        row = sku_for_detected_product("AMD_Radeon_Graphics", "gfx1150")
        self.assertEqual(row[0], "strix")
        self.assertEqual(row[1], "gfx1150")

    def test_unknown_product_without_gfx_family_keeps_generic_fallback(self) -> None:
        row = sku_for_detected_product("AMD_Radeon_Graphics")
        self.assertEqual(row[1], "gfx120x")

    @patch("auplc_installer.gpu.detect_gpu_gfx_family", return_value="gfx1150")
    @patch("auplc_installer.gpu.detect_gpu_product_names", return_value=["AMD_Radeon_Graphics"])
    def test_detect_and_configure_uses_gfx_for_generic_single_product_name(self, *_: object) -> None:
        cfg = GpuConfig()
        detect_and_configure_gpu(cfg)
        self.assertEqual(cfg.accel_key, "strix")
        self.assertEqual(cfg.gpu_target, "gfx1150")
        self.assertEqual(cfg.gpu_product_name, "AMD_Radeon_Graphics")

    @patch("auplc_installer.gpu._read_gpu_product_names_from_node_labels", return_value=["AMD_Radeon_Graphics"])
    def test_refinement_preserves_existing_gfx_for_generic_product_name(self, *_: object) -> None:
        cfg = GpuConfig()
        cfg.append(
            SkuEntry(
                accel_key="strix",
                product_name="AMD_Radeon_Graphics",
                gpu_target="gfx1150",
                accel_env="",
                quota_rate=2,
                display_name="",
            )
        )
        refine_gpu_config_from_node_labels(cfg)
        self.assertEqual(cfg.accel_key, "strix")
        self.assertEqual(cfg.gpu_target, "gfx1150")


class FallbackQuotaRateAlignmentTests(unittest.TestCase):
    """Regression guard against the Tier-1 bug we just fixed.

    Same physical GPU should map to the same quotaRate whether the user
    landed on the curated path (PRODUCT_NAME_TO_SKU) or the gfx-family
    fallback (_GFX_FALLBACK).
    """

    PRODUCT_FOR_KEY = {
        "phx": "AMD_Radeon_780M_Graphics",
        "strix": "AMD_Radeon_890M_Graphics",
        "strix-halo": "AMD_Radeon_8060S_Graphics",
        "9070xt": "AMD_Radeon_RX_9070_XT",
        "r9700": "AMD_Radeon_AI_PRO_R9700",
        "9600gre": "AMD_Radeon_RX_9600_GRE",
    }

    def test_fallback_quota_rate_matches_curated(self) -> None:
        for short_key, product_name in self.PRODUCT_FOR_KEY.items():
            with self.subTest(key=short_key):
                fallback_rate = _GFX_FALLBACK[short_key][3]
                curated_rate = PRODUCT_NAME_TO_SKU[product_name][3]
                self.assertEqual(
                    fallback_rate,
                    curated_rate,
                    f"_GFX_FALLBACK[{short_key!r}] quota_rate diverges from PRODUCT_NAME_TO_SKU[{product_name!r}]",
                )


class GpuConfigTests(unittest.TestCase):
    def _entry(self, key: str, target: str = "gfx1151") -> SkuEntry:
        return SkuEntry(
            accel_key=key,
            product_name="",
            gpu_target=target,
            accel_env="",
            quota_rate=4,
            display_name="",
        )

    def test_append_dedups_by_accel_key(self) -> None:
        cfg = GpuConfig()
        cfg.append(self._entry("strix-halo"))
        cfg.append(self._entry("strix-halo"))  # duplicate
        self.assertEqual(len(cfg.skus), 1)

    def test_first_entry_drives_primary_scalars(self) -> None:
        cfg = GpuConfig()
        cfg.append(self._entry("strix-halo", target="gfx1151"))
        cfg.append(self._entry("9070xt", target="gfx1201"))
        self.assertEqual(cfg.accel_key, "strix-halo")
        self.assertEqual(cfg.gpu_target, "gfx1151")

    def test_homogeneous_target_true_for_single_sku(self) -> None:
        cfg = GpuConfig()
        cfg.append(self._entry("strix-halo"))
        self.assertTrue(cfg.homogeneous_target)

    def test_homogeneous_target_false_for_mixed_gfx(self) -> None:
        cfg = GpuConfig()
        cfg.append(self._entry("strix-halo", target="gfx1151"))
        cfg.append(self._entry("9070xt", target="gfx1201"))
        self.assertFalse(cfg.homogeneous_target)

    def test_append_product_uses_curated_table_when_known(self) -> None:
        cfg = GpuConfig()
        append_product(cfg, "AMD_Radeon_8060S_Graphics")
        self.assertEqual(cfg.accel_key, "strix-halo")
        self.assertEqual(cfg.gpu_target, "gfx1151")
        self.assertEqual(cfg.skus[0].product_name, "AMD_Radeon_8060S_Graphics")

    def test_append_product_synthesises_row_when_unknown(self) -> None:
        cfg = GpuConfig()
        append_product(cfg, "AMD_Some_Future_GPU")
        self.assertEqual(cfg.accel_key, "amd-some-future-gpu")
        self.assertEqual(cfg.gpu_target, "gfx120x")

    def test_append_product_ignores_empty_string(self) -> None:
        cfg = GpuConfig()
        append_product(cfg, "")
        self.assertEqual(cfg.skus, [])


if __name__ == "__main__":
    unittest.main()
