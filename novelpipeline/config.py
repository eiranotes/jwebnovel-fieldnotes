from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class PipelineConfig:
    root: Path
    data_dir: Path
    site_dir: Path
    log_dir: Path
    episodes_per_work: int = 5
    max_new_works_per_run: int = 10
    request_delay_seconds: float = 1.5
    request_timeout_seconds: float = 30.0
    user_agent: str = "novel-daily-pipeline/0.1 (personal automation)"


@dataclass(slots=True)
class TranslationConfig:
    enabled: bool = False
    provider: str = "openai_compatible"
    model_env: str = "OPENAI_MODEL"
    api_key_env: str = "OPENAI_API_KEY"
    base_url_env: str = "OPENAI_BASE_URL"
    chunk_chars: int = 6500
    previous_context_chars: int = 1200
    temperature: float = 0.2


@dataclass(slots=True)
class AppConfig:
    path: Path
    pipeline: PipelineConfig
    translation: TranslationConfig
    narou_queries: list[dict] = field(default_factory=list)
    kakuyomu_queries: list[dict] = field(default_factory=list)
    seed_urls: list[str] = field(default_factory=list)


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as fh:
        raw = tomllib.load(fh)

    root = config_path.parent
    p = raw.get("pipeline", {})
    pipeline = PipelineConfig(
        root=root,
        data_dir=_resolve(root, p.get("data_dir", "data")),
        site_dir=_resolve(root, p.get("site_dir", "site")),
        log_dir=_resolve(root, p.get("log_dir", "logs")),
        episodes_per_work=int(p.get("episodes_per_work", 5)),
        max_new_works_per_run=int(p.get("max_new_works_per_run", 10)),
        request_delay_seconds=float(p.get("request_delay_seconds", 1.5)),
        request_timeout_seconds=float(p.get("request_timeout_seconds", 30)),
        user_agent=str(p.get("user_agent", "novel-daily-pipeline/0.1 (personal automation)")),
    )

    t = raw.get("translation", {})
    translation = TranslationConfig(
        enabled=bool(t.get("enabled", False)),
        provider=str(t.get("provider", "openai_compatible")),
        model_env=str(t.get("model_env", "OPENAI_MODEL")),
        api_key_env=str(t.get("api_key_env", "OPENAI_API_KEY")),
        base_url_env=str(t.get("base_url_env", "OPENAI_BASE_URL")),
        chunk_chars=int(t.get("chunk_chars", 6500)),
        previous_context_chars=int(t.get("previous_context_chars", 1200)),
        temperature=float(t.get("temperature", 0.2)),
    )

    discovery = raw.get("discovery", {})
    seeds = raw.get("seeds", {})
    return AppConfig(
        path=config_path,
        pipeline=pipeline,
        translation=translation,
        narou_queries=list(discovery.get("narou", [])),
        kakuyomu_queries=list(discovery.get("kakuyomu", [])),
        seed_urls=[str(x).strip() for x in seeds.get("urls", []) if str(x).strip()],
    )


def ensure_directories(config: AppConfig) -> None:
    config.pipeline.data_dir.mkdir(parents=True, exist_ok=True)
    (config.pipeline.data_dir / "works").mkdir(parents=True, exist_ok=True)
    config.pipeline.site_dir.mkdir(parents=True, exist_ok=True)
    config.pipeline.log_dir.mkdir(parents=True, exist_ok=True)
