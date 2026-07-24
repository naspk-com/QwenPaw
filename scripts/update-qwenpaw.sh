#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
CODE_DIR="${PROJECT_ROOT}/app/qwenpaw/code"
UI_FN_DESIGN="${PROJECT_ROOT}/ui-fndesign"
WWW_DIR="${PROJECT_ROOT}/app/www"
MD_FILES_DIR="${CODE_DIR}/src/qwenpaw/agents/md_files"
MANIFEST_PATH="${PROJECT_ROOT}/manifest"
SIDEBAR_PATH="${UI_FN_DESIGN}/src/components/DesktopSidebar.vue"
DIST_DIR="${PROJECT_ROOT}/dist"
UPSTREAM_URL="https://github.com/agentscope-ai/QwenPaw.git"

TMP_BASE="${HOME}/.cache/qwenpaw"
mkdir -p "${TMP_BASE}"
TEMP_DIR="$(mktemp -d "${TMP_BASE}/temp.XXXXXX")"
BACKUP_DIR="$(mktemp -d "${TMP_BASE}/backup.XXXXXX")"

cleanup() {
    rm -rf "${TEMP_DIR}" "${BACKUP_DIR}"
}
trap cleanup EXIT

usage() {
    cat <<'EOF'
Usage: scripts/update-qwenpaw.sh <new_version> <changelog>

Examples:
  scripts/update-qwenpaw.sh 1.1.12 "更新上游代码，修复若干问题"
  scripts/update-qwenpaw.sh 1.2.0 "新增XX功能，优化YY体验"
EOF
}

manifest_value() {
    local key="$1"
    awk -F= -v key="${key}" '
        $1 ~ "^[[:space:]]*" key "[[:space:]]*$" {
            value = $2
            sub(/^[[:space:]]+/, "", value)
            sub(/[[:space:]]+$/, "", value)
            gsub(/^'\''|'\''$/, "", value)
            print value
            exit
        }
    ' "${MANIFEST_PATH}"
}

# ── 安全检查：确保 CODE_DIR 不是 Git 仓库顶层 ──
check_git_safety() {
    local git_toplevel
    git_toplevel="$(cd "${CODE_DIR}" && git rev-parse --show-toplevel 2>/dev/null || true)"

    if [ -z "${git_toplevel}" ]; then
        echo "警告: ${CODE_DIR} 不在任何 Git 仓库中"
        return 0
    fi

    local abs_code_dir
    abs_code_dir="$(cd "${CODE_DIR}" && pwd)"

    if [ "${git_toplevel}" = "${abs_code_dir}" ]; then
        echo "错误: ${CODE_DIR} 是 Git 仓库顶层！" >&2
        echo "这样会导致 git 操作覆盖整个项目根目录。" >&2
        echo "请确保 ${CODE_DIR} 是上游代码的存放目录，而不是 Git 仓库根目录。" >&2
        exit 1
    fi

    echo "安全检查通过: CODE_DIR 是 Git 仓库子目录，顶层为 ${git_toplevel}"
}

# ── 备份自定义 MEMORY.md 文件 ──
backup_memory_files() {
    echo "==> 备份自定义 MEMORY.md 文件"
    for lang in zh en ru id; do
        local src="${MD_FILES_DIR}/${lang}/MEMORY.md"
        if [ -f "${src}" ]; then
            local dest="${BACKUP_DIR}/MEMORY_${lang}.md"
            cp "${src}" "${dest}"
            echo "    已备份: ${lang}/MEMORY.md"
        fi
    done
}

# ── 恢复自定义 MEMORY.md 文件 ──
restore_memory_files() {
    echo "==> 恢复自定义 MEMORY.md 文件"
    for lang in zh en ru id; do
        local backup="${BACKUP_DIR}/MEMORY_${lang}.md"
        local dest="${MD_FILES_DIR}/${lang}/MEMORY.md"
        if [ -f "${backup}" ]; then
            mkdir -p "$(dirname "${dest}")"
            cp "${backup}" "${dest}"
            echo "    已恢复: ${lang}/MEMORY.md"
        fi
    done
}

# ── 克隆上游并同步到 CODE_DIR ──
sync_upstream() {
    echo "==> 克隆上游仓库到临时目录"
    echo "    上游: ${UPSTREAM_URL}"
    echo "    临时目录: ${TEMP_DIR}"

    git clone --depth 1 "${UPSTREAM_URL}" "${TEMP_DIR}"

    local upstream_commit
    upstream_commit="$(cd "${TEMP_DIR}" && git log -1 --oneline)"
    echo "    上游最新: ${upstream_commit}"

    echo "==> 同步上游代码到 CODE_DIR"
    echo "    目标: ${CODE_DIR}"

    mkdir -p "${CODE_DIR}"

    local rsync_items=(
        "src/"
        "plugins/"
        "pyproject.toml"
        "setup.py"
        ".python-version"
    )

    for item in "${rsync_items[@]}"; do
        if [ -e "${TEMP_DIR}/${item}" ]; then
            rsync -av --delete "${TEMP_DIR}/${item}" "${CODE_DIR}/${item}"
            echo "    已同步: ${item}"
        fi
    done

    echo "    同步完成"
}

