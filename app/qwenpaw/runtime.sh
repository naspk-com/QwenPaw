#!/bin/bash
# Shared runtime paths for fnOS lifecycle scripts and the management CGI.

qwenpaw_setup() {
    local base="${QWENPAW_APP_BASE:-/var/apps/com.dustinky.qwenpaw}"
    TRIM_APPDEST="${TRIM_APPDEST:-${base}/target}"
    TRIM_PKGHOME="${TRIM_PKGHOME:-${base}/home}"
    TRIM_PKGETC="${TRIM_PKGETC:-${base}/etc}"
    TRIM_PKGVAR="${TRIM_PKGVAR:-${base}/var}"
    TRIM_DATA_SHARE_PATHS="${TRIM_DATA_SHARE_PATHS:-${base}/shares/com.dustinky.qwenpaw}"
    TRIM_SERVICE_PORT="${TRIM_SERVICE_PORT:-19091}"
    export TRIM_APPDEST TRIM_PKGHOME TRIM_PKGETC TRIM_PKGVAR TRIM_DATA_SHARE_PATHS TRIM_SERVICE_PORT
    export HOME="${TRIM_PKGETC}"
    export QWENPAW_WORKING_DIR="${TRIM_DATA_SHARE_PATHS%%:*}/.qwenpaw"
    export QWENPAW_AUTH_ENABLED=true
    local saved_log_level=""
    if [ -r "${TRIM_PKGETC}/qwenpaw-log-level" ]; then
        IFS= read -r saved_log_level < "${TRIM_PKGETC}/qwenpaw-log-level" || true
    fi
    case "${wizard_log_level:-${saved_log_level:-info}}" in
        debug|info|warning|error|critical)
            export QWENPAW_LOG_LEVEL="${wizard_log_level:-${saved_log_level:-info}}"
            ;;
        *)
            echo "QwenPaw: invalid log level" >&2
            return 1
            ;;
    esac
    export QWENPAW_DEPENDENCY_STATE_DIR="${QWENPAW_DEPENDENCY_STATE_DIR:-${TRIM_PKGHOME}/dependency-environments}"
    export PATH="/var/apps/nodejs_v24/target/bin:${PATH}"
    QWENPAW_RUNTIME_FILE="${TRIM_PKGHOME}/qwenpaw-active-runtime"
    VENV_DIR="${TRIM_PKGHOME}/venv"
    if [ -f "${QWENPAW_RUNTIME_FILE}" ]; then
        local candidate runtime_root_real candidate_real
        IFS= read -r candidate < "${QWENPAW_RUNTIME_FILE}" || true
        case "${candidate}" in
            /*) ;;
            *) echo "QwenPaw: invalid active runtime path" >&2; return 1 ;;
        esac
        runtime_root_real="$(cd -P -- "${TRIM_PKGHOME}/qwenpaw-runtimes" 2>/dev/null && pwd -P)" || runtime_root_real=""
        candidate_real="$(cd -P -- "${candidate}" 2>/dev/null && pwd -P)" || candidate_real=""
        if [ -z "${runtime_root_real}" ] || [ -z "${candidate_real}" ]; then
            echo "QwenPaw: invalid active runtime path or missing runtime" >&2
            return 1
        fi
        case "${candidate_real}/" in
            "${runtime_root_real}"/*/) ;;
            *) echo "QwenPaw: invalid active runtime path" >&2; return 1 ;;
        esac
        if [ ! -x "${candidate_real}/bin/python3" ]; then
            echo "QwenPaw: active runtime is missing: ${candidate}" >&2
            return 1
        fi
        VENV_DIR="${candidate}"
    fi
    export VENV_DIR QWENPAW_RUNTIME_FILE
}

qwenpaw_save_log_level() {
    local value="${1:-}" temporary
    case "${value}" in
        debug|info|warning|error|critical) ;;
        *) qwenpaw_report_error "无效的日志级别"; return 1 ;;
    esac
    mkdir -p "${TRIM_PKGETC}" || return 1
    temporary="$(mktemp "${TRIM_PKGETC}/.qwenpaw-log-level.XXXXXXXX")" || return 1
    printf '%s\n' "${value}" > "${temporary}" && \
        mv -f "${temporary}" "${TRIM_PKGETC}/qwenpaw-log-level"
}

qwenpaw_exec() {
    exec "${VENV_DIR}/bin/python3" "${TRIM_APPDEST}/qwenpaw/compat.py" \
        app --host 0.0.0.0 --port "${TRIM_SERVICE_PORT}" \
        --log-level "${QWENPAW_LOG_LEVEL}"
}

qwenpaw_report_error() {
    echo "QwenPaw: $*" >&2
    if [ -n "${TRIM_TEMP_LOGFILE:-}" ]; then
        printf '%s\n' "QwenPaw: $*" >> "${TRIM_TEMP_LOGFILE}"
    fi
}

