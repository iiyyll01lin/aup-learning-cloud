# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

ARG BASE_IMAGE=ghcr.io/amdresearch/auplc-default:latest
ARG IMAGE_FLAVOR=cpu
FROM ${BASE_IMAGE}

ARG IMAGE_FLAVOR
USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl nginx-light && \
    curl -fsSL https://code-server.dev/install.sh | sh && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY extensions.txt /opt/auplc/extensions/extensions.txt
COPY extensions/ /opt/auplc/extensions/local/
COPY auplc-hub-link/auplc-hub-link-0.0.0.vsix /opt/auplc/extensions/local/auplc-hub-link-0.0.0.vsix
COPY start-code-server.sh /usr/local/bin/start-code-server.sh

RUN chmod +x /usr/local/bin/start-code-server.sh && \
    mkdir -p \
        /opt/auplc/extensions/local \
        /home/jovyan/.cache \
        /home/jovyan/.config \
        /home/jovyan/.local/share/code-server && \
    chown -R jovyan:100 /opt/auplc /home/jovyan/.cache /home/jovyan/.config /home/jovyan/.local

USER jovyan

RUN set -eu; \
    while IFS= read -r extension_id || [ -n "${extension_id}" ]; do \
        case "${extension_id}" in ''|'#'*) continue ;; esac; \
        code-server --install-extension "${extension_id}"; \
    done < /opt/auplc/extensions/extensions.txt; \
    find /opt/auplc/extensions/local -type f -name '*.vsix' -print0 | \
        xargs -0 -r -n 1 code-server --install-extension

EXPOSE 8888
WORKDIR /home/jovyan
CMD ["/usr/local/bin/start-code-server.sh"]
