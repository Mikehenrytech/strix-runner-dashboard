import { useEffect, useMemo, useState } from "react";
import { getFacets, getRunDetail, getRuns, getSummary } from "./api";
import type {
  ExcludedRun,
  Facets,
  RunDetail,
  RunFilters,
  RunListItem,
  RunsResponse,
  Summary,
} from "./types";

interface ExclusionCandidate {
  stable_id: string;
  profile: string;
  run_name: string;
  start_time: string | null;
}

const numberFormat = new Intl.NumberFormat("es-ES");
const dateFormat = new Intl.DateTimeFormat("es-ES", {
  dateStyle: "medium",
  timeStyle: "short",
});
const EXCLUSIONS_STORAGE_KEY = "strix-history-dashboard.exclusions.v1";

const EMPTY_FACETS: Facets = {
  profiles: [],
  statuses: [],
  agents: [],
  skills: [],
  utilities: [],
};

const DEFAULT_FILTERS: RunFilters = {
  profile: "",
  status: "",
  agent: "",
  skill: "",
  utility: "",
  from: "",
  to: "",
  search: "",
  sort_by: "start_time",
  order: "desc",
  page: 1,
  page_size: 25,
};

function loadExclusions(): ExcludedRun[] {
  try {
    const value = JSON.parse(localStorage.getItem(EXCLUSIONS_STORAGE_KEY) || "[]");
    if (!Array.isArray(value)) return [];
    return value
      .filter(
        (item): item is ExcludedRun =>
          typeof item === "object" &&
          item !== null &&
          typeof item.stable_id === "string" &&
          /^[0-9a-f]{20}$/.test(item.stable_id) &&
          typeof item.profile === "string" &&
          typeof item.run_name === "string" &&
          (item.start_time === null || typeof item.start_time === "string") &&
          typeof item.reason === "string" &&
          typeof item.excluded_at === "string",
      )
      .slice(0, 1_000);
  } catch {
    return [];
  }
}

function saveExclusions(exclusions: ExcludedRun[]): void {
  try {
    localStorage.setItem(EXCLUSIONS_STORAGE_KEY, JSON.stringify(exclusions));
  } catch {
    // The dashboard remains usable when browser storage is disabled.
  }
}

function initialFilters(): RunFilters {
  const query = new URLSearchParams(window.location.search);
  return {
    ...DEFAULT_FILTERS,
    profile: query.get("profile") || "",
    status: query.get("status") || "",
    agent: query.get("agent") || "",
    skill: query.get("skill") || "",
    utility: query.get("utility") || "",
    from: query.get("from") || "",
    to: query.get("to") || "",
    search: query.get("search") || "",
    sort_by: query.get("sort_by") || "start_time",
    order: query.get("order") === "asc" ? "asc" : "desc",
    page: Math.max(1, Number(query.get("page")) || 1),
    page_size: DEFAULT_FILTERS.page_size,
  };
}

function formatDate(value: string | null): string {
  if (!value) return "No observable";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dateFormat.format(parsed);
}

function formatDuration(value: number | null): string {
  if (value == null) return "—";
  if (value < 60) return `${Math.round(value)} s`;
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return `${minutes} min ${seconds} s`;
}

function utilityLabel(value: string): string {
  const labels: Record<string, string> = {
    high: "Alta",
    medium: "Media",
    low: "Baja",
    not_observable: "No observable",
  };
  return labels[value] || value;
}

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    completed: "Completado",
    stopped: "Detenido",
    interrupted: "Interrumpido",
    running: "En curso",
    unknown: "Desconocido",
  };
  return labels[value] || value;
}

function MetricCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{hint}</small>
    </article>
  );
}

