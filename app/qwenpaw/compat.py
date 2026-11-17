"""Compatibility launcher for environment variables from older releases."""

import os
import runpy
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv


# These variables were read through EnvVarLoader in the 1.x/2.0 releases
# and are still consumed by the current upstream release.
LEGACY_NAMES = (
    "WORKING_DIR",
    "SECRET_DIR",
    "BACKUP_DIR",
    "CONFIG_FILE",
    "HEARTBEAT_FILE",
    "JOBS_FILE",
    "CHATS_FILE",
    "TOKEN_USAGE_FILE",
    "DEBUG_HISTORY_FILE",
    "DESKTOP_PORT",
    "RUNNING_IN_CONTAINER",
    "MODEL_PROVIDER_CHECK_TIMEOUT",
    "OPENAPI_DOCS",
    "MEMORY_COMPACT_KEEP_RECENT",
    "MEMORY_COMPACT_RATIO",
    "CORS_ORIGINS",
    "UPLOAD_MAX_SIZE_MB",
    "LLM_MAX_RETRIES",
    "LLM_BACKOFF_BASE",
    "LLM_BACKOFF_CAP",
    "LLM_MAX_CONCURRENT",
    "LLM_MAX_QPM",
    "LLM_RATE_LIMIT_PAUSE",
    "LLM_RATE_LIMIT_JITTER",
    "LLM_ACQUIRE_TIMEOUT",
    "TOOL_GUARD_APPROVAL_TIMEOUT_SECONDS",
    "TOOL_GUARD_APPROVAL_HEARTBEAT_INTERVAL",
)


def apply_legacy_environment(environ, env_files=()):
    """Fill missing modern names without overwriting explicit modern values."""
    values = {}
    for path in env_files:
        if path and Path(path).is_file():
            for key, value in dotenv_values(path).items():
                if value is not None:
                    values.setdefault(key, value)
    values.update(environ)
    for suffix in LEGACY_NAMES:
        modern = "QWENPAW_" + suffix
        legacy = "COPAW_" + suffix
        if modern not in values and legacy in values:
            environ[modern] = values[legacy]


def main():
    workdir = os.environ.get("QWENPAW_WORKING_DIR")
    project_env = Path(__file__).resolve().parent / "code" / ".env"
    workdir_env = Path(workdir) / ".env" if workdir else None
    env_files = ()
    if not os.environ.get("QWENPAW_RUNTIME_ID"):
        env_files = (project_env, workdir_env)
        for path in (project_env, workdir_env):
            if path and path.is_file():
                load_dotenv(path, override=False)
    apply_legacy_environment(os.environ, env_files)
    sys.argv[0] = "qwenpaw"
    runpy.run_module("qwenpaw", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
