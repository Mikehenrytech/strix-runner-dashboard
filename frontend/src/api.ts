import type {
  Facets,
  RunDetail,
  RunFilters,
  RunsResponse,
  Summary,
} from "./types";

const API_ROOT = "/api/v1";

function appendExclusions(query: URLSearchParams, excludedIds: string[]): void {
  excludedIds.forEach((stableId) => query.append("exclude", stableId));
}

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new Error(body?.detail || `Error HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export function getSummary(excludedIds: string[], refresh = false): Promise<Summary> {
  const query = new URLSearchParams();
  appendExclusions(query, excludedIds);
  if (refresh) query.set("refresh", "true");
  const suffix = query.toString();
  return fetchJson<Summary>(`/summary${suffix ? `?${suffix}` : ""}`);
}

export function getFacets(excludedIds: string[], refresh = false): Promise<Facets> {
  const query = new URLSearchParams();
  appendExclusions(query, excludedIds);
  if (refresh) query.set("refresh", "true");
  const suffix = query.toString();
  return fetchJson<Facets>(`/facets${suffix ? `?${suffix}` : ""}`);
}

export function getRuns(
  filters: RunFilters,
  excludedIds: string[],
  signal?: AbortSignal,
): Promise<RunsResponse> {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) {
      query.set(key, String(value));
    }
  });
  appendExclusions(query, excludedIds);
  return fetchJson<RunsResponse>(`/runs?${query.toString()}`, signal);
}

export function getRunDetail(
  stableId: string,
  signal?: AbortSignal,
): Promise<RunDetail> {
  return fetchJson<RunDetail>(`/runs/${encodeURIComponent(stableId)}`, signal);
}
