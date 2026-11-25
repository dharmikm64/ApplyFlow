import type { ScanRun } from "../api/types";

export function ScanProgress({ run }: { run: ScanRun }) {
  const { listed, estimatedTotal, screened, candidates, processed } = run.progress;
  const total = estimatedTotal ?? 0;
  const pct = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : null;
  const label = run.kind === "initial" ? "Scanning your emails…" : "Syncing new emails…";
  return (
    <section className="card" aria-live="polite" aria-busy="true" data-testid="scan-progress">
      <strong>{run.status === "queued" ? "Starting scan…" : label}</strong>
      <div
        className="progress"
        role="progressbar"
        aria-label="Scan progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
      >
        <div className="progress__bar" style={{ width: `${pct ?? 5}%` }} />
      </div>
      <p className="fineprint">
        Examined {screened.toLocaleString()} of {total > 0 ? `~${total.toLocaleString()}` : listed.toLocaleString()}{" "}
        emails · {candidates.toLocaleString()} looked recruiting-related · {processed.toLocaleString()} processed.
        You can leave this page; the scan keeps running.
      </p>
    </section>
  );
}
