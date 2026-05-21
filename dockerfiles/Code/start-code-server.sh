#!/usr/bin/env bash
set -euo pipefail

export USER="${USER:-jovyan}"
export SHELL="${SHELL:-/bin/bash}"

public_port="${PORT:-8888}"
code_server_port="${AUPLC_CODE_SERVER_PORT:-8889}"
service_prefix="${JUPYTERHUB_SERVICE_PREFIX:-/}"
workdir="${AUPLC_CODE_WORKDIR:-/home/jovyan}"
extensions_dir="${AUPLC_CODE_EXTENSIONS_DIR:-/opt/auplc/code-server/extensions}"

case "${service_prefix}" in
  /*) ;;
  *) service_prefix="/${service_prefix}" ;;
esac

case "${service_prefix}" in
  */) ;;
  *) service_prefix="${service_prefix}/" ;;
esac

regex_prefix="$(printf '%s' "${service_prefix}" | sed 's/[.[\*^$()+?{}|]/\\&/g')"
nginx_conf="/tmp/auplc-code-server-nginx.conf"
redirect_block=""

if [ "${service_prefix}" != "/" ]; then
  redirect_block="
    location = ${service_prefix%/} {
      return 302 ${service_prefix};
    }
"
fi

cat >"${nginx_conf}" <<EOF
pid /tmp/auplc-code-server-nginx.pid;
error_log /dev/stderr info;
events {}
http {
  access_log /dev/stdout;

  client_body_temp_path /tmp/client_body;
  proxy_temp_path /tmp/proxy;
  fastcgi_temp_path /tmp/fastcgi;
  uwsgi_temp_path /tmp/uwsgi;
  scgi_temp_path /tmp/scgi;

  map \$http_upgrade \$connection_upgrade {
    default upgrade;
    '' close;
  }

  server {
    listen 0.0.0.0:${public_port};
    client_max_body_size 0;
${redirect_block}

    location ${service_prefix} {
      rewrite ^${regex_prefix}(.*)\$ /\$1 break;
      proxy_pass http://127.0.0.1:${code_server_port};
      proxy_http_version 1.1;
      proxy_set_header Host \$http_host;
      proxy_set_header X-Forwarded-Host \$http_host;
      proxy_set_header Upgrade \$http_upgrade;
      proxy_set_header Connection \$connection_upgrade;
      proxy_set_header X-Real-IP \$remote_addr;
      proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto \$scheme;
      proxy_read_timeout 86400;
      proxy_redirect off;
    }
  }
}
EOF

code-server \
  --auth none \
  --bind-addr "127.0.0.1:${code_server_port}" \
  --extensions-dir "${extensions_dir}" \
  "${workdir}" &
code_server_pid="$!"

nginx -c "${nginx_conf}" -g 'daemon off;' &
nginx_pid="$!"

cleanup() {
  kill "${nginx_pid}" "${code_server_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait -n "${nginx_pid}" "${code_server_pid}"
