from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .config import ensure_directories, load_config
from .db import StateDB
from .export import export_work
from .pipeline import NovelPipeline, setup_logging
from .report import build_report


def _default_config() -> Path:
    return Path("config.toml").resolve()


def _load(path: str):
    config = load_config(path)
    ensure_directories(config)
    setup_logging(config)
    return config


def cmd_init(args) -> int:
    target = Path(args.config).resolve()
    root = Path(__file__).resolve().parent.parent
    example = root / "config.example.toml"
    if not target.exists():
        shutil.copyfile(example, target)
        print(f"created {target}")
    else:
        print(f"kept existing {target}")
    config = _load(str(target))
    StateDB(config.pipeline.data_dir / "state.sqlite3")
    output = build_report(config, StateDB(config.pipeline.data_dir / "state.sqlite3"))
    print(f"initialized state DB and report: {output}")
    return 0


def cmd_discover(args) -> int:
    pipeline = NovelPipeline(_load(args.config))
    total, new = pipeline.discover_only()
    print(json.dumps({"candidates": total, "new": new}, ensure_ascii=False))
    return 0


def cmd_run(args) -> int:
    result = NovelPipeline(_load(args.config)).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "DONE" else 2


def cmd_status(args) -> int:
    config = _load(args.config)
    db = StateDB(config.pipeline.data_dir / "state.sqlite3")
    rows = db.list_works(limit=args.limit)
    if not rows:
        print("no works")
        return 0
    for row in rows:
        err = f" | error={row['last_error']}" if row["last_error"] else ""
        print(f"{row['site']:8} {row['status']:14} {row['work_id']:20} {row['title'] or '-'}{err}")
    return 0


def cmd_report(args) -> int:
    config = _load(args.config)
    output = build_report(config, StateDB(config.pipeline.data_dir / "state.sqlite3"))
    print(output)
    return 0


def cmd_fetch_work(args) -> int:
    result = export_work(
        url=args.url,
        output_dir=args.output_dir,
        episodes=args.episodes,
        delay_seconds=args.delay,
        timeout_seconds=args.timeout,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="novel-pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create config/state/report scaffold")
    p.add_argument("--config", default=str(_default_config()))
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("discover", help="run discovery and dedupe only")
    p.add_argument("--config", default=str(_default_config()))
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("run", help="run full daily pipeline")
    p.add_argument("--config", default=str(_default_config()))
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("work-status", help="show stored work states")
    p.add_argument("--config", default=str(_default_config()))
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("rebuild-report", help="rebuild static HTML report")
    p.add_argument("--config", default=str(_default_config()))
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("fetch-work", help="export the first N public episodes of one work")
    p.add_argument("--url", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--episodes", type=int, default=5)
    p.add_argument("--delay", type=float, default=1.5)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_fetch_work)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
