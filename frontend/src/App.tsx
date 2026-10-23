import { useCallback, useEffect, useRef, useState } from "react";
import Editor, { OnMount } from "@monaco-editor/react";
import { api } from "./api";
import type { Lang, Diagnosis, Health, Sample, HistoryRow, Bench, StratKey, Patch, CompileResult, CounterfactualCandidate, CounterfactualOut } from "./types";

const LANGS: { id: Lang; label: string }[] = [{ id: "c", label: "C" }, { id: "cpp", label: "C++" }, { id: "java", label: "Java" }, { id: "python", label: "Python" }];
const DEFAULTS: Record<Lang, string> = {
  c: '#include <stdio.h>\n\nint main(void) {\n    printf("hello\\n");\n    return 0;\n}\n',
  cpp: '#include <iostream>\n\nint main() {\n    std::cout << "hello" << std::endl;\n    return 0;\n}\n',
  java: 'public class Main {\n    public static void main(String[] args) {\n        System.out.println("hello");\n    }\n}\n',
  python: 'print("hello")\n',
};
const EXT: Record<Lang, string> = { c: ".c", cpp: ".cpp", java: ".java", python: ".py" };
const pct = (x: number) => `${(100 * x).toFixed(1)}%`;

export default function App() {
  const [tab, setTab] = useState<"ide" | "bench" | "system">("ide");
  return (
    <div className="app">
      <header><b>CompilerX<span className="x">-AI</span></b><span className="sub">root-cause localisation for syntax errors</span>
        <nav>{(["ide", "bench", "system"] as const).map(t => <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t === "ide" ? "IDE" : t === "bench" ? "Benchmark" : "System"}</button>)}</nav>
      </header>
      {tab === "ide" && <Ide />}
      {tab === "bench" && <Benchmark />}
      {tab === "system" && <System />}
    </div>
  );
}

