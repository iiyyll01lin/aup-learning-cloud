# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for the ROCm DaemonSet ``imagePullPolicy`` patch in :mod:`auplc_installer.rocm`.

The offline-reboot ``ImagePullBackOff`` fix moves ``_patch_image_pull_policy``
into the shared (online + offline) code path of both
``deploy_rocm_gpu_device_plugin`` and ``deploy_rocm_gpu_node_labeller``, so the
DaemonSets are always patched to ``imagePullPolicy=IfNotPresent`` after creation
and before the readiness wait.

We exercise the *online* path (``offline_mode=False``, ``bundle_dir=None``) and
stub every subprocess wrapper in the ``auplc_installer.rocm`` namespace (plus
``verify_sha256`` and ``os.remove``) so nothing touches the host or network:

  * ``run_capture`` returns rc=1 so ``_exists_daemonset(...)`` reports the
    DaemonSet as absent and the create path runs.
  * ``run`` captures the ``wget``/``kubectl create``/``kubectl patch`` argv lists.
  * ``run_streaming`` returns 0 so ``_wait_daemonset_ready(...)`` succeeds.
  * ``verify_sha256`` and ``os.remove`` are no-ops.

``deploy_rocm_gpu_device_plugin`` also invokes the labeller deploy, so a single
call covers both DaemonSets.
"""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from auplc_installer import rocm

_PATCH_PATH = "/spec/template/spec/containers/0/imagePullPolicy"


def _completed(returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr="")


def _patch_argv_for(mock_run, daemonset: str) -> list[str]:
    """Return the argv of the ``kubectl patch ds <daemonset>`` call on ``mock_run``."""
    for call in mock_run.call_args_list:
        argv = call.args[0] if call.args else call.kwargs.get("cmd", [])
        if (
            isinstance(argv, list)
            and argv[:3] == ["kubectl", "patch", "ds"]
            and daemonset in argv
        ):
            return argv
    raise AssertionError(
        f"no `kubectl patch ds {daemonset}` call; calls={mock_run.call_args_list}"
    )


class RocmPullPolicyOnlineTests(unittest.TestCase):
    """Online deploy must patch both ROCm DaemonSets to ``IfNotPresent``."""

    @patch("auplc_installer.rocm.os.remove", return_value=None)
    @patch("auplc_installer.rocm.verify_sha256", return_value=None)
    @patch("auplc_installer.rocm.run_streaming", return_value=0)
    @patch("auplc_installer.rocm.run_capture", return_value=_completed(1))
    @patch("auplc_installer.rocm.run", return_value=_completed())
    def test_both_daemonsets_patched_in_online_mode(
        self, mock_run, _mock_capture, _mock_stream, _mock_sha, _mock_remove
    ) -> None:
        rocm.deploy_rocm_gpu_device_plugin(offline_mode=False, bundle_dir=None)

        for daemonset in ("amdgpu-device-plugin-daemonset", "amdgpu-labeller-daemonset"):
            argv = _patch_argv_for(mock_run, daemonset)
            self.assertIn("--type=json", argv)
            patch_body = argv[argv.index("-p") + 1]
            self.assertIn("IfNotPresent", patch_body)
            self.assertIn(_PATCH_PATH, patch_body)

    @patch("auplc_installer.rocm.os.remove", return_value=None)
    @patch("auplc_installer.rocm.verify_sha256", return_value=None)
    @patch("auplc_installer.rocm.run_streaming", return_value=0)
    @patch("auplc_installer.rocm.run_capture", return_value=_completed(1))
    @patch("auplc_installer.rocm.run", return_value=_completed())
    def test_patch_value_is_ifnotpresent_not_always(
        self, mock_run, _mock_capture, _mock_stream, _mock_sha, _mock_remove
    ) -> None:
        rocm.deploy_rocm_gpu_device_plugin(offline_mode=False, bundle_dir=None)

        for daemonset in ("amdgpu-device-plugin-daemonset", "amdgpu-labeller-daemonset"):
            patch_body = _patch_argv_for(mock_run, daemonset)[
                _patch_argv_for(mock_run, daemonset).index("-p") + 1
            ]
            self.assertIn('"value":"IfNotPresent"', patch_body)
            self.assertNotIn("Always", patch_body)


if __name__ == "__main__":
    unittest.main()
