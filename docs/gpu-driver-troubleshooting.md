<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved. -->
<!--
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
-->

# GPU Page Fault Incident & amdgpu Driver Runbook · GPU Page Fault 事件與 amdgpu 驅動排查手冊

A field report and runbook for the "every GPU op page-faults" failure seen on
Strix Halo (gfx1151 / Radeon 8060S) AUP Learning Cloud nodes, plus the tools that
diagnose, fix, and prevent it.

針對 Strix Halo（gfx1151 / Radeon 8060S）節點上「任何 GPU 運算都 page fault」故障的
事件報告與排查手冊，以及用來診斷、修復、預防的工具。

---

## 1. Summary · 摘要

**EN —** On a gfx1151 node, every GPU operation (even a 32-byte `torch.ones(8)`)
crashed with an `amdgpu [gfxhub] page fault`. Root cause: the **host `amdgpu`
kernel driver was too old (release 30.30 / module 6.16.13)** for the ROCm 7.13
userspace shipped inside the course containers and for the brand-new gfx1151
chip. Upgrading the host driver to the platform baseline **31.30 (module 6.19.4)**
and rebooting fixed it. It was **not** a notebook, VRAM, XNACK, or kernel
point-release problem, and **not** caused by `demo-setup.sh`.

**中文 —** 在 gfx1151 節點上，任何 GPU 運算（連 32 bytes 的 `torch.ones(8)`）都會
觸發 `amdgpu [gfxhub] page fault`。根因：**主機的 `amdgpu` 核心驅動太舊（release
30.30 / 模組 6.16.13）**，與課程容器內的 ROCm 7.13 userspace 及全新的 gfx1151 晶片
不匹配。將主機驅動升級到平台基線 **31.30（模組 6.19.4）** 並重開機即解決。**不是**
notebook、VRAM、XNACK 或核心小版本問題，也**不是** `demo-setup.sh` 造成的。

---

## 2. Symptoms · 症狀

**EN —** In `dmesg` (and `journalctl -k`):

**中文 —** 在 `dmesg`（或 `journalctl -k`）中：

```
amdgpu 0000:c5:00.0: amdgpu: [gfxhub] page fault (src_id:0 ring:153 vmid:8 ...)
  Process python3 ...
  Faulty UTCL2 client ID: CPF (0x4)
  WALKER_ERROR: 0x1
  PERMISSION_FAULTS: 0x3
  MAPPING_ERROR: 0x1
```

Inside the pod / container: `Memory access fault by GPU node-1 ... Reason: Page
not present or supervisor privilege.` and the process exits with code 134.

容器/pod 內：`Memory access fault by GPU node-1 ... Reason: Page not present` 並以
exit code 134 結束。

**Key tell · 關鍵判讀:** it faults even on a trivial op (`torch.ones(8)`) and on a
plain host→device copy — so it is **not** about memory size. The Command
Processor Fetcher (CPF) cannot translate the first command buffer = a
driver/firmware-level inability to run any GPU kernel.

連最小運算（`torch.ones(8)`）與純記憶體拷貝都炸 → **與記憶體大小無關**。命令處理器
擷取單元（CPF）連第一個命令緩衝區都翻譯不了 = 驅動/韌體層級「跑不動任何 GPU kernel」。

---

## 3. Root Cause · 根本原因

**EN —** The host shipped **amdgpu 30.30** (apt repo `repo.radeon.com/amdgpu/30.30`,
DKMS module `6.16.13`), but the platform baseline (ROCm 7.13 containers) requires
**amdgpu 31.30**, installed by `deploy/ansible/roles/rocm/tasks/main.yml`. On
gfx1151 the older driver cannot initialise the command processor, so the GPU VM
page-faults on the first submission. Evidence the node had drifted: the apt
source list still contained a commented-out `# deb .../amdgpu/7.2/...` line —
the box had been moved 7.2 → 30.30 but never reached 31.30.

**中文 —** 主機裝的是 **amdgpu 30.30**（apt repo `repo.radeon.com/amdgpu/30.30`，
DKMS 模組 `6.16.13`），但平台基線（ROCm 7.13 容器）要求 **amdgpu 31.30**，由
`deploy/ansible/roles/rocm/tasks/main.yml` 安裝。對 gfx1151 來說舊驅動無法初始化
命令處理器，因此第一次 GPU 送命令就 page fault。漂移證據：apt 來源清單裡仍留著被
註解掉的 `# deb .../amdgpu/7.2/...` —— 這台從 7.2 升到 30.30，卻沒升到 31.30。

### Ruled out · 已排除