function Ide() {
  const [lang, setLang] = useState<Lang>("c");
  const [source, setSource] = useState(DEFAULTS.c);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [term, setTerm] = useState("Ready. Choose Compile, Run or Diagnose.");
  const [diag, setDiag] = useState<Diagnosis | null>(null);
  const [busy, setBusy] = useState(false);
  const [patchMsg, setPatchMsg] = useState("");
  const [lab, setLab] = useState<Diagnosis | null>(null);
  const [labBusy, setLabBusy] = useState(false);
  const [labMsg, setLabMsg] = useState("");
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [stdin, setStdin] = useState("");
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  const monacoRef = useRef<Parameters<OnMount>[1] | null>(null);
  const decoRef = useRef<{ clear: () => void } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refreshHistory = useCallback(() => { api.history(15).then(r => setHistory(r.history)).catch(() => undefined); }, []);
  useEffect(() => { api.samples().then(r => setSamples(r.samples)).catch(e => setTerm(String(e))); api.health().then(setHealth).catch(() => undefined); refreshHistory(); }, [refreshHistory]);

  const decorate = useCallback((d: Diagnosis | null) => {
    const ed = editorRef.current, mo = monacoRef.current; if (!ed || !mo) return;
    decoRef.current?.clear();
    const decos: unknown[] = [];
    if (d?.reported) decos.push({ range: new mo.Range(d.reported.line, 1, d.reported.line, 1), options: { isWholeLine: true, className: "line-reported", glyphMarginClassName: "glyph-reported", hoverMessage: { value: `Compiler reported: ${d.reported.message}` } } });
    if (d?.root_cause_line) decos.push({ range: new mo.Range(d.root_cause_line, 1, d.root_cause_line, 1), options: { isWholeLine: true, className: "line-root", glyphMarginClassName: "glyph-root", hoverMessage: { value: "Probable root cause" } } });
    decoRef.current = ed.createDecorationsCollection(decos as never[]);
  }, []);
  useEffect(() => decorate(diag), [diag, decorate]);

  const guard = async (fn: () => Promise<void>) => { setBusy(true); try { await fn(); } catch (e) { setTerm(`Error: ${(e as Error).message}`); } finally { setBusy(false); } };
  const fmtCompile = (r: CompileResult) => `$ ${r.tool}  (${r.duration_ms} ms)\n` + (r.ok ? "Compilation OK - no errors." : r.raw_output || r.diagnostics.map(d => `${d.line}:${d.column} ${d.severity}: ${d.message}`).join("\n"));

  const onCompile = () => guard(async () => { setDiag(null); setPatchMsg(""); setLab(null); setLabMsg(""); setTerm(fmtCompile(await api.compile(lang, source))); });
  const onRun = () => guard(async () => {
    const r = await api.run(lang, source, stdin);
    setTerm(r.stage === "compile" ? `Compile failed:\n${r.stderr}` : `${r.stdout ?? ""}${r.stderr ? `\n[stderr]\n${r.stderr}` : ""}${r.timed_out ? "\n[timed out]" : ""}${r.output_truncated ? "\n[output truncated]" : ""}\n\n${r.isolation_note ?? ""}`);
  });
  const onDiagnose = () => guard(async () => {
    setPatchMsg(""); setLab(null); setLabMsg(""); const d = await api.diagnose(lang, source); setDiag(d); setTerm(fmtCompile(d.compile)); refreshHistory();
  });
  const onAccept = (p: Patch) => guard(async () => {
    const r = await api.applyPatch(lang, source, p); setSource(r.source); setPatchMsg(r.revalidation.ok ? "Patch applied - source now compiles cleanly." : "Patch applied - errors remain; run Diagnose again."); setDiag(null); setLab(null); setLabMsg("");
  });
  const onReject = () => { setPatchMsg("Patch rejected - your source was not modified."); };
  const onOpen = (f: File | undefined) => { if (!f) return; const ext = LANGS.find(l => f.name.endsWith(EXT[l.id])); if (ext) setLang(ext.id); f.text().then(t => { setSource(t); setDiag(null); setLab(null); setLabMsg(""); }); };
  const onSave = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([source], { type: "text/plain" })); a.download = `main${EXT[lang]}`; a.click(); URL.revokeObjectURL(a.href); };
  const onSample = (id: string) => { const s = samples.find(x => x.id === id); if (s) { setLang(s.language); setSource(s.source); setDiag(null); setPatchMsg(""); setLab(null); setLabMsg(""); } };

  // Counterfactual Repair Lab (Phase 2/3/5): compiles every candidate line's patches for
  // real and shows the evidence, instead of just the single best-guess patch above.
  const onOpenLab = () => { setLabBusy(true); setLabMsg(""); api.counterfactual(lang, source).then(d => { setLab(d); }).catch(e => setLabMsg(`Error: ${(e as Error).message}`)).finally(() => setLabBusy(false)); };
  const onLabAccept = (c: CounterfactualCandidate) => guard(async () => {
    if (!c.patch) return;
    const p: Patch = { template: c.patch.template, description: c.patch.description, line: c.patch.line, edits: c.patch.edits, diff: c.patch.diff, validation: null };
    const r = await api.applyPatch(lang, source, p);
    setSource(r.source); setLabMsg(r.revalidation.ok ? `Applied line ${c.line} patch - source now compiles cleanly.` : `Applied line ${c.line} patch - errors remain; run Diagnose again.`);
    setDiag(null); setLab(null);
  });
  const onLabReject = (c: CounterfactualCandidate) => { setLabMsg(`Candidate at line ${c.line} rejected - your source was not modified.`); };
  const tc = health?.toolchains[lang]; const execOn = health?.execution.enabled ?? false;

  return (
    <main className="ide">
      <section className="left">
        <div className="toolbar">
          <select value={lang} onChange={e => { const l = e.target.value as Lang; setLang(l); setSource(DEFAULTS[l]); setDiag(null); }}>{LANGS.map(l => <option key={l.id} value={l.id}>{l.label}</option>)}</select>
          <select value="" onChange={e => onSample(e.target.value)}><option value="">Sample programs...</option>{samples.map(s => <option key={s.id} value={s.id}>{s.title}</option>)}</select>
          <button onClick={() => fileRef.current?.click()}>Open</button><input ref={fileRef} type="file" hidden accept=".c,.cpp,.java,.py" onChange={e => onOpen(e.target.files?.[0])} />
          <button onClick={onSave}>Save</button>
          <button onClick={() => { setSource(DEFAULTS[lang]); setDiag(null); setPatchMsg(""); }}>Reset</button>
          <span className="grow" />
          <button disabled={busy || tc?.available === false} onClick={onCompile}>Compile</button>
          <button disabled={busy || !execOn} title={execOn ? "" : "Execution is disabled on this server (no secure sandbox)"} onClick={onRun}>Run</button>
          <button className="primary" disabled={busy || tc?.available === false} onClick={onDiagnose}>Diagnose</button>
        </div>
        <div className="editor"><Editor height="100%" theme="vs-dark" language={lang === "cpp" ? "cpp" : lang} value={source} onChange={v => setSource(v ?? "")}
          onMount={(ed, mo) => { editorRef.current = ed; monacoRef.current = mo; decorate(diag); }} options={{ glyphMargin: true, minimap: { enabled: false }, fontSize: 14, lineNumbers: "on", scrollBeyondLastLine: false }} /></div>
        {execOn && <input className="stdin" placeholder="stdin for Run" value={stdin} onChange={e => setStdin(e.target.value)} />}
        <pre className="term">{term}</pre>
      </section>
      <aside className="right">
        <h3>Diagnosis {tc && !tc.available && <span className="bad">toolchain missing: {tc.detail}</span>}</h3>
        {!diag && <p className="muted">Press <b>Diagnose</b>. Red = where the compiler stopped; amber = probable root cause.</p>}
        {diag?.status === "ok" && <p className="good">No errors found.</p>}
        {diag?.status === "non_syntax_error" && <p>{diag.note}</p>}
        {diag?.status === "syntax_error" && diag.reported && diag.strategies && <>
          <div className="card"><div className="k">Original compiler message</div><code>{diag.reported.message}</code>
            <div className="k">Reported</div>line {diag.reported.line}, col {diag.reported.column} · category <b>{diag.category}</b></div>
          <div className="card"><div className="k">Probable root cause ({diag.primary_strategy === "ml" ? "ML" : "rule-based"})</div>
            <b className="root">line {diag.root_cause_line}</b> {diag.root_cause_line !== diag.reported.line ? <span className="muted">({diag.reported.line - (diag.root_cause_line ?? 0)} line(s) before the reported line)</span> : <span className="muted">(same as reported)</span>}
            <button className="link" onClick={() => editorRef.current?.revealLineInCenter(diag.root_cause_line ?? 1)}>go to line</button></div>
          <div className="cols">{(["rule", "ml"] as const).map(s => <div className="card" key={s}><div className="k">{s === "ml" ? "ML ranking" : "Rule-based ranking"}</div>
            {diag.strategies![s].unavailable ? <span className="muted">unavailable: {diag.strategies![s].unavailable}</span> :
              <table><tbody>{diag.strategies![s].candidates!.map(c => <tr key={c.line}><td>line {c.line}</td><td className="num">{c.score.toFixed(3)}</td></tr>)}</tbody></table>}</div>)}</div>
          <p className="muted">Compiler baseline: line {diag.strategies.conventional.root_cause_line}. {diag.agreement ? "Rule and ML agree." : "Rule and ML disagree - inspect both."}</p>
          <p className="expl">{diag.explanation}</p>
          {diag.patch ? <div className="card"><div className="k">Suggested patch - {diag.patch.description}</div>
            <pre className="diff">{diag.patch.diff}</pre>
            <div className={`val ${diag.patch.validation?.status}`}>Validation on a temporary copy: <b>{diag.patch.validation?.status}</b>{diag.patch.validation?.first_error ? ` (next error: line ${diag.patch.validation.first_error.line}: ${diag.patch.validation.first_error.message})` : ""}</div>
            <button className="primary" disabled={busy} onClick={() => onAccept(diag.patch!)}>Accept patch</button> <button onClick={onReject}>Reject</button> </div>
            : <p className="muted">No validated correction found.</p>}
          {patchMsg && <p className="note">{patchMsg}</p>}
          <h3>Counterfactual Repair Lab</h3>
          <p className="muted">Compiles every nearby candidate line for real (not just the one suggestion above) and shows what actually happened - which errors it resolved, which it introduced, how big the edit was.</p>
          <button disabled={labBusy} onClick={onOpenLab}>{labBusy ? "Validating against the compiler..." : "Run Repair Lab"}</button>
          {lab?.strategies?.counterfactual && <RepairLab out={lab.strategies.counterfactual} busy={busy} onAccept={onLabAccept} onReject={onLabReject} onGoto={ln => editorRef.current?.revealLineInCenter(ln)} />}
          {labMsg && <p className="note">{labMsg}</p>}
        </>}
        <h3>History</h3>
        <table className="hist"><tbody>{history.map(h => <tr key={h.id} onClick={() => { setLang(h.language as Lang); setSource(h.source); }}><td>{h.language}</td><td>{h.status}</td><td>{h.reported_line ?? "-"}→{h.root_line ?? "-"}</td><td>{h.patch_status ?? ""}</td></tr>)}</tbody></table>
        {history.length === 0 && <p className="muted">No diagnoses yet.</p>}
      </aside>
    </main>
  );
}

