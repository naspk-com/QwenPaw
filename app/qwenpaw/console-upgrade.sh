#!/bin/bash

source "${TRIM_APPDEST}/qwenpaw/runtime.sh" || exit 1
qwenpaw_setup || exit 1
pid_file="${TRIM_PKGVAR}/qwenpaw.pid"
upgrade_pid_file="${TRIM_PKGVAR}/qwenpaw-upgrade.pid"
lock_dir="${TRIM_PKGVAR}/qwenpaw-upgrade.lock"
log_file="${TRIM_PKGVAR}/qwenpaw.log"
trap 'rm -f "${upgrade_pid_file}"; rmdir "${lock_dir}" 2>/dev/null || true' EXIT

echo "=== QwenPaw 升级开始 ==="
if ! qwenpaw_prepare_runtime pypi "${1:-}"; then
    echo "=== 升级失败：原运行环境未删除 ==="
    exit 1
fi

if [ -x "${VENV_DIR}/bin/python3" ]; then
    current_version="$("${VENV_DIR}/bin/python3" -c \
        'import importlib.metadata; print(importlib.metadata.version("qwenpaw"))')" || exit 1
    if ! "${QWENPAW_PREPARED_RUNTIME}/bin/python3" - "${current_version}" <<'PY'
import importlib.metadata
import sys
from pip._vendor.packaging.version import Version

sys.exit(
    0 if Version(importlib.metadata.version("qwenpaw")) >= Version(sys.argv[1])
    else 1
)
PY
    then
        echo "=== 升级失败：目标版本低于当前版本 ==="
        exit 1
    fi
fi

was_running=false
if [ -f "${pid_file}" ]; then
    IFS= read -r pid < "${pid_file}" || true
    case "${pid:-}" in
        ''|*[!0-9]*) ;;
        *)
            if kill -0 "${pid}" 2>/dev/null; then
                was_running=true
                kill -TERM "${pid}" || exit 1
                count=0
                while kill -0 "${pid}" 2>/dev/null && [ "${count}" -lt 15 ]; do
                    sleep 1
                    count=$((count + 1))
                done
                if kill -0 "${pid}" 2>/dev/null; then
                    echo "=== 升级失败：旧服务未停止，请查看日志 ==="
                    exit 1
                fi
            fi
            ;;
    esac
    rm -f "${pid_file}"
fi
restart_old_runtime() {
    if [ "${was_running}" = true ]; then
        qwenpaw_exec >> "${log_file}" 2>&1 &
        printf '%s\n' "$!" > "${pid_file}"
    fi
}
if ! qwenpaw_snapshot_data; then
    restart_old_runtime
    echo "=== 升级失败：无法备份用户数据 ==="
    exit 1
fi
if ! qwenpaw_prepare_channels "${1:-}"; then
    restart_old_runtime
    echo "=== 升级失败：无法准备旧频道依赖 ==="
    exit 1
fi
if ! qwenpaw_activate_runtime; then
    restart_old_runtime
    echo "=== 升级失败：无法切换运行环境 ==="
    exit 1
fi
if [ "${was_running}" = true ]; then
    qwenpaw_exec >> "${log_file}" 2>&1 &
    pid=$!
    printf '%s\n' "${pid}" > "${pid_file}"
    if ! "${VENV_DIR}/bin/python3" - "${TRIM_SERVICE_PORT}" "${pid}" <<'PY'
import http.client
import os
import sys
import time

port, pid = map(int, sys.argv[1:])
for _ in range(60):
    try:
        os.kill(pid, 0)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/api/version")
        response = conn.getresponse()
        response.read()
        conn.close()
        if response.status == 200:
            sys.exit(0)
    except ProcessLookupError:
        break
    except OSError:
        pass
    time.sleep(1)
sys.exit(1)
PY
    then
        echo "=== 升级失败：新服务未能启动，请查看服务日志 ==="
        exit 1
    fi
fi
rm -f "${TRIM_PKGVAR}/qwenpaw-status.cache"
echo "=== 升级成功 ==="