- VRAM size / 512MB carve-out — a 32-byte op faults. · 32 bytes 就炸，與 VRAM 無關。
- XNACK — `HSA_XNACK=0` and `=1` both fault. · 兩種都炸。
- Notebook code · notebook 程式 — trivial op faults. · 最小運算就炸。
- Kernel point release (1020 vs documented 1018) — benign; DKMS rebuilds for the
  running kernel; 1018 was removed from apt. · 無害；DKMS 會對當前核心重建；1018 已下架。

---

## 4. Diagnose · 診斷

**Fastest (with the tool) · 最快（用工具）:**

```bash
sudo ./auplc-gpu-doctor.sh           # check installed amdgpu release vs 31.30 + dmesg faults
sudo ./auplc-gpu-doctor.sh --smoke   # also run a real GPU compute kernel in a cached image
```

**Manual · 手動:**

```bash
# installed amdgpu release (expect 31.30; 30.30 = the bug)
dpkg -l | grep -E 'amdgpu-install|amdgpu-dkms' | awk '{print $2,$3}'
grep -rhoE 'amdgpu(-install)?/[0-9]+\.[0-9]+' /etc/apt/sources.list.d/ | sort -u
cat /sys/module/amdgpu/version

# reproduce inside the running GPU notebook pod
kubectl -n jupyterhub exec jupyter-student -- python3 -c "import torch; print(torch.ones(8, device='cuda').sum())"
sudo dmesg -T | grep -Ei 'amdgpu|page fault'
```

---

## 5. Fix / Rescue · 修復／搶救

**One command · 一鍵:**

```bash
sudo ./auplc-gpu-doctor.sh --fix     # switch amdgpu repo to 31.30, upgrade DKMS + firmware
sudo reboot
sudo ./auplc-gpu-doctor.sh --check   # expect: amdgpu release 31.30 ... [OK]
```

**Manual equivalent · 手動等效步驟:**

```bash
sudo apt-get install -y "linux-headers-$(uname -r)"   # DKMS build headers
wget https://repo.radeon.com/amdgpu-install/31.30/ubuntu/noble/amdgpu-install_31.30.313000-1_all.deb -O /tmp/a.deb
sudo apt-get install -y -o Dpkg::Options::=--force-confold /tmp/a.deb   # keeps your rocm.list
sudo apt-get update
sudo apt-get install -y -o Dpkg::Options::=--force-confold amdgpu-dkms amdgpu-dkms-firmware
sudo reboot
```

> `--force-confold` keeps existing apt source files (answer "keep current" to the
> `rocm.list` prompt). · `--force-confold` 會保留現有 apt 來源檔（等同對 `rocm.list`
> 選「保留現用」）。

**After reboot, verify end-to-end · 重開後做端到端驗證:**

```bash
cat /sys/module/amdgpu/version                         # 6.19.4 (31.30)
# spawn a GPU notebook via the WEB FORM (see §8) then:
kubectl -n jupyterhub exec jupyter-student -- python3 -c "import torch; print(torch.ones(8, device='cuda').sum())"
```

---

## 6. Prevention · 預防

`demo-setup.sh` now gates on the driver baseline during install (`gpu_driver_gate`,
runs after preflight, only when an AMD GPU is present):

`demo-setup.sh` 現在會在安裝時驗驅動基線（`gpu_driver_gate`，在 preflight 之後執行，
僅在偵測到 AMD GPU 時）：

| Driver state · 驅動狀態 | Default · 預設 | `FIX_GPU=1` |
|---|---|---|
| `>= 31.30` | OK, continue · 通過繼續 | same · 同左 |
| too old / missing · 太舊或沒裝 | **STOP** with instructions · **停止**並給指令 | **auto `--fix`** + shared reboot · **自動修復**並共用一次重開 |
| no AMD GPU · 無 AMD GPU | skip · 略過 | skip · 略過 |
| `SKIP_CHECKS=1` | skip · 略過 | skip · 略過 |

```bash
sudo ./demo-setup.sh             # stops early if the driver is too old
sudo FIX_GPU=1 ./demo-setup.sh   # auto-upgrade the driver, reboot, and continue
```

**After a successful install, lock the working stack in place** (opt-in — the
kernel/driver holds block updates until `--unpin`) · **裝好後把可用的組合鎖住**
（選用；kernel/驅動 hold 會擋更新，直到 `--unpin`）:

```bash
sudo ./auplc-gpu-doctor.sh --pin     # hold driver at baseline + pin the boot kernel
sudo ./auplc-gpu-doctor.sh --unpin   # revert anytime · 隨時可解
```

---

