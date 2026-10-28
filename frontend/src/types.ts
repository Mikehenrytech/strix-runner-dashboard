export interface TimelinePoint {
  date: string;
  runs: number;
  findings: number;
  tokens: number;
}

export interface Summary {
  generated_at: string | null;
  runs: number;
  excluded_runs: number;
  profiles: number;
  findings: number;
  runs_with_unknown_findings: number;
  agents: number;
  skills: number;
  total_tokens: number;
  average_duration_seconds: number | null;
  statuses: Record<string, number>;
  utilities: Record<string, number>;
  timeline: TimelinePoint[];
}

export interface Facets {
  profiles: string[];
  statuses: string[];
  agents: string[];
  skills: string[];
  utilities: string[];
}

export interface RunListItem {
  stable_id: string;
  selection_id: number | null;
  run_id: string | null;
  run_name: string;
  profile: string;
  run_dir_relative: string | null;
  start_time: string | null;
  end_time: string | null;
  status: string;
  findings: number | null;
  severity_counts: Record<string, number>;
  duration_seconds: number | null;
  agents: number;
  skills: number;
  total_tokens: number;
  models: string[];
  report_available: boolean;
}

export interface RunsResponse {
  generated_at: string | null;
  items: RunListItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  excluded_runs: number;
}

export interface ExcludedRun {
  stable_id: string;
  profile: string;
  run_name: string;
  start_time: string | null;
  reason: string;
  excluded_at: string;
}

export interface HistorySkill {
  name: string;
  utility: string;
  reason: string | null;
  evidence: string[];
}

export interface HistoryAgent {
  agent_id: string;
  name: string;
  status: string | null;
  task: string | null;
  skills: HistorySkill[];
}

export interface RunDetail {
  stable_id: string;
  selection_id: number | null;
  run_id: string | null;
  run_name: string;
  profile_label: string;
  profile_source: string;
  profile_candidates: string[];
  run_dir_relative: string | null;
  start_time: string | null;
  end_time: string | null;
  status: string;
  scan_mode: string | null;
  duration_seconds: number | null;
  targets: string[];
  findings: number | null;
  severity_counts: Record<string, number>;
  findings_source: string;
  command_display: string;
  command_source: string;
  command_gaps: string[];
  agents: HistoryAgent[];
  llm_usage: Record<string, number>;
  models: string[];
  report_available: boolean;
  report_url: string | null;
}

export interface RunFilters {
  profile: string;
  status: string;
  agent: string;
  skill: string;
  utility: string;
  from: string;
  to: string;
  search: string;
  sort_by: string;
  order: "asc" | "desc";
  page: number;
  page_size: number;
}