# ── 构建前端控制台 ──
build_console() {
    echo "==> 构建前端控制台"

    if [ ! -d "${TEMP_DIR}/console" ]; then
        echo "    console 目录不存在于上游，跳过构建"
        return
    fi

    echo "    从临时目录构建 console"

    local console_src="${TEMP_DIR}/console"
    local console_dest="${CODE_DIR}/console"

    mkdir -p "${console_dest}"

    cd "${console_src}"
    npm ci
    npm run build

    cd "${CODE_DIR}"

    mkdir -p "src/qwenpaw/console"
    cp -R "${console_src}/dist/." "src/qwenpaw/console/"

    echo "    控制台构建完成"
}

# ── 构建 UI 前端 (ui-fndesign) ──
build_ui_fndesign() {
    echo "==> 构建 UI 前端 (ui-fndesign)"

    if ! command -v pnpm >/dev/null 2>&1; then
        echo "错误: pnpm 未安装" >&2
        exit 1
    fi

    cd "${UI_FN_DESIGN}"
    pnpm install --frozen-lockfile
    pnpm build

    if [ ! -f "${WWW_DIR}/index.html" ]; then
        echo "错误: 构建失败，未生成 index.html" >&2
        exit 1
    fi

    echo "    UI 前端构建完成"
}

# ── 更新版本号 ──
update_versions() {
    local new_version="$1"
    local changelog="$2"

    echo "==> 更新版本号: ${new_version}"

    local python_script
    python_script="$(cat <<'PYEOF'
import re
import sys

manifest_path = sys.argv[1]
changelog = sys.argv[2]
version = sys.argv[3]

with open(manifest_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(
    r'^version\s*=.*$',
    f'version                    = {version}',
    content,
    flags=re.MULTILINE
)

changelog_escaped = changelog.replace('"', '\\"')
content = re.sub(
    r'^changelog\s*=.*$',
    f'changelog                  = "{changelog_escaped}"',
    content,
    flags=re.MULTILINE
)

with open(manifest_path, 'w', encoding='utf-8') as f:
    f.write(content)
PYEOF
)"

    python3 -c "${python_script}" "${MANIFEST_PATH}" "${changelog}" "${new_version}"

    perl -pi -e "s/v[0-9]+\.[0-9]+\.[0-9]+/v${new_version}/" "${SIDEBAR_PATH}"

    echo "    版本号已更新"
}

# ── 构建 fpk 包 ──
build_fpk() {
    echo "==> 构建 fnOS 应用包"

    ensure_tools

    local app_name
    local version
    local default_fpk
    local target_fpk

    app_name="$(manifest_value appname)"
    version="$(manifest_value version)"
    default_fpk="${PROJECT_ROOT}/${app_name}.fpk"
    target_fpk="${DIST_DIR}/${app_name}_v${version}.fpk"

    mkdir -p "${DIST_DIR}"
    rm -f "${default_fpk}" "${target_fpk}"

    cd "${PROJECT_ROOT}"
    fnpack build --directory "${PROJECT_ROOT}"

    if [ ! -f "${default_fpk}" ]; then
        echo "打包失败: 未找到 ${default_fpk}" >&2
        exit 1
    fi

    mv "${default_fpk}" "${target_fpk}"
    echo "==> 已生成: ${target_fpk}"
}

ensure_tools() {
    command -v fnpack >/dev/null 2>&1 || {
        echo "fnpack not found in PATH" >&2
        exit 1
    }
}

# ── 主流程 ──
main() {
    if [ "$#" -ne 2 ]; then
        usage >&2
        exit 1
    fi

    local new_version="$1"
    local changelog="$2"

    echo "============================================"
    echo " QwenPaw 更新脚本"
    echo " 新版本: ${new_version}"
    echo " 更新日志: ${changelog}"
    echo "============================================"
    echo ""

    # 0. 安全检查
    check_git_safety

    # 1. 备份自定义 MEMORY.md
    backup_memory_files

    # 2. 克隆上游并同步
    sync_upstream

    # 3. 恢复自定义 MEMORY.md
    restore_memory_files

    # 4. 构建前端控制台
    build_console

    # 5. 更新版本号（先更新再构建，确保产物包含版本信息）
    update_versions "${new_version}" "${changelog}"

    # 6. 构建 UI 前端
    build_ui_fndesign

    # 7. 构建 fpk 包
    build_fpk

    local app_name
    app_name="$(manifest_value appname)"

    echo ""
    echo "============================================"
    echo " 更新完成!"
    echo " 版本: ${new_version}"
    echo " 包路径: ${DIST_DIR}/${app_name}_v${new_version}.fpk"
    echo "============================================"
}

main "$@"
