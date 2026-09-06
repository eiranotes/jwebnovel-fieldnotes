#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LABEL = "com.eiranotes.fieldnotes.private-console"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
SERVER = ROOT / "scripts" / "private_console.py"
LOG_DIR = Path.home() / "Library" / "Logs" / "Fieldnotes"
PID_FILE = ROOT / "workspace" / "private-console.pid"
TAILSCALE_CANDIDATES = [
    Path("/Applications/Tailscale.app/Contents/MacOS/tailscale"),
    Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale"),
    Path("/opt/homebrew/bin/tailscale"),
    Path("/usr/local/bin/tailscale"),
]


def tailscale_bin() -> Path | None:
    return next((p for p in TAILSCALE_CANDIDATES if p.exists() and os.access(p, os.X_OK)), None)


def main() -> int:
    (ROOT / "workspace").mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if PLIST.exists():
        PLIST.unlink()

    running = False
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            os.kill(old_pid, 0)
            running = True
            print(f"console_pid={old_pid}")
        except Exception:
            PID_FILE.unlink(missing_ok=True)
    if not running:
        out = (ROOT / "workspace" / "private-console.out.log").open("ab")
        err = (ROOT / "workspace" / "private-console.err.log").open("ab")
        proc = subprocess.Popen(
            ["/usr/bin/python3", str(SERVER), "--host", "127.0.0.1", "--port", "18765"],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        PID_FILE.write_text(str(proc.pid) + "\n", encoding="utf-8")
        print(f"console_pid={proc.pid}")

    ts = tailscale_bin()
    if ts:
        subprocess.run([str(ts), "serve", "--bg", "--yes", "--set-path", "/fieldnotes", "http://127.0.0.1:18765"], check=True)
        print("tailnet_url=https://tofu-macbookair.tail05abcf.ts.net/fieldnotes/console.html")
    else:
        print("tailscale=not-found; local_url=http://127.0.0.1:18765/console.html")
    print("autostart=disabled_by_macos_external_volume_privacy")
    print("restart_command=python3 scripts/install_private_console.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
