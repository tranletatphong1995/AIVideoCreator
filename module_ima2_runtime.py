"""Runtime helpers for the optional ima2-gen / ChatGPT online mode."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests


DEFAULT_IMA2_URL = "http://127.0.0.1:3333"
DEFAULT_OAUTH_URL = "http://127.0.0.1:10531"


def ima2_server_json_path() -> Path:
    return Path.home() / ".ima2" / "server.json"


def read_ima2_server_info() -> dict:
    path = ima2_server_json_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def resolve_ima2_server_url(configured_url: str = "") -> str:
    configured_url = (configured_url or "").strip().rstrip("/")
    if configured_url and configured_url != DEFAULT_IMA2_URL:
        return configured_url

    info = read_ima2_server_info()
    backend = info.get("backend") if isinstance(info.get("backend"), dict) else {}
    url = backend.get("url") or info.get("url") or configured_url or DEFAULT_IMA2_URL
    return str(url).rstrip("/")


def resolve_ima2_oauth_url(configured_server_url: str = "") -> str:
    info = read_ima2_server_info()
    oauth = info.get("oauth") if isinstance(info.get("oauth"), dict) else {}
    url = oauth.get("url")
    if url:
        return str(url).rstrip("/")

    server_url = resolve_ima2_server_url(configured_server_url)
    try:
        response = requests.get(f"{server_url}/api/providers", timeout=5)
        if response.status_code < 500:
            data = response.json()
            for key in ("oauth", "data"):
                block = data.get(key) if isinstance(data, dict) else None
                if isinstance(block, dict):
                    candidate = block.get("url") or block.get("oauthUrl")
                    if candidate:
                        return str(candidate).rstrip("/")
    except Exception:
        pass

    return DEFAULT_OAUTH_URL


def is_ima2_server_ready(server_url: str = "") -> bool:
    url = resolve_ima2_server_url(server_url)
    try:
        response = requests.get(f"{url}/api/health", timeout=3)
        return response.status_code < 500
    except Exception:
        return False


def wait_for_ima2_server(server_url: str = "", timeout_sec: int = 120) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if is_ima2_server_ready(server_url):
            return True
        time.sleep(2)
    return False


def launch_ima2_server(command: str = "npx --yes ima2-gen serve") -> None:
    command = (command or "").strip() or "npx --yes ima2-gen serve"
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    if os.name == "nt":
        subprocess.Popen(
            ["cmd", "/k", command],
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    else:
        subprocess.Popen(command, env=env, shell=True)


def run_chatgpt_login(command: str = "npx --yes @openai/codex login") -> int:
    command = (command or "").strip() or "npx --yes @openai/codex login"
    if os.name == "nt":
        process = subprocess.Popen(
            ["cmd", "/k", command],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return process.pid

    process = subprocess.Popen(command, shell=True)
    return process.pid


def check_node_version(min_major: int = 20) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        version = (completed.stdout or completed.stderr or "").strip()
        major = int(version.lstrip("v").split(".", 1)[0])
        return major >= min_major, version
    except Exception as exc:
        return False, str(exc)


def check_npx_ima2() -> tuple[bool, str]:
    try:
        if os.name == "nt":
            command = ["cmd", "/c", "npx", "--yes", "ima2-gen", "--help"]
        else:
            command = ["npx", "--yes", "ima2-gen", "--help"]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )
        output = (completed.stdout or completed.stderr or "").strip()
        return completed.returncode == 0, output[:400]
    except Exception as exc:
        return False, str(exc)


def print_safe(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(message.encode(encoding, errors="replace").decode(encoding))