function Distribution({
  title,
  values,
  labeler = (value) => value,
}: {
  title: string;
  values: Record<string, number>;
  labeler?: (value: string) => string;
}) {
  const entries = Object.entries(values).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, count]) => sum + count, 0) || 1;
  return (
    <section className="panel distribution-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Distribución</p>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="distribution-list">
        {entries.length === 0 && <p className="empty-copy">Sin datos observables.</p>}
        {entries.map(([name, count]) => (
          <div className="distribution-row" key={name}>
            <div>
              <span>{labeler(name)}</span>
              <strong>{numberFormat.format(count)}</strong>
            </div>
            <div className="track" aria-hidden="true">
              <span
                className={`fill fill-${name}`}
                style={{ width: `${Math.max(4, (count / total) * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Timeline({ summary }: { summary: Summary }) {
  const points = summary.timeline.slice(-18);
  const peak = Math.max(1, ...points.map((point) => point.runs));
  return (
    <section className="panel timeline-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Actividad</p>
          <h2>Ejecuciones en el tiempo</h2>
        </div>
        <span className="panel-note">Últimos {points.length} días con actividad</span>
      </div>
      <div className="timeline" role="img" aria-label="Ejecuciones por fecha">
        {points.length === 0 && <p className="empty-copy">Sin fechas observables.</p>}
        {points.map((point) => (
          <div className="timeline-column" key={point.date}>
            <span
              className="timeline-bar"
              style={{ height: `${Math.max(10, (point.runs / peak) * 100)}%` }}
              title={`${point.date}: ${point.runs} ejecuciones, ${point.findings} hallazgos`}
            />
            <small>{point.date.slice(5)}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function Filters({
  facets,
  filters,
  onChange,
  onReset,
}: {
  facets: Facets;
  filters: RunFilters;
  onChange: (key: keyof RunFilters, value: string | number) => void;
  onReset: () => void;
}) {
  const select = (
    key: "profile" | "status" | "agent" | "skill" | "utility",
    label: string,
    options: string[],
    labeler: (value: string) => string = (value) => value,
  ) => (
    <label>
      <span>{label}</span>
      <select value={filters[key]} onChange={(event) => onChange(key, event.target.value)}>
        <option value="">Todos</option>
        {options.map((option) => (
          <option value={option} key={option}>
            {labeler(option)}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <section className="filters panel" aria-label="Filtros del historial">
      <div className="search-field">
        <label htmlFor="search">Buscar</label>
        <input
          id="search"
          type="search"
          placeholder="Run, objetivo, agente o skill"
          value={filters.search}
          onChange={(event) => onChange("search", event.target.value)}
        />
      </div>
      {select("profile", "Aplicación", facets.profiles)}
      {select("status", "Estado", facets.statuses, statusLabel)}
      {select("agent", "Agente", facets.agents)}
      {select("skill", "Skill", facets.skills)}
      {select("utility", "Utilidad", facets.utilities, utilityLabel)}
      <label>
        <span>Desde</span>
        <input
          type="date"
          value={filters.from}
          onChange={(event) => onChange("from", event.target.value)}
        />
      </label>
      <label>
        <span>Hasta</span>
        <input
          type="date"
          value={filters.to}
          onChange={(event) => onChange("to", event.target.value)}
        />
      </label>
      <button className="button button-quiet reset-button" type="button" onClick={onReset}>
        Limpiar filtros
      </button>
    </section>
  );
}

function Comparison({
  runs,
  onRemove,
}: {
  runs: RunListItem[];
  onRemove: (id: string) => void;
}) {
  if (runs.length === 0) return null;
  return (
    <section className="panel comparison-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Comparación rápida</p>
          <h2>{runs.length} ejecución(es) seleccionadas</h2>
        </div>
      </div>
      <div className="comparison-grid">
        {runs.map((run) => (
          <article key={run.stable_id}>
            <button
              className="remove-comparison"
              onClick={() => onRemove(run.stable_id)}
              aria-label={`Quitar ${run.run_name} de la comparación`}
            >
              ×
            </button>
            <strong>{run.profile}</strong>
            <span>{formatDate(run.start_time)}</span>
            <dl>
              <div><dt>Hallazgos</dt><dd>{run.findings ?? "?"}</dd></div>
              <div><dt>Duración</dt><dd>{formatDuration(run.duration_seconds)}</dd></div>
              <div><dt>Tokens</dt><dd>{numberFormat.format(run.total_tokens)}</dd></div>
              <div><dt>Skills</dt><dd>{run.skills}</dd></div>
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}

function ExclusionsPanel({
  exclusions,
  onRestore,
  onRestoreAll,
}: {
  exclusions: ExcludedRun[];
  onRestore: (id: string) => void;
  onRestoreAll: () => void;
}) {
  return (
    <section className="panel exclusions-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Preferencias locales</p>
          <h2>Análisis excluidos ({exclusions.length})</h2>
        </div>
        {exclusions.length > 0 && (
          <button className="button button-quiet" type="button" onClick={onRestoreAll}>
            Restaurar todos
          </button>
        )}
      </div>
      <p className="exclusions-help">
        Se ocultan solo en este navegador. Los artefactos originales permanecen intactos.
      </p>
      {exclusions.length === 0 ? (
        <p className="empty-copy">No hay análisis excluidos.</p>
      ) : (
        <div className="exclusions-list">
          {exclusions.map((run) => (
            <article key={run.stable_id}>
              <div>
                <strong>{run.profile}</strong>
                <span>{formatDate(run.start_time)} · {run.run_name}</span>
                <small>{run.reason}</small>
              </div>
              <button
                className="button button-quiet"
                type="button"
                onClick={() => onRestore(run.stable_id)}
              >
                Restaurar
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function ExclusionDialog({
  runs,
  onCancel,
  onConfirm,
}: {
  runs: ExclusionCandidate[];
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState("Análisis de prueba");
  if (runs.length === 0) return null;
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onCancel}>
      <section
        className="confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="exclude-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <p className="eyebrow">Exclusión reversible</p>
        <h2 id="exclude-title">
          Excluir {runs.length === 1 ? "este análisis" : `${runs.length} análisis`}
        </h2>
        <p>
          Dejarán de contar en el dashboard, pero no se borrará ningún archivo de Strix.
        </p>
        <label>
          <span>Motivo</span>
          <input
            autoFocus
            maxLength={160}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <div className="modal-actions">
          <button className="button button-quiet" type="button" onClick={onCancel}>
            Cancelar
          </button>
          <button
            className="button button-danger"
            type="button"
            onClick={() => onConfirm(reason.trim() || "Sin motivo")}
          >
            Excluir del dashboard
          </button>
        </div>
      </section>
    </div>
  );
}

function RunsTable({
  data,
  loading,
  filters,
  compared,
  onFiltersChange,
  onOpen,
  onCompare,
  onExclude,
}: {
  data: RunsResponse | null;
  loading: boolean;
  filters: RunFilters;
  compared: Set<string>;
  onFiltersChange: (key: keyof RunFilters, value: string | number) => void;
  onOpen: (id: string) => void;
  onCompare: (run: RunListItem) => void;
  onExclude: (run: RunListItem) => void;
}) {
  const items = data?.items || [];
  return (
    <section className="panel runs-panel">
      <div className="panel-heading runs-heading">
        <div>
          <p className="eyebrow">Inventario</p>
          <h2>{numberFormat.format(data?.total || 0)} ejecuciones</h2>
        </div>
        <div className="sort-controls">
          <label>
            <span>Ordenar por</span>
            <select
              value={filters.sort_by}
              onChange={(event) => onFiltersChange("sort_by", event.target.value)}
            >
              <option value="start_time">Fecha</option>
              <option value="profile">Aplicación</option>
              <option value="status">Estado</option>
              <option value="findings">Hallazgos</option>
              <option value="duration_seconds">Duración</option>
              <option value="total_tokens">Tokens</option>
            </select>
          </label>
          <button
            className="button button-quiet order-button"
            onClick={() => onFiltersChange("order", filters.order === "desc" ? "asc" : "desc")}
            title="Cambiar dirección"
          >
            {filters.order === "desc" ? "↓ Desc" : "↑ Asc"}
          </button>
        </div>
      </div>
      <div className={`table-wrap ${loading ? "is-loading" : ""}`}>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Aplicación / fecha</th>
              <th>Estado</th>
              <th>Hallazgos</th>
              <th>Duración</th>
              <th>Agentes / skills</th>
              <th>Tokens</th>
              <th><span className="sr-only">Acciones</span></th>
            </tr>
          </thead>
          <tbody>
            {!loading && items.length === 0 && (
              <tr><td colSpan={8} className="empty-table">No hay ejecuciones con estos filtros.</td></tr>
            )}
            {items.map((run) => (
              <tr key={run.stable_id}>
                <td><span className="run-id">#{run.selection_id ?? "—"}</span></td>
                <td>
                  <button className="run-link" onClick={() => onOpen(run.stable_id)}>
                    <strong>{run.profile}</strong>
                    <span>{formatDate(run.start_time)}</span>
                  </button>
                </td>
                <td><span className={`status status-${run.status}`}>{statusLabel(run.status)}</span></td>
                <td>
                  <strong className={run.findings ? "finding-count" : ""}>{run.findings ?? "?"}</strong>
                  {run.report_available && <span className="report-dot" title="Informe disponible" />}
                </td>
                <td>{formatDuration(run.duration_seconds)}</td>
                <td>{run.agents} / {run.skills}</td>
                <td>{numberFormat.format(run.total_tokens)}</td>
                <td className="row-actions">
                  <button
                    className={`compare-button ${compared.has(run.stable_id) ? "active" : ""}`}
                    onClick={() => onCompare(run)}
                    aria-pressed={compared.has(run.stable_id)}
                  >
                    Comparar
                  </button>
                  <button
                    className="exclude-button"
                    onClick={() => onExclude(run)}
                    aria-label={`Excluir ${run.run_name} del dashboard`}
                    title="Excluir del dashboard"
                  >
                    Ocultar
                  </button>
                  <button className="open-button" onClick={() => onOpen(run.stable_id)} aria-label="Abrir detalle">
                    →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <span>Página {data?.page || 1} de {Math.max(1, data?.pages || 1)}</span>
        <div>
          <button
            className="button button-quiet"
            disabled={!data || data.page <= 1 || loading}
            onClick={() => onFiltersChange("page", Math.max(1, filters.page - 1))}
          >
            Anterior
          </button>
          <button
            className="button button-quiet"
            disabled={!data || data.page >= data.pages || loading}
            onClick={() => onFiltersChange("page", filters.page + 1)}
          >
            Siguiente
          </button>
        </div>
      </div>
    </section>
  );
}

function DetailDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setError("");
    setDetail(null);
    getRunDetail(id, controller.signal).then(setDetail).catch((reason: Error) => {
      if (reason.name !== "AbortError") setError(reason.message);
    });
    return () => controller.abort();
  }, [id]);

  if (!id) return null;
  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Detalle de ejecución" onMouseDown={(event) => event.stopPropagation()}>
        <button className="drawer-close" onClick={onClose} aria-label="Cerrar detalle">×</button>
        {error && <div className="error-banner">{error}</div>}
        {!detail && !error && <div className="drawer-loading">Cargando detalle…</div>}
        {detail && (
          <>
            <header className="drawer-header">
              <p className="eyebrow">Ejecución #{detail.selection_id ?? "—"}</p>
              <h2>{detail.profile_label}</h2>
              <div className="drawer-meta">
                <span className={`status status-${detail.status}`}>{statusLabel(detail.status)}</span>
                <span>{formatDate(detail.start_time)}</span>
                <span>{formatDuration(detail.duration_seconds)}</span>
              </div>
            </header>
            <div className="detail-metrics">
              <div><span>Hallazgos</span><strong>{detail.findings ?? "?"}</strong></div>
              <div><span>Agentes</span><strong>{detail.agents.length}</strong></div>
              <div><span>Skills</span><strong>{detail.agents.reduce((sum, agent) => sum + agent.skills.length, 0)}</strong></div>
              <div><span>Tokens</span><strong>{numberFormat.format(detail.llm_usage.total_tokens || 0)}</strong></div>
            </div>
            {detail.report_available && detail.report_url && (
              <a className="button button-primary report-link" href={detail.report_url} target="_blank" rel="noreferrer">
                Abrir informe de penetración ↗
              </a>
            )}
            <section className="detail-section">
              <h3>Comando <span>{detail.command_source}</span></h3>
              <pre>{detail.command_display || "No observable"}</pre>
              {detail.command_gaps.length > 0 && <p className="muted">No observable: {detail.command_gaps.join(", ")}</p>}
            </section>
            <section className="detail-section">
              <h3>Objetivos</h3>
              <ul className="target-list">
                {detail.targets.map((target) => <li key={target}>{target}</li>)}
              </ul>
            </section>
            <section className="detail-section">
              <h3>Agentes y skills</h3>
              <div className="agent-list">
                {detail.agents.length === 0 && <p className="muted">No hay agentes registrados.</p>}
                {detail.agents.map((agent) => (
                  <article className="agent-card" key={agent.agent_id || agent.name}>
                    <div className="agent-heading">
                      <strong>{agent.name}</strong>
                      {agent.status && <span>{agent.status}</span>}
                    </div>
                    {agent.task && <p>{agent.task}</p>}
                    <div className="skill-list">
                      {agent.skills.length === 0 && <span className="muted">Sin skills registradas</span>}
                      {agent.skills.map((skill) => (
                        <div className="skill-row" key={`${agent.agent_id}-${skill.name}`}>
                          <span className={`utility utility-${skill.utility}`}>{utilityLabel(skill.utility)}</span>
                          <div><strong>{skill.name}</strong>{skill.reason && <small>{skill.reason}</small>}</div>
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </>
        )}
      </aside>
    </div>
  );
}

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [facets, setFacets] = useState<Facets>(EMPTY_FACETS);
  const [runs, setRuns] = useState<RunsResponse | null>(null);
  const [filters, setFilters] = useState<RunFilters>(initialFilters);
  const [debouncedSearch, setDebouncedSearch] = useState(filters.search);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [comparison, setComparison] = useState<RunListItem[]>([]);
  const [exclusions, setExclusions] = useState<ExcludedRun[]>(() => loadExclusions());
  const [excludeCandidates, setExcludeCandidates] = useState<ExclusionCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const excludedIds = useMemo(() => exclusions.map((item) => item.stable_id), [exclusions]);

  useEffect(() => {
    saveExclusions(exclusions);
  }, [exclusions]);

  useEffect(() => {
    Promise.all([getSummary(excludedIds), getFacets(excludedIds)])
      .then(([nextSummary, nextFacets]) => {
        setSummary(nextSummary);
        setFacets(nextFacets);
      })
      .catch((reason: Error) => setError(reason.message));
  }, [excludedIds]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(filters.search), 250);
    return () => window.clearTimeout(timer);
  }, [filters.search]);

  const effectiveFilters = useMemo(
    () => ({ ...filters, search: debouncedSearch }),
    [filters, debouncedSearch],
  );

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    getRuns(effectiveFilters, excludedIds, controller.signal)
      .then((data) => {
        setRuns(data);
        setError("");
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [effectiveFilters, excludedIds]);

  useEffect(() => {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== "" && value !== 1 && value !== 25 && value !== "start_time" && value !== "desc") {
        query.set(key, String(value));
      }
    });
    const suffix = query.toString();
    window.history.replaceState(null, "", suffix ? `?${suffix}` : window.location.pathname);
  }, [filters]);

  const updateFilter = (key: keyof RunFilters, value: string | number) => {
    setFilters((current) => ({
      ...current,
      [key]: value,
      page: key === "page" ? Number(value) : 1,
    }));
  };

  const resetFilters = () => setFilters({ ...DEFAULT_FILTERS });

  const refresh = async () => {
    setRefreshing(true);
    setError("");
    try {
      const nextSummary = await getSummary(excludedIds, true);
      const [nextFacets, nextRuns] = await Promise.all([
        getFacets(excludedIds),
        getRuns(effectiveFilters, excludedIds),
      ]);
      setSummary(nextSummary);
      setFacets(nextFacets);
      setRuns(nextRuns);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo actualizar.");
    } finally {
      setRefreshing(false);
    }
  };

  const toggleComparison = (run: RunListItem) => {
    setComparison((current) => {
      if (current.some((item) => item.stable_id === run.stable_id)) {
        return current.filter((item) => item.stable_id !== run.stable_id);
      }
      return [...current.slice(-2), run];
    });
  };

  const openExcludeDialog = (run: RunListItem) => {
    setExcludeCandidates([
      {
        stable_id: run.stable_id,
        profile: run.profile,
        run_name: run.run_name,
        start_time: run.start_time,
      },
    ]);
  };

  const confirmExclude = (reason: string) => {
    const now = new Date().toISOString();
    setExclusions((current) => [
      ...current,
      ...excludeCandidates.map((candidate) => ({
        ...candidate,
        reason: reason.trim() || "Sin motivo",
        excluded_at: now,
      })),
    ]);
    setExcludeCandidates([]);
  };

  const restoreRun = (stable_id: string) => {
    setExclusions((current) => current.filter((item) => item.stable_id !== stable_id));
  };

  const restoreAllRuns = () => setExclusions([]);

  const comparedIds = new Set(comparison.map((run) => run.stable_id));

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true"><span>S</span></div>
          <div>
            <p>STRIX / HISTORY</p>
            <strong>Security Observatory</strong>
          </div>
        </div>
        <div className="topbar-actions">
          <span className="readonly-badge"><i /> Solo lectura</span>
          <button className="button button-primary" onClick={refresh} disabled={refreshing}>
            {refreshing ? "Actualizando…" : "↻ Actualizar datos"}
          </button>
        </div>
      </header>

      <main>
        <section className="hero">
          <div>
            <p className="eyebrow">Visión consolidada</p>
            <h1>Historial de análisis</h1>
            <p className="hero-copy">Ejecuciones, agentes y skills observadas en los artefactos locales de Strix.</p>
          </div>
          <div className="freshness">
            <span>Instantánea</span>
            <strong>{summary?.generated_at ? formatDate(summary.generated_at) : "Cargando…"}</strong>
          </div>
        </section>

        {error && <div className="error-banner" role="alert">{error}</div>}

        <section className="metrics-grid" aria-label="Resumen del historial">
          <MetricCard label="Ejecuciones" value={numberFormat.format(summary?.runs || 0)} hint={`${summary?.profiles || 0} aplicaciones`} />
          <MetricCard label="Hallazgos" value={numberFormat.format(summary?.findings || 0)} hint={`${summary?.runs_with_unknown_findings || 0} runs sin dato`} />
          <MetricCard label="Agentes" value={numberFormat.format(summary?.agents || 0)} hint={`${numberFormat.format(summary?.skills || 0)} skills cargadas`} />
          <MetricCard label="Tokens" value={numberFormat.format(summary?.total_tokens || 0)} hint="Consumo total observable" />
          <MetricCard label="Duración media" value={formatDuration(summary?.average_duration_seconds ?? null)} hint="Solo runs con duración" />
        </section>

        {summary && (
          <section className="analytics-grid">
            <Timeline summary={summary} />
            <Distribution title="Estados" values={summary.statuses} labeler={statusLabel} />
            <Distribution title="Utilidad de skills" values={summary.utilities} labeler={utilityLabel} />
          </section>
        )}

        <Filters facets={facets} filters={filters} onChange={updateFilter} onReset={resetFilters} />
        <Comparison runs={comparison} onRemove={(id) => setComparison((items) => items.filter((item) => item.stable_id !== id))} />
        <ExclusionsPanel
          exclusions={exclusions}
          onRestore={restoreRun}
          onRestoreAll={restoreAllRuns}
        />
        <RunsTable
          data={runs}
          loading={loading}
          filters={filters}
          compared={comparedIds}
          onFiltersChange={updateFilter}
          onOpen={setSelectedId}
          onCompare={toggleComparison}
          onExclude={openExcludeDialog}
        />
      </main>

      <footer>
        <span>Strix History Dashboard</span>
        <span>Datos locales · Sin operaciones de escritura</span>
      </footer>
      <DetailDrawer id={selectedId} onClose={() => setSelectedId(null)} />
      <ExclusionDialog
        runs={excludeCandidates}
        onCancel={() => setExcludeCandidates([])}
        onConfirm={confirmExclude}
      />
    </div>
  );
}
