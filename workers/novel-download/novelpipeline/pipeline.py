from __future__ import annotations

import json
import logging
from pathlib import Path

from .config import AppConfig, ensure_directories
from .db import StateDB
from .discovery import DiscoveryEngine
from .download import WorkDownloader, work_dir, write_state
from .http import PoliteHttpClient
from .models import WorkMetadata
from .report import build_report
from .sites import KakuyomuSite, NarouSite
from .translate import WorkTranslator


LOG = logging.getLogger("novel-pipeline")


def setup_logging(config: AppConfig) -> None:
    ensure_directories(config)
    LOG.setLevel(logging.INFO)
    if LOG.handlers:
        return
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    LOG.addHandler(stream)
    file_handler = logging.FileHandler(config.pipeline.log_dir / "pipeline.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    LOG.addHandler(file_handler)


class NovelPipeline:
    def __init__(self, config: AppConfig):
        self.config = config
        ensure_directories(config)
        setup_logging(config)
        self.db = StateDB(config.pipeline.data_dir / "state.sqlite3")
        http = PoliteHttpClient(
            user_agent=config.pipeline.user_agent,
            delay_seconds=config.pipeline.request_delay_seconds,
            timeout_seconds=config.pipeline.request_timeout_seconds,
        )
        self.narou = NarouSite(http)
        self.kakuyomu = KakuyomuSite(http)
        self.adapters = {"narou": self.narou, "kakuyomu": self.kakuyomu}
        self.discovery = DiscoveryEngine(config, self.db, self.narou, self.kakuyomu)
        self.downloader = WorkDownloader(config, self.db)

    def discover_only(self) -> tuple[int, int]:
        candidates, new_count = self.discovery.discover()
        build_report(self.config, self.db)
        LOG.info("discovery complete: %d candidates, %d new", len(candidates), new_count)
        return len(candidates), new_count

    @staticmethod
    def _load_metadata(path: Path) -> WorkMetadata:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return WorkMetadata(
            site=payload["site"],
            work_id=payload["work_id"],
            url=payload["url"],
            title=payload.get("title", ""),
            author=payload.get("author", ""),
            summary=payload.get("summary", ""),
            episode_urls=list(payload.get("episode_urls", [])),
            extra=dict(payload.get("extra", {})),
        )

    def _process_work(self, row) -> None:
        site = row["site"]
        work_id = row["work_id"]
        adapter = self.adapters[site]
        root = work_dir(self.config, site, work_id)
        root.mkdir(parents=True, exist_ok=True)
        status = row["status"]
        meta_path = root / "metadata.json"

        if status == "DISCOVERED" or not meta_path.exists():
            LOG.info("metadata %s/%s", site, work_id)
            meta = adapter.fetch_metadata(work_id, row["url"])
            self.downloader.save_metadata(meta)
            status = "METADATA_READY"
        else:
            meta = self._load_metadata(meta_path)

        # Kakuyomu discovery cannot know episode count cheaply before opening the work.
        raw_meta = json.loads(row["metadata_json"] or "{}")
        min_episodes = int(raw_meta.get("min_episodes", 0) or 0)
        if min_episodes and len(meta.episode_urls) < min_episodes:
            self.db.update_work(site, work_id, status="FILTERED", last_error=None)
            write_state(root / "state.json", status="FILTERED", extra={"reason": f"episode_count < {min_episodes}"})
            LOG.info("filtered %s/%s: only %d episodes", site, work_id, len(meta.episode_urls))
            return

        if status in {"DISCOVERED", "METADATA_READY"}:
            LOG.info("download %s/%s first %d", site, work_id, self.config.pipeline.episodes_per_work)
            self.downloader.download(meta, adapter)
            status = "DOWNLOADED"

        if self.config.translation.enabled and status in {"DOWNLOADED", "TRANSLATING"}:
            LOG.info("translate %s/%s", site, work_id)
            translator = WorkTranslator(self.config, self.db)
            translator.translate_work(site, work_id)

    def run(self) -> dict:
        run_id = self.db.start_run()
        discovered = 0
        processed = 0
        errors: list[str] = []
        try:
            candidates, _new_count = self.discovery.discover()
            discovered = len(candidates)
            statuses = ("DISCOVERED", "METADATA_READY")
            if self.config.translation.enabled:
                statuses += ("DOWNLOADED", "TRANSLATING")
            pending = self.db.list_pending(statuses, limit=self.config.pipeline.max_new_works_per_run)
            for row in pending:
                try:
                    self._process_work(row)
                    processed += 1
                except Exception as exc:
                    message = f"{row['site']}/{row['work_id']}: {exc}"
                    errors.append(message)
                    self.db.update_work(row["site"], row["work_id"], last_error=str(exc))
                    root = work_dir(self.config, row["site"], row["work_id"])
                    write_state(root / "state.json", status=row["status"], error=str(exc))
                    LOG.exception("work failed %s/%s", row["site"], row["work_id"])
            build_report(self.config, self.db)
            run_status = "PARTIAL" if errors else "DONE"
            self.db.finish_run(
                run_id,
                status=run_status,
                discovered=discovered,
                processed=processed,
                error="\n".join(errors)[:8000] if errors else None,
            )
            return {"run_id": run_id, "status": run_status, "discovered": discovered, "processed": processed, "errors": errors}
        except Exception as exc:
            self.db.finish_run(run_id, status="ERROR", discovered=discovered, processed=processed, error=str(exc))
            build_report(self.config, self.db)
            raise
