#!/usr/bin/env python3
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = Path.home() / "HermesWorkspace" / "project" / "fieldnotes-runtime"
LABEL = "com.eiranotes.fieldnotes.runtime-console"
OLD_LABELS = (
    "com.eiranotes.fieldnotes.private-console",
    "com.eiranotes.fieldnotes.autostart",
)
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs" / "Fieldnotes"
HELPER_APP = Path.home() / "Applications" / "Fieldnotes Autostart.app"
TAILSCALE_CANDIDATES = (
    Path("/Applications/Tailscale.app/Contents/MacOS/tailscale"),
    Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale"),
    Path("/opt/homebrew/bin/tailscale"),
    Path("/usr/local/bin/tailscale"),
)


def run(args: list[str], *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=check, text=True, capture_output=capture)


def tailscale_bin() -> Path | None:
    return next((p for p in TAILSCALE_CANDIDATES if p.exists() and os.access(p, os.X_OK)), None)


def install_runtime() -> None:
    run(["/usr/bin/python3", str(ROOT / "scripts" / "runtime_sync.py"), "install"])
    server = RUNTIME / "scripts" / "private_console.py"
    if not server.is_file():
        raise SystemExit(f"Runtime server missing after sync: {server}")
    if (RUNTIME / ".git").exists():
        raise SystemExit(f"Runtime mirror must not contain .git: {RUNTIME}")


def remove_old_services(uid: int) -> None:
    labels = (*OLD_LABELS, LABEL)
    for label in labels:
        run(["launchctl", "bootout", f"gui/{uid}/{label}"], check=False)
        old_plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        if label != LABEL:
            old_plist.unlink(missing_ok=True)
    run(["/usr/bin/pkill", "-x", "FieldnotesAutostart"], check=False)
    if HELPER_APP.exists():
        shutil.rmtree(HELPER_APP, ignore_errors=True)


def write_launch_agent() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [
            "/usr/bin/python3",
            str(RUNTIME / "scripts" / "private_console.py"),
            "--host", "127.0.0.1",
            "--port", "18765",
        ],
        "WorkingDirectory": str(RUNTIME),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "ThrottleInterval": 10,
        "StandardOutPath": str(LOG_DIR / "runtime-console.out.log"),
        "StandardErrorPath": str(LOG_DIR / "runtime-console.err.log"),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    }
    with PLIST.open("wb") as fp:
        plistlib.dump(payload, fp, sort_keys=False)


def bootstrap(uid: int) -> None:
    run(["launchctl", "bootstrap", f"gui/{uid}", str(PLIST)])
    run(["launchctl", "kickstart", "-k", f"gui/{uid}/{LABEL}"])


def configure_tailscale() -> str:
    binary = tailscale_bin()
    if not binary:
        return "not_found"
    run([
        str(binary), "serve", "--bg", "--yes", "--set-path", "/fieldnotes",
        "http://127.0.0.1:18765",
    ])
    return str(binary)


def verify_server() -> bool:
    import urllib.request

    for _ in range(20):
        try:
            with urllib.request.urlopen("http://127.0.0.1:18765/api/state", timeout=1.5) as response:
                return response.status == 200
        except Exception:
            time.sleep(0.25)
    return False


def main() -> int:
    uid = os.getuid()
    install_runtime()
    remove_old_services(uid)
    write_launch_agent()
    bootstrap(uid)
    ts = configure_tailscale()
    ok = verify_server()
    print(f"runtime_root={RUNTIME}")
    print(f"runtime_git_repo={(RUNTIME / '.git').exists()}")
    print(f"launch_agent={PLIST}")
    print(f"autostart={'enabled_and_verified' if ok else 'enabled_but_server_not_verified'}")
    print(f"tailscale={ts}")
    print("tailnet_url=https://tofu-macbookair.tail05abcf.ts.net/fieldnotes/console.html")
    if not ok:
        raise SystemExit("Runtime console did not become reachable on 127.0.0.1:18765")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
