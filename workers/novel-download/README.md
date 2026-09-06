# Novel Daily Pipeline

Narou / Kakuyomu 작품을 매일 조건 검색하고, 신규 후보를 중복 제거한 뒤 앞 5화를 저장하고, 선택적으로 청크 단위 한국어 번역을 수행하는 로컬 자동화 파이프라인입니다.

## 처리 흐름

`discover -> dedupe -> metadata -> first N episodes -> source merge -> glossary/ruby hints -> resumable chunk translation -> bilingual output -> static report`

핵심 상태는 `data/state.sqlite3`에 저장하며, 작품별 원문/번역/용어집/상태 파일은 `data/works/<site>/<work_id>/` 아래에 유지합니다.

## 빠른 시작

```bash
python3.11 -m venv .venv
.venv/bin/pip install 'beautifulsoup4>=4.12,<5'
cp config.example.toml config.toml
.venv/bin/python -m novelpipeline init
.venv/bin/python -m novelpipeline run --config config.toml
```

이 Mac의 시스템 `python3`는 3.9이므로 `python3.11`을 명시해 가상환경을 생성합니다.

검색 조건을 아직 정하지 않았다면 `config.toml`의 discovery 블록을 disabled 상태로 두고 `seeds.urls`에 작품 URL만 넣어도 다운로드 파이프라인을 검증할 수 있습니다.

번역을 켤 때는 `.env.example`의 변수를 실제 환경에 설정하고 `[translation] enabled = true`로 바꿉니다. API 키는 설정 파일/DB/로그에 저장하지 않습니다.

## 주요 명령

```bash
.venv/bin/python -m novelpipeline init
.venv/bin/python -m novelpipeline discover --config config.toml
.venv/bin/python -m novelpipeline run --config config.toml
.venv/bin/python -m novelpipeline work-status --config config.toml
.venv/bin/python -m novelpipeline rebuild-report --config config.toml
.venv/bin/python -m novelpipeline fetch-work --url 'https://kakuyomu.jp/works/...' --output-dir /path/to/source_inbox --episodes 5
```

`fetch-work`는 다른 오케스트레이터가 작품 URL 하나를 넘겨줄 때 쓰는 integration command입니다. 작품 앞 N화를 회차별 TXT와 `acquisition_manifest.json`으로 내보냅니다.

## 자동 실행

macOS에서는 `scripts/install_launchd.sh HH MM`으로 매일 1회 launchd job을 설치할 수 있습니다. 검색 조건과 번역 provider를 먼저 확정한 뒤 활성화하는 것을 전제로 합니다.

현재 상태와 검증 결과는 `docs/STATUS.md`, 운영/복구 절차는 `docs/OPERATIONS.md`에 기록합니다.

## 참고 구현 경계

설계 시 다음 공개 프로젝트의 기능 배치를 참고하되 코드는 직접 복사하지 않는 구조로 작성했습니다.

- `ayati/novel_downloader`: 다중 사이트 다운로드, 범위 다운로드, resume/watch 개념
- `Minekmj/Novel-Syosetu-Kakuyomu-Downloader-Translator`: 검색/다운로드/번역/용어집 모듈 분리
- `ripdog/tsundoku`: 작품별 고유명사 상태와 resumable translation 아이디어. GPL 코드는 포함하지 않음

자세한 결정사항은 `docs/DECISIONS.md`를 참고하십시오.
