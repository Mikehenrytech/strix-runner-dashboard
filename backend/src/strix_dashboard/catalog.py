"""Read, normalize, filter, and safely expose Strix history."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .settings import DashboardSettings


class DashboardError(Exception):
    """A bounded error suitable for returning through the local API."""

    def __init__(self, message: str, status_code: int = 500):
        self.status_code = status_code
        super().__init__(message)


class RunnerHistorySource:
    """Load the runner's versioned history JSON without invoking a shell."""

    def __init__(self, settings: DashboardSettings):
        self.settings = settings

    def load(self) -> dict[str, Any]:
        runner = self.settings.runner.resolve()
        if not runner.is_file():
            raise DashboardError(f"No existe strix_runner.py: {runner}", 503)
        command = [
            sys.executable,
            str(runner),
            "--config",
            str(self.settings.config),
            "history",
            "--all",
            "--json",
        ]
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        try:
            result = subprocess.run(
                command,
                cwd=runner.parent,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.settings.command_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DashboardError(
                f"No se pudo consultar el historial: {exc}",
                503,
            ) from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            if len(detail) > 1_000:
                detail = detail[:1_000] + "..."
            raise DashboardError(
                detail or "El runner no pudo generar el historial.",
                503,
            )
        if len(result.stdout) > self.settings.max_history_json_bytes:
            raise DashboardError("El historial supera el tamaño permitido.", 503)
        try:
            payload = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DashboardError(
                "El runner devolvió un historial JSON inválido.",
                503,
            ) from exc
        if not isinstance(payload, dict):
            raise DashboardError("La raíz del historial debe ser un objeto.", 503)
        return payload


@dataclass(frozen=True)
class HistorySnapshot:
    """One immutable-in-practice normalized history generation."""

    generated_at: str | None
    loaded_at: float
    runs: tuple[dict[str, Any], ...]
    by_id: dict[str, dict[str, Any]]


def _stable_id(run: dict[str, Any]) -> str:
    identity = str(run.get("run_dir") or run.get("run_id") or run.get("run_name") or "")
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _run_profile(run: dict[str, Any]) -> str:
    profile = run.get("profile")
    if isinstance(profile, str) and profile:
        return profile
    candidates = _as_list(run.get("profile_candidates"))
    return str(candidates[0]) if candidates else "Sin asociar"


def _run_day(run: dict[str, Any]) -> str:
    start_time = run.get("start_time")
    return start_time[:10] if isinstance(start_time, str) else ""


def _run_tokens(run: dict[str, Any]) -> int:
    value = _as_dict(run.get("llm_usage")).get("total_tokens", 0)
    return int(value) if isinstance(value, (int, float)) else 0


def _run_models(run: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    models: list[str] = []
    for agent in _as_list(run.get("agents")):
        if not isinstance(agent, dict):
            continue
        model = agent.get("model")
        if isinstance(model, str) and model and model not in seen:
            seen.add(model)
            models.append(model)
    return models


def _run_agents(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _as_list(run.get("agents")) if isinstance(item, dict)]


def _run_skills(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        skill
        for agent in _run_agents(run)
        for skill in _as_list(agent.get("skills"))
        if isinstance(skill, dict)
    ]


class HistoryCatalog:
    """Cache and query a versioned history payload."""

    def __init__(
        self,
        settings: DashboardSettings,
        loader: Callable[[], dict[str, Any]],
    ):
        self.settings = settings
        self.loader = loader
        self._snapshot: HistorySnapshot | None = None
        self._lock = threading.Lock()

    def snapshot(self, *, force: bool = False) -> HistorySnapshot:
        now = time.monotonic()
        current = self._snapshot
        if (
            not force
            and current is not None
            and now - current.loaded_at < self.settings.cache_ttl_seconds
        ):
            return current
        with self._lock:
            current = self._snapshot
            now = time.monotonic()
            if (
                not force
                and current is not None
                and now - current.loaded_at < self.settings.cache_ttl_seconds
            ):
                return current
            payload = self.loader()
            if payload.get("schema_version") != 1:
                raise DashboardError("Versión de historial no soportada.", 503)
            raw_runs = payload.get("runs")
            if not isinstance(raw_runs, list):
                raise DashboardError("El historial no contiene una lista de runs.", 503)
            runs: list[dict[str, Any]] = []
            by_id: dict[str, dict[str, Any]] = {}
            for raw_run in raw_runs:
                if not isinstance(raw_run, dict):
                    continue
                run = copy.deepcopy(raw_run)
                stable_id = _stable_id(run)
                run["stable_id"] = stable_id
                runs.append(run)
                by_id[stable_id] = run
            current = HistorySnapshot(
                generated_at=(
                    str(payload.get("generated_at"))
                    if payload.get("generated_at")
                    else None
                ),
                loaded_at=now,
                runs=tuple(runs),
                by_id=by_id,
            )
            self._snapshot = current
            return current

    def summary(self, *, force: bool = False) -> dict[str, Any]:
        snapshot = self.snapshot(force=force)
        return self.filtered_summary(snapshot, excluded_ids=set())

    def filtered_summary(
        self,
        snapshot: HistorySnapshot,
        *,
        excluded_ids: set[str],
    ) -> dict[str, Any]:
        runs = [run for run in snapshot.runs if run["stable_id"] not in excluded_ids]
        statuses: dict[str, int] = {}
        utilities: dict[str, int] = {}
        timeline: dict[str, dict[str, int]] = {}
        profiles: set[str] = set()
        findings = 0
        unknown_findings = 0
        agent_count = 0
        skill_count = 0
        total_tokens = 0
        durations: list[float] = []
        for run in runs:
            profile = _run_profile(run)
            profiles.add(profile)
            status = str(run.get("status") or "unknown")
            statuses[status] = statuses.get(status, 0) + 1
            value = run.get("findings")
            if isinstance(value, int):
                findings += value
            else:
                unknown_findings += 1
            duration = run.get("duration_seconds")
            if isinstance(duration, (int, float)):
                durations.append(float(duration))
            agents = _run_agents(run)
            skills = _run_skills(run)
            agent_count += len(agents)
            skill_count += len(skills)
            total_tokens += _run_tokens(run)
            for skill in skills:
                utility = str(skill.get("utility") or "not_observable")
                utilities[utility] = utilities.get(utility, 0) + 1
            day = _run_day(run)
            if day:
                point = timeline.setdefault(
                    day,
                    {"runs": 0, "findings": 0, "tokens": 0},
                )
                point["runs"] += 1
                point["findings"] += value if isinstance(value, int) else 0
                point["tokens"] += _run_tokens(run)
        return {
            "generated_at": snapshot.generated_at,
            "runs": len(runs),
            "excluded_runs": len(snapshot.runs) - len(runs),
            "profiles": len(profiles),
            "findings": findings,
            "runs_with_unknown_findings": unknown_findings,
            "agents": agent_count,
            "skills": skill_count,
            "total_tokens": total_tokens,
            "average_duration_seconds": (
                sum(durations) / len(durations) if durations else None
            ),
            "statuses": dict(sorted(statuses.items())),
            "utilities": dict(sorted(utilities.items())),
            "timeline": [
                {"date": day, **values}
                for day, values in sorted(timeline.items())
            ],
        }

    def summary_excluding(
        self,
        excluded_ids: set[str],
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        return self.filtered_summary(
            self.snapshot(force=force),
            excluded_ids=excluded_ids,
        )

    def facets(
        self,
        *,
        excluded_ids: set[str] | None = None,
        force: bool = False,
    ) -> dict[str, list[str]]:
        snapshot = self.snapshot(force=force)
        profiles: set[str] = set()
        statuses: set[str] = set()
        agents: set[str] = set()
        skills: set[str] = set()
        utilities: set[str] = set()
        excluded_ids = excluded_ids or set()
        for run in snapshot.runs:
            if run["stable_id"] in excluded_ids:
                continue
            profiles.add(_run_profile(run))
            statuses.add(str(run.get("status") or "unknown"))
            for agent in _run_agents(run):
                name = agent.get("name")
                if isinstance(name, str) and name:
                    agents.add(name)
                for skill in _as_list(agent.get("skills")):
                    if not isinstance(skill, dict):
                        continue
                    skill_name = skill.get("name")
                    if isinstance(skill_name, str) and skill_name:
                        skills.add(skill_name)
                    utilities.add(str(skill.get("utility") or "not_observable"))
        return {
            "profiles": sorted(profiles, key=str.casefold),
            "statuses": sorted(statuses, key=str.casefold),
            "agents": sorted(agents, key=str.casefold),
            "skills": sorted(skills, key=str.casefold),
            "utilities": sorted(utilities, key=str.casefold),
        }

    def list_runs(
        self,
        *,
        profile: str | None = None,
        status: str | None = None,
        agent: str | None = None,
        skill: str | None = None,
        utility: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        search: str | None = None,
        sort_by: str = "start_time",
        order: str = "desc",
        page: int = 1,
        page_size: int = 25,
        excluded_ids: set[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        snapshot = self.snapshot(force=force)
        query = (search or "").strip().casefold()
        excluded_ids = excluded_ids or set()

        def matches(run: dict[str, Any]) -> bool:
            if run["stable_id"] in excluded_ids:
                return False
            agents = _run_agents(run)
            skills = _run_skills(run)
            if profile and _run_profile(run) != profile:
                return False
            if status and str(run.get("status") or "unknown") != status:
                return False
            if agent and not any(item.get("name") == agent for item in agents):
                return False
            if skill and not any(item.get("name") == skill for item in skills):
                return False
            if utility and not any(
                str(item.get("utility") or "not_observable") == utility
                for item in skills
            ):
                return False
            day = _run_day(run)
            if from_date and (not day or day < from_date):
                return False
            if to_date and (not day or day > to_date):
                return False
            if query:
                searchable = json.dumps(
                    {
                        "run_id": run.get("run_id"),
                        "run_name": run.get("run_name"),
                        "profile": _run_profile(run),
                        "run_dir_relative": run.get("run_dir_relative"),
                        "targets": run.get("targets"),
                        "agents": agents,
                        "models": _run_models(run),
                    },
                    ensure_ascii=False,
                ).casefold()
                if query not in searchable:
                    return False
            return True

        filtered = [run for run in snapshot.runs if matches(run)]
        key_functions: dict[str, Callable[[dict[str, Any]], Any]] = {
            "start_time": lambda run: run.get("start_time"),
            "profile": _run_profile,
            "status": lambda run: run.get("status"),
            "findings": lambda run: run.get("findings"),
            "duration_seconds": lambda run: run.get("duration_seconds"),
            "total_tokens": _run_tokens,
        }
        key_function = key_functions.get(sort_by, key_functions["start_time"])
        present = [run for run in filtered if key_function(run) is not None]
        missing = [run for run in filtered if key_function(run) is None]
        present.sort(key=key_function, reverse=order == "desc")
        filtered = present + missing
        total = len(filtered)
        start = (page - 1) * page_size
        items = [self._list_item(run) for run in filtered[start : start + page_size]]
        return {
            "generated_at": snapshot.generated_at,
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
            "excluded_runs": sum(
                run["stable_id"] in excluded_ids for run in snapshot.runs
            ),
        }

    def detail(self, stable_id: str, *, force: bool = False) -> dict[str, Any]:
        run = self.snapshot(force=force).by_id.get(stable_id)
        if run is None:
            raise DashboardError("Ejecución no encontrada.", 404)
        result = copy.deepcopy(run)
        report_available = bool(result.get("report_path"))
        result.pop("run_dir", None)
        result.pop("report_path", None)
        result.pop("report_uri", None)
        result["profile_label"] = _run_profile(run)
        result["report_available"] = report_available
        result["report_url"] = (
            f"/api/v1/runs/{stable_id}/report" if report_available else None
        )
        if "models" not in result:
            result["models"] = _run_models(run)
        return result

    def report(self, stable_id: str) -> tuple[str, str]:
        run = self.snapshot().by_id.get(stable_id)
        if run is None:
            raise DashboardError("Ejecución no encontrada.", 404)
        report_value = run.get("report_path")
        run_value = run.get("run_dir")
        if not isinstance(report_value, str) or not isinstance(run_value, str):
            raise DashboardError("La ejecución no tiene informe.", 404)
        try:
            root = self._runs_root()
            run_dir = Path(run_value).resolve()
            report = Path(report_value).resolve()
            run_dir.relative_to(root)
            report.relative_to(run_dir)
        except (OSError, ValueError) as exc:
            raise DashboardError("Ruta de informe no permitida.", 404) from exc
        if report.name != "penetration_test_report.md" or not report.is_file():
            raise DashboardError("Informe no encontrado.", 404)
        try:
            if report.stat().st_size > self.settings.max_report_bytes:
                raise DashboardError("El informe supera el tamaño permitido.", 413)
            content = report.read_text(encoding="utf-8", errors="replace")
        except DashboardError:
            raise
        except OSError as exc:
            raise DashboardError("No se pudo leer el informe.", 404) from exc
        return content, report.name

    def _runs_root(self) -> Path:
        if self.settings.runs_root_override is not None:
            return self.settings.runs_root_override.resolve()
        try:
            payload = json.loads(self.settings.config.read_text(encoding="utf-8"))
            path_strix = payload["globals"]["path_strix"]
            if not isinstance(path_strix, str) or not path_strix:
                raise KeyError("path_strix")
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise DashboardError("No se pudo resolver PATH_STRIX.", 503) from exc
        return Path(os.path.expandvars(path_strix)).expanduser().resolve() / "strix_runs"

    @staticmethod
    def _list_item(run: dict[str, Any]) -> dict[str, Any]:
        agents = _run_agents(run)
        skills = _run_skills(run)
        return {
            "stable_id": run["stable_id"],
            "selection_id": run.get("selection_id"),
            "run_id": run.get("run_id"),
            "run_name": run.get("run_name"),
            "profile": _run_profile(run),
            "run_dir_relative": run.get("run_dir_relative"),
            "start_time": run.get("start_time"),
            "end_time": run.get("end_time"),
            "status": run.get("status"),
            "findings": run.get("findings"),
            "severity_counts": _as_dict(run.get("severity_counts")),
            "duration_seconds": run.get("duration_seconds"),
            "agents": len(agents),
            "skills": len(skills),
            "total_tokens": _run_tokens(run),
            "models": _run_models(run),
            "report_available": bool(run.get("report_path")),
        }
