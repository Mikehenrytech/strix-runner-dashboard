from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from strix_dashboard.app import create_app
from strix_dashboard.catalog import (
    DashboardError,
    HistoryCatalog,
    RunnerHistorySource,
)
from strix_dashboard.settings import DashboardSettings


def sample_payload(run_dir: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": "2026-10-08T13:00:00+02:00",
        "runs": [
            {
                "selection_id": 1,
                "run_id": "run-001",
                "run_name": run_dir.name,
                "run_dir": str(run_dir),
                "run_dir_relative": "strix_runs/run-one",
                "profile": "payments-api",
                "profile_candidates": ["payments-api"],
                "profile_source": "captured",
                "start_time": "2026-10-08T10:00:00+02:00",
                "end_time": "2026-10-08T10:02:00+02:00",
                "status": "completed",
                "findings": 3,
                "severity_counts": {"high": 1, "medium": 2},
                "duration_seconds": 120.0,
                "targets": ["https://example.test"],
                "report_path": str(run_dir / "penetration_test_report.md"),
                "report_uri": "file:///not-exposed",
                "command": ["uv", "run", "strix"],
                "command_display": "uv run strix",
                "command_source": "captured",
                "command_gaps": [],
                "agents": [
                    {
                        "agent_id": "agent-1",
                        "name": "recon",
                        "status": "completed",
                        "task": "Mapear superficie",
                        "model": "openai/gpt-4o",
                        "skills": [
                            {
                                "name": "asset-discovery",
                                "utility": "high",
                                "reason": "Encontró endpoints",
                                "evidence": [],
                            }
                        ],
                    },
                    {
                        "agent_id": "agent-2",
                        "name": "planner",
                        "status": "completed",
                        "model": "openai/gpt-4o-mini",
                        "skills": [],
                    },
                ],
                "llm_usage": {"total_tokens": 4200},
            },
            {
                "selection_id": 2,
                "run_id": "run-002",
                "run_name": "older-run",
                "run_dir": str(run_dir.parent / "older-run"),
                "profile": "catalog-web",
                "profile_candidates": ["catalog-web"],
                "start_time": "2026-10-01T09:00:00+02:00",
                "status": "stopped",
                "findings": None,
                "severity_counts": {},
                "duration_seconds": None,
                "targets": ["https://catalog.test"],
                "report_path": None,
                "agents": [],
                "llm_usage": {"total_tokens": 100},
            },
        ],
    }


