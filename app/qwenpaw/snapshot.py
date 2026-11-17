"""Create a private, consistent pre-upgrade archive after the service stops."""

import os
import base64
import json
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from cryptography.fernet import Fernet, InvalidToken

from compat import apply_legacy_environment


def data_paths(environ, project_env):
    env = dict(environ)
    workdir = Path(env["QWENPAW_WORKING_DIR"]).expanduser().resolve()
    files = (project_env, workdir / ".env")
    apply_legacy_environment(env, files)
    values = {}
    for path in files:
        if path.is_file():
            for key, value in dotenv_values(path).items():
                if value is not None:
                    values.setdefault(key, value)
    values.update(env)
    secret = Path(
        values.get("QWENPAW_SECRET_DIR") or f"{workdir}.secret"
    ).expanduser().resolve()
    return workdir, secret


def snapshot(workdir, secret, destination):
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(destination, 0o700)
    for path in (workdir, secret):
        if destination.resolve().is_relative_to(path.resolve()):
            raise ValueError("backup directory is inside a source directory")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fd, temporary = tempfile.mkstemp(prefix=".snapshot-", dir=destination)
    final = destination / f"qwenpaw-{timestamp}-{Path(temporary).name[10:]}.tar.gz"
    try:
        with os.fdopen(fd, "wb") as stream:
            with tarfile.open(fileobj=stream, mode="w:gz") as archive:
                for path in dict.fromkeys((workdir, secret)):
                    if path.exists():
                        archive.add(path, arcname=str(path).lstrip("/"), recursive=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, final)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return final


def verify_file_key(workdir, secret):
    """Refuse migration when existing encrypted credentials cannot be read."""
    paths = [
        workdir / "config.json",
        workdir / "envs.json",
        workdir / "providers.json",
        secret / "envs.json",
        secret / "providers.json",
        secret / "community_credentials.json",
    ]
    for root in (workdir / "providers", secret / "providers"):
        if root.is_dir():
            paths.extend(root.rglob("*.json"))

    def encrypted_values(value):
        if isinstance(value, dict):
            for child in value.values():
                yield from encrypted_values(child)
        elif isinstance(value, list):
            for child in value:
                yield from encrypted_values(child)
        elif isinstance(value, str) and value.startswith("ENC:gAAAA"):
            yield value[4:].encode("ascii")

    tokens = []
    for path in dict.fromkeys(paths):
        if path.is_file():
            with path.open(encoding="utf-8") as stream:
                tokens.extend(encrypted_values(json.load(stream)))
    if not tokens:
        return
    key_file = secret / ".master_key"
    if not key_file.is_file():
        raise ValueError("存在加密凭据，但密钥文件不存在")
    key = bytes.fromhex(key_file.read_text(encoding="utf-8").strip())
    if len(key) != 32:
        raise ValueError("主密钥文件格式无效")
    fernet = Fernet(base64.urlsafe_b64encode(key))
    try:
        for token in tokens:
            fernet.decrypt(token)
    except InvalidToken as exc:
        raise ValueError("无法使用现有主密钥解密凭据") from exc


def main():
    base = Path(__file__).resolve().parent
    workdir, secret = data_paths(os.environ, base / "code" / ".env")
    archive = snapshot(workdir, secret, Path(os.environ["TRIM_PKGHOME"]) / "qwenpaw-backups")
    print(f"升级前数据快照已创建: {archive}")
    verify_file_key(workdir, secret)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"创建升级前数据快照失败: {exc}", file=sys.stderr)
        sys.exit(1)