qwenpaw_has_newer_pypi_runtime() {
    [ -x "${VENV_DIR}/bin/python3" ] || return 1
    "${VENV_DIR}/bin/python3" - "${TRIM_APPDEST}/qwenpaw/code/src/qwenpaw/__version__.py" <<'PY'
import ast
import importlib.metadata
import json
import sys
from pip._vendor.packaging.version import Version

try:
    dist = importlib.metadata.distribution("qwenpaw")
    direct = json.loads(dist.read_text("direct_url.json") or "{}")
    if direct.get("dir_info", {}).get("editable"):
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        tree = ast.parse(f.read())
    versions = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)
    ]
    if len(versions) != 1:
        sys.exit(2)
    sys.exit(0 if Version(dist.version) > Version(versions[0]) else 1)
except Exception:
    sys.exit(2)
PY
}

qwenpaw_prepare_runtime() {
    local source="$1" mirror="${2:-}" runtime_root new_runtime
    local -a pip_options=()
    case "${mirror}" in
        tsinghua) pip_options=(-i https://pypi.tuna.tsinghua.edu.cn/simple) ;;
        aliyun) pip_options=(-i https://mirrors.aliyun.com/pypi/simple/) ;;
        ustc) pip_options=(-i https://pypi.mirrors.ustc.edu.cn/simple/) ;;
        ""|pypi|official) ;;
        *) qwenpaw_report_error "未知的 Python 镜像源"; return 1 ;;
    esac

    if [ "${source}" = "bundle" ]; then
        source="${TRIM_APPDEST}/qwenpaw/code"
        if [ ! -f "${source}/src/qwenpaw/console/index.html" ]; then
            qwenpaw_report_error "安装包缺少官方控制台，请重新构建应用包"
            return 1
        fi
    elif [ "${source}" = "pypi" ]; then
        source="qwenpaw"
    else
        qwenpaw_report_error "未知的升级来源"
        return 1
    fi
    runtime_root="${TRIM_PKGHOME}/qwenpaw-runtimes"
    mkdir -p "${runtime_root}" || return 1
    new_runtime="$(mktemp -d "${runtime_root}/runtime.XXXXXXXX")" || return 1
    if ! /var/apps/python312/target/bin/python3 -m venv "${new_runtime}"; then
        qwenpaw_report_error "创建新运行环境失败，原环境未删除"
        return 1
    fi
    if ! "${new_runtime}/bin/python3" -m pip install --upgrade \
        "${pip_options[@]}" "${source}"; then
        qwenpaw_report_error "安装新版本失败，原环境未删除"
        return 1
    fi
    if ! "${new_runtime}/bin/python3" -m pip check; then
        qwenpaw_report_error "新运行环境依赖检查失败，原环境未删除"
        return 1
    fi
    if ! "${new_runtime}/bin/python3" -c \
        'import importlib.metadata; print(importlib.metadata.version("qwenpaw"))'; then
        qwenpaw_report_error "无法读取新版本，原环境未删除"
        return 1
    fi
    QWENPAW_PREPARED_RUNTIME="${new_runtime}"
    export QWENPAW_PREPARED_RUNTIME
}

qwenpaw_activate_runtime() {
    local pointer
    [ -x "${QWENPAW_PREPARED_RUNTIME:-}/bin/python3" ] || return 1
    pointer="$(mktemp "${TRIM_PKGHOME}/.qwenpaw-runtime.XXXXXXXX")" || return 1
    if ! printf '%s\n' "${QWENPAW_PREPARED_RUNTIME}" > "${pointer}" || \
        ! mv -f "${pointer}" "${QWENPAW_RUNTIME_FILE}"; then
        qwenpaw_report_error "无法切换运行环境，原环境未删除"
        return 1
    fi
    VENV_DIR="${QWENPAW_PREPARED_RUNTIME}"
    export VENV_DIR
}

qwenpaw_snapshot_data() {
    "${QWENPAW_PREPARED_RUNTIME}/bin/python3" \
        "${TRIM_APPDEST}/qwenpaw/snapshot.py"
}

qwenpaw_prepare_channels() {
    local mirror="${1:-}" index=""
    case "${mirror}" in
        tsinghua) index=https://pypi.tuna.tsinghua.edu.cn/simple ;;
        aliyun) index=https://mirrors.aliyun.com/pypi/simple/ ;;
        ustc) index=https://pypi.mirrors.ustc.edu.cn/simple/ ;;
        ""|pypi|official) ;;
        *) return 1 ;;
    esac
    if ! "${QWENPAW_PREPARED_RUNTIME}/bin/python3" -c \
        'import importlib.metadata as m; from pip._vendor.packaging.version import Version; import sys; sys.exit(0 if Version(m.version("qwenpaw")) >= Version("2.3.0") else 1)'; then
        return 0
    fi
    if [ -n "${index}" ]; then
        PIP_INDEX_URL="${index}" "${QWENPAW_PREPARED_RUNTIME}/bin/python3" \
            "${TRIM_APPDEST}/qwenpaw/compat.py" plugin prepare-upgrade
    else
        "${QWENPAW_PREPARED_RUNTIME}/bin/python3" \
            "${TRIM_APPDEST}/qwenpaw/compat.py" plugin prepare-upgrade
    fi
}