function Bar({ v, cls }: { v: number; cls: string }) { return <div className="bar"><div className={cls} style={{ width: `${100 * v}%` }} /><span>{pct(v)}</span></div>; }

// Counterfactual Repair Lab panel (Phase 5): every candidate root-cause line the backend
// actually compiled, in ranked order, with real pass/fail evidence - not just the single
// best guess the "Suggested patch" card above already shows. Reuses the same accept/reject
// convention (explicit action required, nothing auto-applies) and the same /api/patch/apply
// call the suggested-patch card uses.
function CfCandidate({ c, busy, onAccept, onReject, onGoto }: { c: CounterfactualCandidate; busy: boolean; onAccept: (c: CounterfactualCandidate) => void; onReject: (c: CounterfactualCandidate) => void; onGoto: (line: number) => void }) {
  const label = c.status === "fixed" ? "compiles cleanly" : c.status === "improved" ? "original error resolved; another remains" : c.status === "not_fixed" ? "still does not compile" : "not validated";
  return (
    <div className="card">
      <div className="k">line {c.line} · heuristic score {c.score.toFixed(2)}{c.verified && <span className="good"> · verified</span>}</div>
      <button className="link" onClick={() => onGoto(c.line)}>go to line</button>
      <div className={`val ${c.status}`}>{label}</div>
      {c.evidence.map((e, i) => <p key={i} className="muted">{e}</p>)}
      {c.patch && <>
        <pre className="diff">{c.patch.diff}</pre>
        <p className="muted">edit size: {c.patch.edit_size_chars} char(s) on {c.patch.edit_size_lines} line(s) · validated in {c.patch.duration_ms} ms{c.patch.new_diagnostics.length > 0 ? ` · introduces ${c.patch.new_diagnostics.length} new diagnostic(s)` : ""}</p>
        <button className="primary" disabled={busy || c.status !== "fixed"} onClick={() => onAccept(c)}>Accept this patch</button> <button onClick={() => onReject(c)}>Reject</button>
      </>}
    </div>
  );
}

