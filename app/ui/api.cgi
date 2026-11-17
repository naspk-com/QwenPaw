#!/bin/bash

APP_BASE="${QWENPAW_APP_BASE:-/var/apps/com.dustinky.qwenpaw}"
if ! source "${TRIM_APPDEST:-${APP_BASE}/target}/qwenpaw/runtime.sh" || ! qwenpaw_setup; then
    echo "Status: 503 Service Unavailable"
    echo "Content-Type: application/json; charset=utf-8"
    echo ""
    echo '{"success":false,"message":"运行环境初始化失败，请检查应用运行环境和权限"}'
    exit 0
fi
LOG_FILE="${TRIM_PKGVAR}/qwenpaw.log"
PID_FILE="${TRIM_PKGVAR}/qwenpaw.pid"
UPGRADE_LOG_FILE="${TRIM_PKGVAR}/qwenpaw-upgrade.log"
UPGRADE_PID_FILE="${TRIM_PKGVAR}/qwenpaw-upgrade.pid"
UPGRADE_LOCK_DIR="${TRIM_PKGVAR}/qwenpaw-upgrade.lock"
STATUS_CACHE_FILE="${TRIM_PKGVAR}/qwenpaw-status.cache"
STATUS_CACHE_TTL=60

mkdir -p "$(dirname "${LOG_FILE}")"

