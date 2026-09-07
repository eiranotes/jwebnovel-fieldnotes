# Private Runtime Mirror

## Why it exists

The canonical repository lives on the external APFS volume:

`/Volumes/DevDrive/Projects/fieldnotes`

macOS background `launchd` jobs on this machine are denied direct reads from that external volume (`Operation not permitted`) even though an interactive Chat On Steroids session can access it. The private console therefore runs from a small **non-Git runtime mirror** on the internal system volume:

`~/HermesWorkspace/project/fieldnotes-runtime`

This is an execution cache, not a second repository or source-of-truth checkout.

## Boot flow

1. Login starts LaunchAgent `com.eiranotes.fieldnotes.runtime-console`.
2. It launches `runtime/scripts/private_console.py` on `127.0.0.1:18765`.
3. Tailscale Serve maps `/fieldnotes` to that loopback server.
4. The iPhone uses the tailnet-only HTTPS URL.

The LaunchAgent no longer needs external-volume permission at boot.

## Sync contract

`python3 scripts/runtime_sync.py pull`

- runtime → canonical
- imports phone-edited search profiles, automation config, queues, rotation state, logs, private preference state, and full-translation workspace state
- derived files such as `work-index.json` and `automation-status.json` are not imported; the canonical job rebuilds them
- run this before the daily canonical job

`python3 scripts/runtime_sync.py push`

- canonical → runtime
- runtime marker의 마지막 동기화 hash와 양쪽 현재 hash를 비교한다
- runtime만 바뀌었으면 먼저 canonical에 import하고, canonical만 바뀌었으면 runtime으로 배포한다
- 양쪽이 마지막 동기화 이후 서로 다르게 바뀌었으면 어느 쪽도 덮어쓰지 않고 `conflict`로 중단한다
- refreshes console code, configs, public state, worker code/venv and local workspace artifacts
- run this after a daily job or after implementation changes

`workspace/learning/`도 mutable private state로 양방향 보존한다. 따라서 phone/private runtime에서 누적된 operational lesson evidence가 code refresh 때문에 사라지지 않는다.

`python3 scripts/runtime_sync.py install`

- first pulls mutable runtime state if a runtime already exists
- then refreshes the complete runtime mirror
- refuses to operate if the runtime contains `.git`

## Invariants

- only `/Volumes/DevDrive/Projects/fieldnotes` is a Git repository
- private/copyrighted text remains local and ignored by Git
- the runtime mirror is tailnet-only and the HTTP server binds only to loopback
- `/api/download` still exposes only files in the explicit artifact inventory; it is not an arbitrary filesystem browser
- raw preference feedback stays under `workspace/` and is not published to GitHub Pages

## Daily Taste delivery

The private runtime exposes daily recommendation reading files without publishing source text to GitHub Pages.

- Combined TXT: `/fieldnotes/api/taste/bundle?date=YYYY-MM-DD&format=txt`
- Per-work ZIP: `/fieldnotes/api/taste/bundle?date=YYYY-MM-DD&format=zip`
- Read-only WebDAV shelf: `/fieldnotes/dav/today/`

The bundle and WebDAV shelf expose only completed sentence-alternating `<원문 제목> - 번역본.txt` files. Original-only and translation-only artifacts are not offered from the reading/download surfaces. The WebDAV surface is read-only at the Field Notes server layer and is intended to be used only through the user's Tailscale network.
