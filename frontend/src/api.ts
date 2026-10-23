import type { Lang, CompileResult, Diagnosis, Health, Sample, HistoryRow, Bench, Patch } from "./types";

// Counterfactual Repair Lab request knobs: how many candidate lines / patches-per-line to
// actually compile. Kept small by default - this calls the real toolchain, unlike rule/ML ranking.

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((data as { error?: string; detail?: string }).error ?? (data as { detail?: string }).detail ?? `HTTP ${r.status}`);
  return data as T;
}

export const api = {
  health: () => req<Health>("GET", "/api/health"),
  samples: () => req<{ samples: Sample[] }>("GET", "/api/samples"),
  modelStatus: () => req<Record<string, unknown>>("GET", "/api/model/status"),
  history: (limit = 30) => req<{ history: HistoryRow[] }>("GET", `/api/history?limit=${limit}`),
  compile: (language: Lang, source: string) => req<CompileResult>("POST", "/api/compile", { language, source }),
  run: (language: Lang, source: string, stdin: string) =>
    req<{ stage: string; ok: boolean; stdout?: string; stderr?: string; timed_out?: boolean; output_truncated?: boolean; isolation_note?: string }>("POST", "/api/run", { language, source, stdin }),
  diagnose: (language: Lang, source: string) => req<Diagnosis>("POST", "/api/diagnose", { language, source }),
  counterfactual: (language: Lang, source: string, max_lines = 6, patches_per_line = 3) =>
    req<Diagnosis>("POST", "/api/counterfactual", { language, source, max_lines, patches_per_line }),
  validatePatch: (language: Lang, source: string, patch: Patch) =>
    req<{ validation: Patch["validation"]; patched_source: string }>("POST", "/api/patch/validate", { language, source, patch }),
  applyPatch: (language: Lang, source: string, patch: Patch) =>
    req<{ source: string; revalidation: { ok: boolean; errors: unknown[] } }>("POST", "/api/patch/apply", { language, source, patch, accept: true }),
  benchmarkResults: () => req<{ available: boolean; results: Bench | null }>("GET", "/api/benchmark/results"),
  benchmarkRun: (suggestion_limit = 10) => req<{ id: string; state: string }>("POST", "/api/benchmark/run", { split: "test", suggestion_limit }),
  benchmarkStatus: (job: string) => req<{ id: string; state: string; error?: string }>("GET", `/api/benchmark/status?job=${job}`),
};
