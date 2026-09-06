# Operations

## 1. 환경 생성

```bash
cd /projects/novel-daily-pipeline
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 2. 설정 준비

```bash
cp config.example.toml config.toml
```

`config.toml`은 git ignore 대상입니다. 검색 조건과 로컬 경로 변경은 이 파일에서만 합니다.

## 3. 초기화

```bash
.venv/bin/python -m novelpipeline init --config config.toml
```

생성/확인 대상:

- `data/state.sqlite3`
- `data/works/`
- `site/index.html`
- `logs/`

## 4. 수동 실행

탐색만:

```bash
.venv/bin/python -m novelpipeline discover --config config.toml
```

전체 파이프라인:

```bash
.venv/bin/python -m novelpipeline run --config config.toml
```

상태 확인:

```bash
.venv/bin/python -m novelpipeline work-status --config config.toml
```

## 5. 번역 활성화

환경변수 예:

```bash
export OPENAI_API_KEY='...'
export OPENAI_BASE_URL='https://api.openai.com/v1'
export OPENAI_MODEL='...'
```

그 뒤 `config.toml`에서:

```toml
[translation]
enabled = true
```

키는 파일/DB에 기록하지 않습니다. 자동 실행 시에는 프로젝트 `.env`를 `scripts/run_daily.sh`가 읽습니다.

## 6. 매일 실행 등록

예: 매일 09:00

```bash
chmod +x scripts/run_daily.sh scripts/install_launchd.sh
./scripts/install_launchd.sh 9 0
```

등록 파일:

`~/Library/LaunchAgents/com.eiraworks.novel-daily-pipeline.plist`

로그:

- `logs/launchd.out.log`
- `logs/launchd.err.log`
- `logs/pipeline.log`

## 7. 중단/오류 후 재개

동일한 `run` 명령을 다시 실행합니다.

- 다운로드 완료 회차는 URL + SHA-256이 같으면 재사용
- 완료 번역 청크는 source SHA-256이 같으면 재사용
- 오류 청크만 다시 provider를 호출
- 원문 변경 시 해당 청크 hash가 바뀌므로 재번역

## 8. 작품별 확인 위치

```text
data/works/<site>/<work_id>/
  metadata.json
  state.json
  glossary.json
  raw/
  merged/
  chunks/
  translated/
  bilingual/
```

전체 상태는 `site/index.html`에서 확인합니다.
