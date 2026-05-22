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

# AUP Learning Cloud Code Images

This directory defines the generic browser coding environments for AUP Learning Cloud. They run `code-server` directly as the single-user process behind JupyterHub.

## Image Model

The coding environments are intentionally generic:

- `auplc-code-cpu` inherits from `ghcr.io/amdresearch/auplc-default:latest` for CPU-only development.
- `auplc-code-gpu` inherits from `ghcr.io/amdresearch/auplc-base:latest` for GPU-accelerated development.
- Existing `auplc-default`, `auplc-base`, and `Course-*` images remain notebook/course-focused.
- Course-specific VS Code image families are not part of this workflow.

The Hub resource keys are `code-cpu` and `code-gpu`. They are configured through the same `custom.resources.images`, `custom.resources.requirements`, `custom.resources.metadata`, and `custom.teams.mapping` model as notebook resources in `runtime/values.yaml`.

## Build Commands

From the repository root:

```bash
make -C dockerfiles code-cpu
make -C dockerfiles code-gpu GPU_TARGET=gfx1151
make -C dockerfiles code
```

`code-cpu` builds `ghcr.io/amdresearch/auplc-code-cpu:latest`. `code-gpu` builds `ghcr.io/amdresearch/auplc-code-gpu:latest` and tags the selected GPU target, for example `ghcr.io/amdresearch/auplc-code-gpu:latest-gfx1151`. The aggregate `code` target builds both.

The Dockerfile pins code-server to version `4.96.4` so builds use a known editor runtime instead of silently changing when a new upstream release appears.

## Runtime Behavior

The start script launches:

```bash
code-server --auth none --bind-addr 127.0.0.1:8889 "${AUPLC_CODE_WORKDIR:-/home/jovyan}"
nginx -c /tmp/auplc-code-server-nginx.conf -g 'daemon off;'
```

nginx listens on the public single-user port `8888`, strips the JupyterHub
service prefix such as `/user/<name>/`, and proxies HTTP/WebSocket traffic to
code-server on loopback. The proxy must preserve the full browser `Host` value
with `X-Forwarded-Host` so code-server's WebSocket origin check succeeds behind
JupyterHub and NodePort-style local URLs.

Extensions are installed into `/opt/auplc/code-server/extensions` and code-server
is launched with `--extensions-dir` pointing there. This keeps image-baked
extensions available when Kubernetes mounts a persistent volume over
`/home/jovyan`.

`--auth none` is acceptable only because JupyterHub and the JupyterHub proxy remain the authentication boundary. The user pod's port `8888` must stay private to the Hub/proxy path and must not be exposed directly through an unauthenticated service, ingress, or port-forward shared with untrusted users.

When users provide a Git repository on the spawn form, the existing init-container clone flow is reused. For code resources, the spawner points `AUPLC_CODE_WORKDIR` at the cloned directory so code-server opens the repository workspace.

## Extensions

Default third-party extensions are listed in `extensions.txt`:

```text
ms-python.python
ms-toolsai.jupyter
redhat.vscode-yaml
eamodio.gitlens
ms-python.debugpy
charliermarsh.ruff
```

This baseline keeps Python and Jupyter support for course work, Debugpy for Python debugging, and Ruff for Python linting and formatting. YAML is retained so users can read and edit course, Kubernetes, and other configuration files without adding their own support first. GitLens is retained on purpose so researchers can learn Git history, blame, and commit discipline inside the same workspace they use for code.

Extension versions are not pinned in this iteration. code-server resolves the current compatible extension releases during each image build, while only the code-server package itself is pinned.

Default editor settings are also not baked into the image in this iteration. User workspaces and profiles should keep control over editor preferences.

Local `.vsix` packages from `extensions/` and the AUPLC Back-to-Hub extension package are installed during the image build. Before adding or redistributing additional VS Code, OpenVSX, or Marketplace extensions, verify that each extension's license and marketplace terms permit your intended use.

## Deployment Notes

After pushing or loading the code images, confirm `runtime/values.yaml` or the environment-specific override points `code-cpu` and `code-gpu` at the desired tags. For a Helm-managed deployment, render or upgrade with the same values files used by the target cluster, then restart Hub pods if only Hub code/config needs to reload.
