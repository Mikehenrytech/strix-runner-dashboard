"""Runtime settings for the local dashboard."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNNER = PROJECT_ROOT.parent / "strix-runner" / "strix_runner.py"
DEFAULT_FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
DEFAULT_CONFIG = Path(
    os.environ.get(
        "STRIX_RUNNER_CONFIG",
        "~/.config/strix-runner/config.json",
    )
).expanduser()


@dataclass(frozen=True)
class DashboardSettings:
    """Paths and bounded resource limits used by the dashboard."""

    runner: Path = DEFAULT_RUNNER
    config: Path = DEFAULT_CONFIG
    frontend_dist: Path = DEFAULT_FRONTEND_DIST
    cache_ttl_seconds: float = 15.0
    command_timeout_seconds: float = 60.0
    max_history_json_bytes: int = 100 * 1024 * 1024
    max_report_bytes: int = 10 * 1024 * 1024
    runs_root_override: Path | None = None

    @classmethod
    def from_environment(cls) -> "DashboardSettings":
        """Load optional dashboard overrides from environment variables."""
        runner_path = os.environ.get(
            "STRIX_DASHBOARD_RUNNER",
            os.environ.get("STRIX_RUNNER_PATH", str(DEFAULT_RUNNER)),
        )
        return cls(
            runner=Path(runner_path).expanduser(),
            config=Path(
                os.environ.get("STRIX_RUNNER_CONFIG", str(DEFAULT_CONFIG))
            ).expanduser(),
            frontend_dist=Path(
                os.environ.get(
                    "STRIX_DASHBOARD_FRONTEND",
                    str(DEFAULT_FRONTEND_DIST),
                )
            ).expanduser(),
            cache_ttl_seconds=float(
                os.environ.get("STRIX_DASHBOARD_CACHE_TTL", "15")
            ),
        )
