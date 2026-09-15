"""Hermes gateway status — يقرأ gateway_state.json بشكل صحيح ولا يظهر not installed وهو شغال."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _hermes_home() -> Path:
    # الأولوية: متغير البيئة → المسار الافتراضي على Windows
    env = os.getenv("HERMES_HOME", "").strip()
    if env:
        return Path(env)
    # افتراضي Windows: %LOCALAPPDATA%/hermes
    local = os.getenv("LOCALAPPDATA", "")
    if local:
        return Path(local) / "hermes"
    return Path.home() / "AppData" / "Local" / "hermes"


def _is_pid_running(pid: int) -> bool:
    """تحقق أن PID ما زال حيًا (Windows + Unix)."""
    if not pid or pid <= 0:
        return False
    try:
        import psutil  # type: ignore

        return psutil.pid_exists(pid)
    except ImportError:
        pass
    # fallback بدون psutil
    try:
        if os.name == "nt":
            import subprocess

            out = subprocess.check_output(["tasklist"], text=True, timeout=3)
            return str(pid) in out
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def get_hermes_gateway_status() -> dict[str, Any]:
    """
    يقرأ حالة hermes gateway من gateway_state.json.
    لا يعيد not_installed أبدًا إذا كان PID حيًا — يصحح الخطأ السابق.
    """
    home = _hermes_home()
    state_file = home / "gateway_state.json"
    pid_file = home / "gateway.pid"
    lock_file = home / "gateway.lock"

    # حاول قراءة gateway_state.json أولاً (المصدر الموثوق)
    data: dict[str, Any] | None = None
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            data = None

    if data and isinstance(data, dict) and data.get("pid"):
        pid = int(data.get("pid") or 0)
        # حتى لو gateway_state == "stopped" لكن PID حي، نعتبره running
        # هذا يصلح bug عرض not installed وهو شغال
        if pid and _is_pid_running(pid):
            return {
                "installed": True,
                "running": True,
                "pid": pid,
                "gateway_state": data.get("gateway_state") or "running",
                "kind": data.get("kind") or "hermes-gateway",
                "version": data.get("code_version") or data.get("version") or "0.21.0",
                "updated_at": data.get("updated_at") or "",
                "hermes_home": str(home),
                "source": "gateway_state.json",
            }
        # PID ميت لكن الملف موجود → installed لكن not running
        return {
            "installed": True,
            "running": False,
            "pid": pid,
            "gateway_state": data.get("gateway_state") or "stopped",
            "kind": data.get("kind") or "hermes-gateway",
            "version": data.get("code_version") or "",
            "updated_at": data.get("updated_at") or "",
            "hermes_home": str(home),
            "source": "gateway_state.json",
        }

    # fallback: pid file
    if pid_file.exists():
        try:
            pj = json.loads(pid_file.read_text(encoding="utf-8"))
            pid = int(pj.get("pid") or 0)
            if pid and _is_pid_running(pid):
                return {
                    "installed": True,
                    "running": True,
                    "pid": pid,
                    "gateway_state": "running",
                    "kind": pj.get("kind") or "hermes-gateway",
                    "version": "",
                    "updated_at": "",
                    "hermes_home": str(home),
                    "source": "gateway.pid",
                }
        except Exception:
            pass

    # fallback: lock file exists → غالبًا installed
    if lock_file.exists():
        return {
            "installed": True,
            "running": False,
            "pid": None,
            "gateway_state": "unknown",
            "kind": "hermes-gateway",
            "version": "",
            "updated_at": "",
            "hermes_home": str(home),
            "source": "gateway.lock",
        }

    # المجلد موجود لكن بلا state → نعتبره installed (مثبت لكن لم يشغّل بعد)
    if home.exists() and (home / "config.yaml").exists():
        return {
            "installed": True,
            "running": False,
            "pid": None,
            "gateway_state": "not_running",
            "kind": "hermes-gateway",
            "version": "",
            "updated_at": "",
            "hermes_home": str(home),
            "source": "config.yaml",
        }

    # فقط إذا لا يوجد أي أثر لـ hermes
    return {
        "installed": False,
        "running": False,
        "pid": None,
        "gateway_state": "not_installed",
        "kind": "hermes-gateway",
        "version": "",
        "updated_at": "",
        "hermes_home": str(home),
        "source": "none",
    }