## 7. Tool reference · 工具參考: `auplc-gpu-doctor.sh`

| Mode · 模式 | What it does · 用途 |
|---|---|
| `--check` (default) | Print GPU + amdgpu release vs 31.30 + DKMS + dmesg fault scan; exit 1 if below baseline. · 印出 GPU、amdgpu 版本、DKMS、dmesg page fault；低於基線回傳 1。 |
| `--smoke` | Also run `torch.ones(8)` on the GPU inside a cached `auplc-*gfx*` image. · 另在 cached GPU image 內實際跑一次 GPU 運算。 |
| `--fix` | Upgrade amdgpu to 31.30 + rebuild DKMS (reboot afterwards). · 升級到 31.30 並重建 DKMS（之後需重開）。 |
| `--pin` / `--pin-kernel` | Hold the driver at baseline + pin the boot kernel (opt-in; blocks kernel/driver updates until `--unpin`). · 鎖驅動於基線 + 釘開機 kernel（選用；會擋更新直到 `--unpin`）。 |
| `--unpin` | Remove those holds (allow updates again). · 解除鎖定（恢復更新）。 |

The required release is defined once at the top of the script
(`REQUIRED_RELEASE="31.30"`); keep it in sync with the ansible rocm role.

所需版本只定義在腳本開頭（`REQUIRED_RELEASE="31.30"`），請與 ansible rocm role 同步。

---

## 8. Notes / FAQ · 補充說明

**Does Ubuntu bundle this amdgpu driver? · Ubuntu 會內建這個 amdgpu 驅動嗎?**
Ubuntu ships the **in-tree** `amdgpu` kernel module (enough for display), but the
**ROCm `amdgpu-dkms`** (30.30 / 31.30 from `repo.radeon.com`) is installed
separately and is what gfx1151 + ROCm compute needs. The reported `6.16.13 /
6.19.4` versions are DKMS (out-of-tree).
Ubuntu 內建的是**內核內建版** `amdgpu`（夠亮畫面），但 **ROCm 的 `amdgpu-dkms`**
（來自 `repo.radeon.com` 的 30.30 / 31.30）要另外裝，才是 gfx1151 + ROCm 計算所需。
看到的 `6.16.13 / 6.19.4` 都是 DKMS（out-of-tree）版本。

**Is `demo-setup.sh` the cause? · 是 `demo-setup.sh` 造成的嗎?**
No. `demo-setup.sh` and `auplc_installer/` install the OEM kernel + k3s/helm +
GPU device-plugin, but **never the amdgpu driver** (only `deploy/ansible/roles/
rocm` does, at 31.30). The old 30.30 came from a separate/manual install.
不是。`demo-setup.sh` 與 `auplc_installer/` 只裝 OEM kernel + k3s/helm + GPU
device-plugin，**完全不碰 amdgpu 驅動**（只有 `deploy/ansible/roles/rocm` 會裝，且是
31.30）。舊的 30.30 是另外手動裝上去的。

**JupyterHub image gotcha · JupyterHub image 陷阱.**
The course/GPU image is selected **only via the web spawn form**
(`RemoteLabKubeSpawner.options_from_form`). A bare REST API
`POST /hub/api/users/<u>/server` skips it and falls back to
`quay.io/jupyterhub/singleuser:latest` (no torch). Headless: POST the form to
`/hub/spawn/<u>` with `resource_type=gpu` (or `Course-CV/DL/LLM/PhySim`).
課程/GPU image **只有透過網頁 spawn 表單**才會被選定。裸 REST API 的
`POST /hub/api/users/<u>/server` 會略過它，fallback 到沒 torch 的上游 image。
Headless 要用表單：`POST /hub/spawn/<u>` 帶 `resource_type=gpu`。

---

## 9. Version baseline · 版本基線

| Component · 元件 | Baseline · 基線 | Source · 來源 |
|---|---|---|
| amdgpu driver | **31.30** (module 6.19.x) | `deploy/ansible/roles/rocm/tasks/main.yml` |
| Container ROCm / torch | `2.9.1+rocm7.13.0` | `dockerfiles/Base/Dockerfile.rocm` |
| GPU | gfx1151 / GC_11_5_0 / Radeon 8060S | — |
| OEM kernel (APU) | `6.14.0-1018-oem`* | `demo-setup.sh` |
| OS | Ubuntu 24.04 | — |

\* The point release rolls forward (e.g. 1020); DKMS rebuilds for whatever kernel
is running, so a newer 6.14.0-*-oem is fine. · 小版本會往前滾（如 1020）；DKMS 會對
當前核心重建，較新的 6.14.0-*-oem 沒問題。