class StaticLoader:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload
        self.calls = 0

    def __call__(self) -> dict[str, object]:
        self.calls += 1
        return copy.deepcopy(self.payload)


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name) / "strix_runs"
        self.run_dir = self.root / "run-one"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "penetration_test_report.md").write_text(
            "# Informe\n\nContenido seguro.",
            encoding="utf-8",
        )
        self.settings = DashboardSettings(
            cache_ttl_seconds=30,
            runs_root_override=self.root,
            frontend_dist=Path(self.temp_dir.name) / "missing-dist",
        )
        self.loader = StaticLoader(sample_payload(self.run_dir))
        self.catalog = HistoryCatalog(self.settings, self.loader)

    def test_summary_facets_and_cache(self) -> None:
        summary = self.catalog.summary()
        facets = self.catalog.facets()

        self.assertEqual(summary["runs"], 2)
        self.assertEqual(summary["findings"], 3)
        self.assertEqual(summary["utilities"], {"high": 1})
        self.assertEqual(facets["profiles"], ["catalog-web", "payments-api"])
        self.assertEqual(facets["skills"], ["asset-discovery"])
        self.assertEqual(self.loader.calls, 1)

    def test_exclusions_affect_summary_facets_and_list(self) -> None:
        first = self.catalog.list_runs()["items"][0]
        excluded = {first["stable_id"]}

        summary = self.catalog.summary_excluding(excluded)
        facets = self.catalog.facets(excluded_ids=excluded)
        runs = self.catalog.list_runs(excluded_ids=excluded)

        self.assertEqual(summary["runs"], 1)
        self.assertEqual(summary["excluded_runs"], 1)
        self.assertEqual(summary["findings"], 0)
        self.assertEqual(facets["profiles"], ["catalog-web"])
        self.assertEqual(facets["skills"], [])
        self.assertEqual(runs["total"], 1)
        self.assertEqual(runs["excluded_runs"], 1)

    def test_filters_pagination_and_stable_ids(self) -> None:
        first = self.catalog.list_runs(profile="payments-api", page_size=1)
        second = self.catalog.list_runs(search="catalog", status="stopped")

        self.assertEqual(first["total"], 1)
        self.assertEqual(first["items"][0]["findings"], 3)
        self.assertEqual(second["total"], 1)
        self.assertEqual(second["items"][0]["profile"], "catalog-web")
        self.assertEqual(
            first["items"][0]["stable_id"],
            self.catalog.list_runs(profile="payments-api")["items"][0]["stable_id"],
        )

    def test_detail_hides_filesystem_paths_and_serves_report(self) -> None:
        stable_id = self.catalog.list_runs()["items"][0]["stable_id"]
        detail = self.catalog.detail(stable_id)
        content, filename = self.catalog.report(stable_id)

        self.assertNotIn("run_dir", detail)
        self.assertNotIn("report_path", detail)
        self.assertTrue(detail["report_available"])
        self.assertEqual(filename, "penetration_test_report.md")
        self.assertIn("Contenido seguro", content)
        self.assertEqual(detail["run_dir_relative"], "strix_runs/run-one")
        self.assertEqual(detail["models"], ["openai/gpt-4o", "openai/gpt-4o-mini"])

    def test_list_exposes_run_dir_relative_and_models(self) -> None:
        items = self.catalog.list_runs()["items"]
        self.assertEqual(len(items), 2)
        first, second = items
        self.assertEqual(first["run_dir_relative"], "strix_runs/run-one")
        self.assertEqual(first["models"], ["openai/gpt-4o", "openai/gpt-4o-mini"])
        self.assertIsNone(second["run_dir_relative"])
        self.assertEqual(second["models"], [])

    def test_report_rejects_path_outside_runs_root(self) -> None:
        outside = Path(self.temp_dir.name) / "outside.md"
        outside.write_text("secret", encoding="utf-8")
        payload = sample_payload(self.run_dir)
        payload["runs"][0]["report_path"] = str(outside)  # type: ignore[index]
        catalog = HistoryCatalog(self.settings, StaticLoader(payload))
        stable_id = catalog.list_runs()["items"][0]["stable_id"]

        with self.assertRaises(DashboardError):
            catalog.report(stable_id)

    def test_read_only_api(self) -> None:
        client = TestClient(create_app(self.settings, self.catalog))

        health = client.get("/api/v1/health")
        runs = client.get("/api/v1/runs", params={"skill": "asset-discovery"})
        stable_id = runs.json()["items"][0]["stable_id"]
        detail = client.get(f"/api/v1/runs/{stable_id}")
        report = client.get(f"/api/v1/runs/{stable_id}/report")

        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json()["readonly"])
        self.assertEqual(runs.json()["total"], 1)
        self.assertNotIn("run_dir", detail.json())
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.headers["x-content-type-options"], "nosniff")
        self.assertIn("default-src 'self'", report.headers["content-security-policy"])
        self.assertEqual(client.post("/api/v1/runs").status_code, 405)
        self.assertEqual(
            client.get("/api/v1/runs", params={"from": "not-a-date"}).status_code,
            422,
        )
        excluded = client.get(
            "/api/v1/summary",
            params=[("exclude", stable_id)],
        )
        self.assertEqual(excluded.status_code, 200)
        self.assertEqual(excluded.json()["runs"], 1)
        self.assertEqual(excluded.json()["excluded_runs"], 1)
        self.assertEqual(
            client.get("/api/v1/summary", params={"exclude": "bad"}).status_code,
            422,
        )

    @mock.patch("strix_dashboard.catalog.subprocess.run")
    def test_runner_source_uses_argument_list_without_shell(self, run_mock) -> None:
        runner = Path(self.temp_dir.name) / "strix_runner.py"
        runner.write_text("# fixture", encoding="utf-8")
        settings = DashboardSettings(
            runner=runner,
            config=Path(self.temp_dir.name) / "config.json",
        )
        run_mock.return_value = mock.Mock(
            returncode=0,
            stdout=b'{"schema_version":1,"runs":[]}',
            stderr=b"",
        )

        payload = RunnerHistorySource(settings).load()

        self.assertEqual(payload["schema_version"], 1)
        command = run_mock.call_args.args[0]
        self.assertIn("history", command)
        self.assertIn("--all", command)
        self.assertIn("--json", command)
        self.assertNotIn("shell", run_mock.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
