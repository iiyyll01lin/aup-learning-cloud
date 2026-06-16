# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for the systemd units emitted by :mod:`auplc_installer.k3s`.

The "auto-start after reboot" fix lives entirely in the *text* of two
systemd files that ``k3s.py`` writes by piping into ``tee`` (via
``run_pipe_text_to``):

  * ``dummy-interface.service`` — must rebuild dummy0 + its node IP on
    every boot, idempotently (``ip addr replace``), ordered after
    ``network-pre.target`` (NOT ``network-online.target``, which never
    completes on an offline boot), loading the ``dummy`` module first.
  * ``k3s.service.d/10-auplc-autostart.conf`` — always written (both
    runtimes). It neutralizes the upstream ``network-online`` wait by
    resetting ``Wants=``/``After=`` with empty assignments, then re-adds
    only the ordering we need: after ``dummy-interface.service`` for
    containerd, and after ``docker.service dummy-interface.service`` for
    ``--docker``.

These are pure string contracts, so we stub the subprocess wrappers in
the ``auplc_installer.k3s`` namespace (the same "patch where it's looked
up" approach the CLI tests use) and assert on the captured ``input_text``
without touching the real system.
"""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from auplc_installer import k3s


def _completed(returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr="")


def _tee_payload(mock_pipe, target: str) -> str:
    """Return the ``input_text`` of the ``tee <target>`` call on ``mock_pipe``."""
    for call in mock_pipe.call_args_list:
        cmd = call.args[0] if call.args else call.kwargs.get("cmd", [])
        if target in cmd:
            return call.kwargs["input_text"]
    raise AssertionError(f"no tee call targeting {target!r}; calls={mock_pipe.call_args_list}")


class SetupDummyInterfaceUnitTests(unittest.TestCase):
    _UNIT = "/etc/systemd/system/dummy-interface.service"

    # ``run_capture`` returns rc=0 so ``_dummy_interface_exists()`` reports
    # the interface as present and we skip the real ``ip`` bring-up path;
    # ``run``/``run_pipe_text_to`` are stubbed so nothing touches the host.
    @patch("auplc_installer.k3s.run_capture", return_value=_completed(0))
    @patch("auplc_installer.k3s.run", return_value=_completed())
    @patch("auplc_installer.k3s.run_pipe_text_to", return_value=0)
    def test_orders_after_network_pre_not_online(self, mock_pipe, _mock_run, _mock_capture) -> None:
        k3s.setup_dummy_interface()
        payload = _tee_payload(mock_pipe, self._UNIT)
        self.assertNotIn("network-online.target", payload)
        self.assertIn("After=network-pre.target", payload)

    @patch("auplc_installer.k3s.run_capture", return_value=_completed(0))
    @patch("auplc_installer.k3s.run", return_value=_completed())
    @patch("auplc_installer.k3s.run_pipe_text_to", return_value=0)
    def test_modprobes_dummy_before_start(self, mock_pipe, _mock_run, _mock_capture) -> None:
        k3s.setup_dummy_interface()
        self.assertIn("ExecStartPre=-/sbin/modprobe dummy", _tee_payload(mock_pipe, self._UNIT))

    @patch("auplc_installer.k3s.run_capture", return_value=_completed(0))
    @patch("auplc_installer.k3s.run", return_value=_completed())
    @patch("auplc_installer.k3s.run_pipe_text_to", return_value=0)
    def test_uses_idempotent_ip_replace(self, mock_pipe, _mock_run, _mock_capture) -> None:
        k3s.setup_dummy_interface()
        self.assertIn(
            "ip addr replace 10.255.255.1/32 dev dummy0",
            _tee_payload(mock_pipe, self._UNIT),
        )


class InstallK3sDropinsUnitTests(unittest.TestCase):
    _DROPIN = "/etc/systemd/system/k3s.service.d/10-auplc-autostart.conf"

    @patch("auplc_installer.k3s.run", return_value=_completed())
    @patch("auplc_installer.k3s.run_pipe_text_to", return_value=0)
    def test_docker_dropin_orders_k3s_after_docker_and_dummy(self, mock_pipe, _mock_run) -> None:
        k3s._install_k3s_dropins(use_docker=True)
        payload = _tee_payload(mock_pipe, self._DROPIN)
        self.assertIn("After=docker.service dummy-interface.service", payload)
        # network-online wait neutralized via an empty Wants= reset line.
        self.assertIn("Wants=\n", payload)
        self.assertNotIn("network-online.target", payload)

    @patch("auplc_installer.k3s.run", return_value=_completed())
    @patch("auplc_installer.k3s.run_pipe_text_to", return_value=0)
    def test_containerd_dropin_orders_k3s_after_dummy(self, mock_pipe, _mock_run) -> None:
        k3s._install_k3s_dropins(use_docker=False)
        payload = _tee_payload(mock_pipe, self._DROPIN)
        self.assertIn("After=dummy-interface.service", payload)
        # network-online wait neutralized via an empty Wants= reset line.
        self.assertIn("Wants=\n", payload)
        self.assertNotIn("network-online.target", payload)


if __name__ == "__main__":
    unittest.main()
