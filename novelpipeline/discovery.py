from __future__ import annotations

from .config import AppConfig
from .db import StateDB
from .models import WorkCandidate
from .sites import KakuyomuSite, NarouSite


class DiscoveryEngine:
    def __init__(self, config: AppConfig, db: StateDB, narou: NarouSite, kakuyomu: KakuyomuSite):
        self.config = config
        self.db = db
        self.narou = narou
        self.kakuyomu = kakuyomu

    def _seed_candidates(self) -> list[WorkCandidate]:
        result: list[WorkCandidate] = []
        for url in self.config.seed_urls:
            work_id = self.narou.parse_work_id(url)
            if work_id:
                result.append(WorkCandidate(site="narou", work_id=work_id, url=self.narou.work_url(work_id), source_query="seed"))
                continue
            work_id = self.kakuyomu.parse_work_id(url)
            if work_id:
                result.append(WorkCandidate(site="kakuyomu", work_id=work_id, url=self.kakuyomu.work_url(work_id), source_query="seed"))
        return result

    def discover(self) -> tuple[list[WorkCandidate], int]:
        candidates: dict[tuple[str, str], WorkCandidate] = {}
        for query in self.config.narou_queries:
            for item in self.narou.discover(query):
                candidates[(item.site, item.work_id)] = item
        for query in self.config.kakuyomu_queries:
            for item in self.kakuyomu.discover(query):
                candidates.setdefault((item.site, item.work_id), item)
        for item in self._seed_candidates():
            candidates.setdefault((item.site, item.work_id), item)

        new_count = 0
        for item in candidates.values():
            if self.db.upsert_candidate(item):
                new_count += 1
        return list(candidates.values()), new_count
