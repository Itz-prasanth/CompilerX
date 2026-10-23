export type Lang = "c" | "cpp" | "java" | "python";
export interface Diag { language: Lang; line: number; column: number; message: string; severity: string; category: string; expected: string | null; is_syntax: boolean; }
export interface CompileResult { ok: boolean; tool: string; diagnostics: Diag[]; raw_output: string; duration_ms: number; timed_out: boolean; toolchain_missing: boolean; }
export interface Candidate { line: number; score: number; evidence?: string[]; probability?: number; strategy?: string; }
export interface Edit { offset: number; delete: number; insert: string; }
export interface Validation { status: "fixed" | "improved" | "not_fixed" | "unvalidated"; remaining_errors: number; first_error: Diag | null; }
export interface Patch { template: string; description: string; line: number; edits: Edit[]; diff: string; validation: Validation | null; }
export interface StrategyOut { root_cause_line?: number; candidates?: Candidate[]; unavailable?: string; }
// Counterfactual Repair Lab (Phase 2/3): one real-compiler-validated patch attempt.
export interface PatchEvidence {
  line: number; template: string; description: string; diff: string;
  status: "fixed" | "improved" | "not_fixed" | "unvalidated"; compiled: boolean;
  remaining_original_error: boolean; remaining_error_count: number; edits: Edit[];
  new_diagnostics: Diag[]; resolved_diagnostics: Diag[];
  edit_size_chars: number; edit_size_lines: number; timed_out: boolean; duration_ms: number;
}
export interface CounterfactualCandidate {
  line: number; prior: number; status: PatchEvidence["status"]; verified: boolean; checked: boolean;
  composite: number; evidence: string[]; patch: PatchEvidence | null; strategy: "counterfactual"; score: number;
}
export interface CounterfactualOut {
  root_cause_line: number | null; candidates: CounterfactualCandidate[];
  ambiguous: boolean; verified_lines: number[]; note: string | null;
}
export interface Diagnosis {
  status: "ok" | "syntax_error" | "non_syntax_error" | "toolchain_missing" | "checker_failed";
  compile: CompileResult; reported?: { line: number; column: number; message: string }; category?: string;
  primary_strategy?: "rule" | "ml"; root_cause_line?: number; candidates?: Candidate[];
  strategies?: { conventional: StrategyOut; rule: StrategyOut; ml: StrategyOut; counterfactual?: CounterfactualOut };
  patch?: Patch; patch_attempts?: Patch[];
  explanation?: string; note?: string; agreement?: boolean;
}
export interface Toolchain { language: Lang; available: boolean; tool: string; version: string; detail: string; }
export interface Health { status: string; toolchains: Record<string, Toolchain>; model: { available: boolean; error: string | null }; execution: { enabled: boolean; isolation: string; how_to_enable: string }; }
export interface Sample { id: string; language: Lang; title: string; source: string; }
export interface HistoryRow { id: number; ts: string; language: string; status: string; reported_line: number | null; root_line: number | null; strategy: string | null; category: string | null; message: string | null; patch_status: string | null; source: string; }
export interface Summary { n: number; top1: number; top3: number; mrr: number; mean_abs_line_error: number; top1_ci95: [number, number]; }
export type StratKey = "conventional" | "rule" | "ml";
export interface Bench {
  created: string; split: string; n_samples: number; programs: number; candidate_recall: number;
  overall: Record<StratKey, Summary>;
  by_language: Record<string, Record<StratKey, Summary> & { n: number }>;
  by_corruption: Record<string, Record<StratKey, Summary> & { n: number }>;
  classification_accuracy: Record<string, { accuracy: number; n: number }>;
  suggestion_correctness?: { overall: Record<StratKey, { fixed: number; n: number; rate: number }>; limit_per_language: number };
  counterfactual_eval?: {
    n: number; top1: number; top3: number; mrr: number;
    verified_repair_rate: number; false_correction_rate: number; avg_validation_ms: number;
    limit_per_language: number;
  };
  handwritten: { n: number; overall: Record<StratKey, Summary> };
}
