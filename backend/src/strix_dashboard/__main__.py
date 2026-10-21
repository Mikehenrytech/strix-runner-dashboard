"""Command-line entry point for the local dashboard server."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from .app import create_app
from .settings import DashboardSettings


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dashboard local de historial Strix")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--runner", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--frontend", type=Path)
    parser.add_argument("--cache-ttl", type=float)
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Permite escuchar fuera de localhost bajo responsabilidad del usuario",
    )
    return parser


def main() -> None:
    args = make_parser().parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not args.allow_remote:
        raise SystemExit("Utiliza --allow-remote para escuchar fuera de localhost.")
    defaults = DashboardSettings.from_environment()
    settings = DashboardSettings(
        runner=(args.runner or defaults.runner).expanduser(),
        config=(args.config or defaults.config).expanduser(),
        frontend_dist=(args.frontend or defaults.frontend_dist).expanduser(),
        cache_ttl_seconds=(
            args.cache_ttl if args.cache_ttl is not None else defaults.cache_ttl_seconds
        ),
        command_timeout_seconds=defaults.command_timeout_seconds,
        max_history_json_bytes=defaults.max_history_json_bytes,
        max_report_bytes=defaults.max_report_bytes,
    )
    uvicorn.run(
        create_app(settings),
        host=args.host,
        port=args.port,
        server_header=False,
    )


if __name__ == "__main__":
    main()