function RepairLab({ out, busy, onAccept, onReject, onGoto }: { out: CounterfactualOut; busy: boolean; onAccept: (c: CounterfactualCandidate) => void; onReject: (c: CounterfactualCandidate) => void; onGoto: (line: number) => void }) {
  return (
    <div>
      {out.ambiguous && <p className="note" style={{ color: "var(--warn)" }}>{out.note}</p>}
      <p className="muted">{out.verified_lines.length} of {out.candidates.length} candidate line(s) compiled cleanly after a patch.</p>
      {out.candidates.map(c => <CfCandidate key={c.line} c={c} busy={busy} onAccept={onAccept} onReject={onReject} onGoto={onGoto} />)}
    </div>
  );
}

function Benchmark() {
  const [b, setB] = useState<Bench | null>(null); const [msg, setMsg] = useState("Loading..."); const [running, setRunning] = useState(false);
  const load = useCallback(() => api.benchmarkResults().then(r => { setB(r.results); setMsg(r.available ? "" : "No benchmark results yet - run scripts/run_benchmark.sh or press Run."); }).catch(e => setMsg(String(e))), []);
  useEffect(() => { load(); }, [load]);
  const run = async () => { setRunning(true); try { const j = await api.benchmarkRun(10); for (;;) { await new Promise(r => setTimeout(r, 3000)); const s = await api.benchmarkStatus(j.id); if (s.state !== "running") { if (s.state === "failed") setMsg(`Benchmark failed: ${s.error}`); break; } } await load(); } catch (e) { setMsg((e as Error).message); } finally { setRunning(false); } };
  const S: StratKey[] = ["conventional", "rule", "ml"]; const cls: Record<StratKey, string> = { conventional: "c-conv", rule: "c-rule", ml: "c-ml" };
  return (
    <main className="page"><h2>Benchmark - three strategies, same held-out programs</h2>
      <button className="primary" disabled={running} onClick={run}>{running ? "Running..." : "Re-run benchmark"}</button> {msg && <span className="muted">{msg}</span>}
      {b && <>
        <p className="muted">{b.n_samples} corrupted programs from {b.programs} unseen originals ({b.split} split) · candidate recall {pct(b.candidate_recall)} · generated {b.created}</p>
        <div className="card"><div className="k">Top-1 root-cause localisation accuracy</div>
          {S.map(s => <div key={s} className="row"><span className="lbl">{s}</span><Bar v={b.overall[s].top1} cls={cls[s]} /><span className="muted">95% CI {pct(b.overall[s].top1_ci95[0])}–{pct(b.overall[s].top1_ci95[1])}</span></div>)}</div>
        <table className="t"><thead><tr><th>Strategy</th><th>Top-1</th><th>Top-3</th><th>MRR</th><th>Mean |Δ line|</th>{b.suggestion_correctness && <th>Fix works</th>}</tr></thead>
          <tbody>{S.map(s => <tr key={s}><td>{s}</td><td>{pct(b.overall[s].top1)}</td><td>{pct(b.overall[s].top3)}</td><td>{b.overall[s].mrr.toFixed(3)}</td><td>{b.overall[s].mean_abs_line_error.toFixed(2)}</td>{b.suggestion_correctness && <td>{pct(b.suggestion_correctness.overall[s].rate)}</td>}</tr>)}</tbody></table>
        <h3>Per language (top-1)</h3><table className="t"><thead><tr><th>Language</th><th>n</th>{S.map(s => <th key={s}>{s}</th>)}</tr></thead><tbody>{Object.entries(b.by_language).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v.n}</td>{S.map(s => <td key={s}>{pct(v[s].top1)}</td>)}</tr>)}</tbody></table>
        <h3>Per injected corruption (top-1)</h3><table className="t"><thead><tr><th>Corruption</th><th>n</th>{S.map(s => <th key={s}>{s}</th>)}</tr></thead><tbody>{Object.entries(b.by_corruption).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v.n}</td>{S.map(s => <td key={s}>{pct(v[s].top1)}</td>)}</tr>)}</tbody></table>
        <p className="muted">Error-type classification accuracy (compiler message → category): {pct(b.classification_accuracy.ALL.accuracy)}. Hand-written corpus (n={b.handwritten.n}, qualitative): {S.map(s => `${s} ${pct(b.handwritten.overall[s].top1)}`).join(" · ")}.</p>
        {b.counterfactual_eval && <>
          <h3>Strategy D - counterfactual evidence-enhanced ranking</h3>
          <p className="muted">Same {b.counterfactual_eval.limit_per_language}-per-language compile-validated subset as "Fix works" above (n={b.counterfactual_eval.n}) - the only strategy that actually compiles candidate patches, so it is not run on the full held-out split.</p>
          <table className="t"><thead><tr><th>Top-1</th><th>Top-3</th><th>MRR</th><th>Verified repair rate</th><th>False-correction rate</th><th>Avg. validation time</th></tr></thead>
            <tbody><tr><td>{pct(b.counterfactual_eval.top1)}</td><td>{pct(b.counterfactual_eval.top3)}</td><td>{b.counterfactual_eval.mrr.toFixed(3)}</td>
              <td>{pct(b.counterfactual_eval.verified_repair_rate)}</td><td>{pct(b.counterfactual_eval.false_correction_rate)}</td><td>{b.counterfactual_eval.avg_validation_ms.toFixed(0)} ms</td></tr></tbody></table>
          <p className="muted">False-correction rate: of the samples where some candidate patch compiled, the share whose top-ranked compiling candidate was NOT the true corruption line - a compiling patch is evidence of a valid fix, not proof of the original mistake.</p>
        </>}
      </>}
    </main>);
}

function System() {
  const [h, setH] = useState<Health | null>(null); const [m, setM] = useState<Record<string, unknown> | null>(null);
  useEffect(() => { api.health().then(setH).catch(() => undefined); api.modelStatus().then(setM).catch(() => undefined); }, []);
  return (
    <main className="page"><h2>Toolchain health</h2>
      <table className="t"><thead><tr><th>Language</th><th>Status</th><th>Tool</th><th>Version</th></tr></thead>
        <tbody>{h && Object.values(h.toolchains).map(t => <tr key={t.language}><td>{t.language}</td><td className={t.available ? "good" : "bad"}>{t.available ? "available" : "missing"}</td><td>{t.tool}</td><td>{t.version || t.detail}</td></tr>)}</tbody></table>
      {h && <p className="muted">Execution: {h.execution.enabled ? "enabled" : "disabled"} - {h.execution.isolation}. {!h.execution.enabled && h.execution.how_to_enable}</p>}
      <h2>ML model</h2><pre className="term">{m ? JSON.stringify(m, null, 2) : "loading..."}</pre></main>);
}