check_process() {
    local pid=$1
    if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

refresh_status_cache() {
    if [ -f "${STATUS_CACHE_FILE}" ]; then
        local cache_age
        cache_age=$(($(date +%s) - $(stat -c %Y "${STATUS_CACHE_FILE}" 2>/dev/null || echo 0)))
        if [ "${cache_age}" -lt "${STATUS_CACHE_TTL}" ]; then
            return 0
        fi
    fi

    if [ -f "${VENV_DIR}/bin/python3" ]; then
        source "${VENV_DIR}/bin/activate" 2>/dev/null
        python3 -c "
import importlib.metadata as m
v=''
try: v=m.version('qwenpaw')
except: pass
print(f'version={v}')
" > "${STATUS_CACHE_FILE}" 2>/dev/null
    else
        echo "version=" > "${STATUS_CACHE_FILE}"
    fi
}

invalidate_status_cache() {
    rm -f "${STATUS_CACHE_FILE}"
}

read_log_file_json() {
    local log_file="$1"
    local lines="$2"
    local python="${VENV_DIR}/bin/python3"

    if [ ! -f "${log_file}" ]; then
        echo '{"success":true,"logs":[],"missing":true}'
        return
    fi

    [ -x "${python}" ] || python="/var/apps/python312/target/bin/python3"
    if [ ! -x "${python}" ]; then
        echo '{"success":false,"message":"无法读取日志：Python 运行环境不可用"}'
        return
    fi

    "${python}" - "${log_file}" "${lines}" <<'PY'
import json
import re
import sys
from collections import deque

ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
try:
    with open(sys.argv[1], encoding='utf-8', errors='replace') as source:
        tailed = deque(source, maxlen=int(sys.argv[2]))
    logs = [
        {'message': text}
        for line in tailed
        if (text := ansi_escape.sub('', line.rstrip('\r\n'))).strip()
    ]
    print(json.dumps({'success': True, 'logs': logs}, ensure_ascii=False))
except OSError:
    print(json.dumps({'success': False, 'message': '无法读取日志，请检查文件权限'}, ensure_ascii=False))
PY
}

get_status() {
    local running=false
    local pid=""
    local start_at="null"

    if [ -f "${PID_FILE}" ]; then
        pid=$(head -n 1 "${PID_FILE}" | tr -d '[:space:]')
        if check_process "${pid}"; then
            running=true
            if command -v stat &>/dev/null; then
                start_at=$(stat -c %Y "${PID_FILE}" 2>/dev/null || echo "null")
            fi
        else
            rm -f "${PID_FILE}"
            pid=""
        fi
    fi

    local version=""

    refresh_status_cache
    if [ -f "${STATUS_CACHE_FILE}" ]; then
        source "${STATUS_CACHE_FILE}" 2>/dev/null
        version="${version:-}"
    fi

    echo "Content-Type: application/json"
    echo ""

    local python="${VENV_DIR}/bin/python3" secret_dir=""
    [ -x "${python}" ] || python="/var/apps/python312/target/bin/python3"
    secret_dir="$(get_secret_dir 2>/dev/null)" || secret_dir=""
    "${python}" - "${running}" "${pid}" "${start_at}" "${version:-未知}" \
        "${QWENPAW_AUTH_ENABLED:-}" "${secret_dir}" \
        "${TRIM_SERVICE_PORT}" "${QWENPAW_WORKING_DIR}" "${TRIM_APPDEST}/qwenpaw" <<'PY'
import json
import os
import sys

running, pid, start, version, auth, secret, port, workdir, app_dir = sys.argv[1:]
sys.path.insert(0, app_dir)
from fnos_api import convert_path

configured = None
if secret:
    try:
        with open(os.path.join(secret, "auth.json"), encoding="utf-8") as f:
            configured = bool(json.load(f).get("user"))
    except FileNotFoundError:
        configured = False
    except (OSError, ValueError, AttributeError):
        pass
print(json.dumps({
    "success": True,
    "running": running == "true",
    "pid": pid,
    "startAt": int(start) if start.isdigit() else None,
    "version": version,
    "authEnabled": auth.strip().lower() in ("true", "1", "yes"),
    "authConfigured": configured,
    "port": int(port) if port.isdigit() else None,
    "workingDir": workdir,
    "workingDirDisplay": convert_path(workdir),
}, ensure_ascii=False))
PY
}

status() {
    get_status
}

start_service() {
    if [ "$REQUEST_METHOD" != "POST" ]; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"仅支持 POST 请求\"}"
        exit 0
    fi

    if [ -f "${PID_FILE}" ]; then
        local pid=$(head -n 1 "${PID_FILE}" | tr -d '[:space:]')
        if check_process "${pid}"; then
            echo "Content-Type: application/json"
            echo ""
            echo "{\"success\":true,\"message\":\"QwenPaw 已在运行\"}"
            exit 0
        else
            rm -f "${PID_FILE}"
        fi
    fi

    nohup "${VENV_DIR}/bin/python3" "${TRIM_APPDEST}/qwenpaw/compat.py" \
        app --host 0.0.0.0 --port "${TRIM_SERVICE_PORT}" \
        --log-level "${QWENPAW_LOG_LEVEL}" >> "${LOG_FILE}" 2>&1 &
    echo $! > "${PID_FILE}"

    sleep 2
    if check_process "$(cat "${PID_FILE}" 2>/dev/null)"; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":true,\"message\":\"QwenPaw 启动成功\"}"
    else
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"QwenPaw 启动失败，请查看日志\"}"
    fi
}

stop_service() {
    if [ "$REQUEST_METHOD" != "POST" ]; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"仅支持 POST 请求\"}"
        exit 0
    fi

    if [ -f "${PID_FILE}" ]; then
        local pid=$(head -n 1 "${PID_FILE}" | tr -d '[:space:]')
        if check_process "${pid}"; then
            kill -TERM "${pid}"

            local count=0
            while check_process "${pid}" && [ $count -lt 10 ]; do
                sleep 1
                count=$((count + 1))
            done

            if check_process "${pid}"; then
                kill -KILL "${pid}"
                sleep 1
            fi

            rm -f "${PID_FILE}"
            echo "Content-Type: application/json"
            echo ""
            echo "{\"success\":true,\"message\":\"QwenPaw 已停止\"}"
        else
            rm -f "${PID_FILE}"
            echo "Content-Type: application/json"
            echo ""
            echo "{\"success\":true,\"message\":\"QwenPaw 未在运行\"}"
        fi
    else
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":true,\"message\":\"QwenPaw 未在运行\"}"
    fi
}

restart_service() {
    if [ "$REQUEST_METHOD" != "POST" ]; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"仅支持 POST 请求\"}"
        exit 0
    fi

    if [ -f "${PID_FILE}" ]; then
        local pid=$(head -n 1 "${PID_FILE}" | tr -d '[:space:]')
        if check_process "${pid}"; then
            kill -TERM "${pid}"
            local count=0
            while check_process "${pid}" && [ $count -lt 10 ]; do
                sleep 1
                count=$((count + 1))
            done
            if check_process "${pid}"; then
                kill -KILL "${pid}"
                sleep 1
            fi
        fi
        rm -f "${PID_FILE}"
    fi

    nohup "${VENV_DIR}/bin/python3" "${TRIM_APPDEST}/qwenpaw/compat.py" \
        app --host 0.0.0.0 --port "${TRIM_SERVICE_PORT}" \
        --log-level "${QWENPAW_LOG_LEVEL}" >> "${LOG_FILE}" 2>&1 &
    echo $! > "${PID_FILE}"

    sleep 2
    if check_process "$(cat "${PID_FILE}" 2>/dev/null)"; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":true,\"message\":\"QwenPaw 重启成功\"}"
    else
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"QwenPaw 重启失败，请查看日志\"}"
    fi
}

get_upgrade_status() {
    local upgrading=false
    local upgrade_pid=""

    if [ -f "${UPGRADE_PID_FILE}" ]; then
        upgrade_pid=$(head -n 1 "${UPGRADE_PID_FILE}" | tr -d '[:space:]')
        if check_process "${upgrade_pid}"; then
            upgrading=true
        else
            rm -f "${UPGRADE_PID_FILE}"
        fi
    fi

    echo "Content-Type: application/json"
    echo ""
    echo "{\"success\":true,\"upgrading\":${upgrading}}"
}

upgrade_service() {
    if [ "$REQUEST_METHOD" != "POST" ]; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"仅支持 POST 请求\"}"
        exit 0
    fi

    if ! mkdir "${UPGRADE_LOCK_DIR}" 2>/dev/null; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"升级正在进行中，请稍候\"}"
        exit 0
    fi

    local mirror=""

    if echo "$QUERY_STRING$REQUEST_URI" | grep -q "mirror="; then
        mirror=$(echo "$QUERY_STRING$REQUEST_URI" | sed 's/.*mirror=\([^&]*\).*/\1/')
    fi

    > "${UPGRADE_LOG_FILE}"
    nohup bash "${TRIM_APPDEST}/qwenpaw/console-upgrade.sh" "${mirror}" \
        >> "${UPGRADE_LOG_FILE}" 2>&1 &
    echo $! > "${UPGRADE_PID_FILE}"

    sleep 1

    echo "Content-Type: application/json"
    echo ""
    echo "{\"success\":true,\"message\":\"升级已开始\"}"
}

get_upgrade_logs() {
    local json_output
    json_output=$(read_log_file_json "${UPGRADE_LOG_FILE}" 500)

    echo "Content-Type: application/json"
    echo ""
    if [ -n "${json_output}" ]; then
        echo "${json_output}"
    else
        echo "{\"success\":true,\"logs\":[]}"
    fi
}

get_logs() {
    local json_output
    json_output=$(read_log_file_json "${LOG_FILE}" 500)

    echo "Content-Type: application/json"
    echo ""
    if [ -n "${json_output}" ]; then
        echo "${json_output}"
    else
        echo "{\"success\":true,\"logs\":[]}"
    fi
}

clear_logs() {
    if [ "$REQUEST_METHOD" != "POST" ]; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"仅支持 POST 请求\"}"
        exit 0
    fi

    > "${LOG_FILE}"
    > "${UPGRADE_LOG_FILE}"

    echo "Content-Type: application/json"
    echo ""
    echo "{\"success\":true,\"message\":\"日志已清空\"}"
}

get_secret_dir() {
    "${VENV_DIR}/bin/python3" - "${TRIM_APPDEST}/qwenpaw" <<'PY'
import os
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from snapshot import data_paths
_, secret = data_paths(os.environ, Path(sys.argv[1]) / "code" / ".env")
print(secret)
PY
}

reset_auth() {
    if [ "$REQUEST_METHOD" != "POST" ]; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"仅支持 POST 请求\"}"
        exit 0
    fi

    local secret_dir auth_file
    if ! secret_dir="$(get_secret_dir)"; then
        echo "Content-Type: application/json"
        echo ""
        echo '{"success":false,"message":"无法确定密钥目录，未修改认证文件"}'
        return
    fi
    auth_file="${secret_dir}/auth.json"
    if [ -f "${auth_file}" ]; then
        rm -f "${auth_file}"
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":true,\"message\":\"密码已重置，下次进入 QwenPaw 时将重新设置账号密码\"}"
    else
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":true,\"message\":\"未找到认证文件，无需重置\"}"
    fi
}

check_tunnel_installed() {
    local tunnel_api="/var/apps/com.dustinky.tunnel/target/ui/api.cgi"
    local installed=false

    if [ -f "${tunnel_api}" ]; then
        installed=true
    fi

    echo "Content-Type: application/json"
    echo ""
    echo "{\"success\":true,\"installed\":${installed}}"
}

backup_download() {
    local working_dir="${QWENPAW_WORKING_DIR}"
    local secret_dir
    if ! secret_dir="$(get_secret_dir)"; then
        echo "Content-Type: application/json"
        echo ""
        echo '{"success":false,"message":"无法确定密钥目录，无法备份"}'
        return
    fi
    local backup_name="qwenpaw-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    local tmp_file

    if [ ! -d "${working_dir}" ]; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"工作目录不存在，无法备份\"}"
        exit 0
    fi

    if [ ! -d "${secret_dir}" ]; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"密钥目录不存在，无法备份\"}"
        exit 0
    fi

    if ! tmp_file="$(mktemp "${TMPDIR:-/tmp}/qwenpaw-backup.XXXXXXXX")"; then
        echo "Content-Type: application/json"
        echo ""
        echo '{"success":false,"message":"无法创建临时备份文件"}'
        return
    fi
    if ! tar -czf "${tmp_file}" \
        -C "$(dirname "${working_dir}")" "$(basename "${working_dir}")" \
        -C "$(dirname "${secret_dir}")" "$(basename "${secret_dir}")" 2>/dev/null; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"打包失败，请检查磁盘空间和权限\"}"
        rm -f "${tmp_file}"
        exit 0
    fi

    if [ ! -f "${tmp_file}" ] || [ ! -s "${tmp_file}" ]; then
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"打包失败，文件为空\"}"
        rm -f "${tmp_file}"
        exit 0
    fi

    echo "Content-Type: application/gzip"
    echo "Content-Disposition: attachment; filename=\"${backup_name}\""
    echo ""

    cat "${tmp_file}"
    rm -f "${tmp_file}"
}

action=""

if [ -n "$QUERY_STRING" ]; then
    if echo "$QUERY_STRING" | grep -q "action=status"; then
        action="status"
    elif echo "$QUERY_STRING" | grep -q "action=start"; then
        action="start"
    elif echo "$QUERY_STRING" | grep -q "action=stop"; then
        action="stop"
    elif echo "$QUERY_STRING" | grep -q "action=restart"; then
        action="restart"
    elif echo "$QUERY_STRING" | grep -q "action=upgrade_status"; then
        action="upgrade_status"
    elif echo "$QUERY_STRING" | grep -q "action=upgrade_logs"; then
        action="upgrade_logs"
    elif echo "$QUERY_STRING" | grep -q "action=upgrade"; then
        action="upgrade"
    elif echo "$QUERY_STRING" | grep -q "action=logs"; then
        action="logs"
    elif echo "$QUERY_STRING" | grep -q "action=clear_logs"; then
        action="clear_logs"
    elif echo "$QUERY_STRING" | grep -q "action=reset_auth"; then
        action="reset_auth"
    elif echo "$QUERY_STRING" | grep -q "action=backup_download"; then
        action="backup_download"
    elif echo "$QUERY_STRING" | grep -q "action=check_tunnel"; then
        action="check_tunnel"
    fi
fi

if [ -z "$action" ] && [ -n "$REQUEST_URI" ]; then
    if echo "$REQUEST_URI" | grep -q "action=status"; then
        action="status"
    elif echo "$REQUEST_URI" | grep -q "action=start"; then
        action="start"
    elif echo "$REQUEST_URI" | grep -q "action=stop"; then
        action="stop"
    elif echo "$REQUEST_URI" | grep -q "action=restart"; then
        action="restart"
    elif echo "$REQUEST_URI" | grep -q "action=upgrade_status"; then
        action="upgrade_status"
    elif echo "$REQUEST_URI" | grep -q "action=upgrade_logs"; then
        action="upgrade_logs"
    elif echo "$REQUEST_URI" | grep -q "action=upgrade"; then
        action="upgrade"
    elif echo "$REQUEST_URI" | grep -q "action=logs"; then
        action="logs"
    elif echo "$REQUEST_URI" | grep -q "action=clear_logs"; then
        action="clear_logs"
    elif echo "$REQUEST_URI" | grep -q "action=reset_auth"; then
        action="reset_auth"
    elif echo "$REQUEST_URI" | grep -q "action=backup_download"; then
        action="backup_download"
    elif echo "$REQUEST_URI" | grep -q "action=check_tunnel"; then
        action="check_tunnel"
    fi
fi

case "$action" in
    status)
        status
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    upgrade)
        upgrade_service
        ;;
    upgrade_status)
        get_upgrade_status
        ;;
    upgrade_logs)
        get_upgrade_logs
        ;;
    logs)
        get_logs
        ;;
    clear_logs)
        clear_logs
        ;;
    reset_auth)
        reset_auth
        ;;
    backup_download)
        backup_download
        ;;
    check_tunnel)
        check_tunnel_installed
        ;;
    *)
        echo "Content-Type: application/json"
        echo ""
        echo "{\"success\":false,\"message\":\"无效的操作\"}"
        ;;
esac
