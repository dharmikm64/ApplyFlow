import { useEffect, useRef, useState } from "react";
import { useApplication, useDismissApplication, useUpdateApplication } from "../api/hooks";
import { ApiError } from "../api/client";
import type { AppStatus, AppEvent, ApplicationDetail } from "../api/types";
import { ALL_STATUSES, STATUS_LABELS } from "../api/types";
import { StateBanner } from "./StateBanner";

const EVENT_LABELS: Record<string, string> = {
  confirmation: "Application confirmed",
  progress: "Progress update",
  rejection: "Rejection",
  acknowledgment: "Acknowledgment",
  offer: "Offer (needs review)",
  withdrawal: "Withdrawal (needs review)",
  manual_edit: "You edited this application",
  dismissed: "Marked as not an application",
  restored: "Restored",
  review_resolved: "Review item resolved",
};

function fmt(ts: string) {
  return new Date(ts).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function EventItem({ e }: { e: AppEvent }) {
  const detail = e.detail as { field?: string; from?: unknown; to?: unknown } | null;
  return (
    <li>
      <strong>{EVENT_LABELS[e.kind] ?? e.kind}</strong>{" "}
      <span className="fineprint">{fmt(e.occurredAt)}</span>
      {detail?.field && (
        <div className="fineprint">
          {detail.field.replace("_", " ")}: {String(detail.from ?? "unknown")} → {String(detail.to ?? "unknown")}
        </div>
      )}
      {e.evidence && (
        <div className="evidence">
          <div className="evidence__meta">
            From {e.evidence.sender ?? "unknown sender"} · {e.evidence.subject ?? "(no subject)"}
          </div>
          {/* Rendered as plain text: React escapes it; raw email HTML is never rendered. */}
          {e.evidence.excerpt && <div>“{e.evidence.excerpt}”</div>}
        </div>
      )}
    </li>
  );
}

function EditForm({ detail, onSaved }: { detail: ApplicationDetail; onSaved: () => void }) {
  const a = detail.application;
  const [company, setCompany] = useState(a.company ?? "");
  const [position, setPosition] = useState(a.position ?? "");
  const [dateApplied, setDateApplied] = useState(a.dateApplied ?? "");
  const [status, setStatus] = useState<AppStatus>(a.status);
  const update = useUpdateApplication(a.id);

  const changes: Record<string, unknown> = {};
  if (company.trim() !== (a.company ?? "")) changes.company = company.trim() || null;
  if (position.trim() !== (a.position ?? "")) changes.position = position.trim() || null;
  if (dateApplied !== (a.dateApplied ?? "")) changes.dateApplied = dateApplied || null;
  if (status !== a.status) changes.status = status;
  const dirty = Object.keys(changes).length > 0;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (dirty) update.mutate(changes, { onSuccess: onSaved });
      }}
    >
      <div className="field">
        <label htmlFor="edit-company">Company</label>
        <input id="edit-company" value={company} onChange={(e) => setCompany(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="edit-position">Position</label>
        <input id="edit-position" value={position} onChange={(e) => setPosition(e.target.value)} />
      </div>
      <div className="row">
        <div className="field">
          <label htmlFor="edit-date">
            Date Applied <span className="hint">(leave empty if unknown)</span>
          </label>
          <input id="edit-date" type="date" value={dateApplied} onChange={(e) => setDateApplied(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="edit-status">Application Status</label>
          <select id="edit-status" value={status} onChange={(e) => setStatus(e.target.value as AppStatus)}>
            {ALL_STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </div>
      </div>
      {update.error instanceof ApiError && (
        <p role="alert" style={{ color: "var(--err)" }}>
          {update.error.message}
        </p>
      )}
      <button type="submit" className="button button--primary" disabled={!dirty || update.isPending}>
        Save corrections
      </button>
      {a.overriddenFields.length > 0 && (
        <p className="fineprint">
          Your corrections ({a.overriddenFields.join(", ").replace("_", " ")}) are kept across syncs.
        </p>
      )}
    </form>
  );
}

export function ApplicationDetailDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useApplication(id);
  const dismiss = useDismissApplication();
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const d = q.data;
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <h2 id="drawer-title" ref={headingRef} tabIndex={-1}>
            {d ? `${d.application.company ?? "Unknown company"} — ${d.application.position ?? "Unknown position"}` : "Application"}
          </h2>
          <button type="button" className="button button--ghost" onClick={onClose} aria-label="Close details">
            ✕
          </button>
        </header>
        {q.isLoading && <StateBanner variant="loading" title="Loading details…" />}
        {q.isError && <StateBanner variant="error" title="Couldn't load this application." />}
        {d && (
          <>
            <section className="card">
              <h3>Date Applied</h3>
              <p>{d.dateAppliedExplanation}</p>
              {d.application.reqId && <p className="fineprint">Requisition ID: {d.application.reqId}</p>}
            </section>
            {d.reviewItems.length > 0 && (
              <StateBanner variant="info" title="Needs your review">
                <ul>
                  {d.reviewItems.map((r) => (
                    <li key={r.id}>{r.explanation}</li>
                  ))}
                </ul>
                <a href="/review">Open the review area</a>
              </StateBanner>
            )}
            <section className="card">
              <h3>Correct details</h3>
              <EditForm key={JSON.stringify(d.application)} detail={d} onSaved={() => q.refetch()} />
            </section>
            <section>
              <h3>History and evidence</h3>
              <ol className="timeline">
                {d.events.map((e) => (
                  <EventItem key={e.id} e={e} />
                ))}
              </ol>
            </section>
            <section className="row" style={{ marginTop: "1rem" }}>
              {d.application.dismissedAt ? (
                <button
                  type="button"
                  className="button"
                  onClick={() => dismiss.mutate({ id, restore: true }, { onSuccess: onClose })}
                >
                  Restore to table
                </button>
              ) : (
                <button
                  type="button"
                  className="button button--danger"
                  onClick={() => dismiss.mutate({ id }, { onSuccess: onClose })}
                >
                  Not an application
                </button>
              )}
            </section>
          </>
        )}
      </aside>
    </div>
  );
}
