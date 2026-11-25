import { useState } from "react";
import { useResolveReview } from "../api/hooks";
import { ApiError } from "../api/client";
import type { ReviewItem } from "../api/types";
import { STATUS_LABELS } from "../api/types";

const TITLES: Record<ReviewItem["type"], string> = {
  possible_application: "Possible application",
  ambiguous_match: "Which application is this?",
  offer_or_withdrawal: "Offer or withdrawal",
  contradictory_update: "Contradictory update",
  manual_conflict: "New evidence conflicts with your correction",
  missing_field: "Missing detail",
};

function label(a: { company: string | null; position: string | null }) {
  return `${a.company ?? "Unknown company"} — ${a.position ?? "Unknown position"}`;
}

export function ReviewItemCard({ item }: { item: ReviewItem }) {
  const resolve = useResolveReview();
  const s = item.suggestion as { action?: string; company?: string; position?: string; status?: string; field?: string; value?: unknown };
  const [company, setCompany] = useState(s.company ?? "");
  const [position, setPosition] = useState(s.position ?? "");
  const [missingValue, setMissingValue] = useState("");
  const [target, setTarget] = useState(item.candidates[0]?.id ?? "");
  const canCreate = item.type === "possible_application" || item.type === "ambiguous_match";
  const canApply = item.type === "contradictory_update" || item.type === "manual_conflict" || item.type === "missing_field";

  const act = (body: { action: string; applicationId?: string; fields?: Record<string, string> }) =>
    resolve.mutate({ id: item.id, ...body });

  return (
    <article className="card" aria-labelledby={`ri-${item.id}`}>
      <h2 id={`ri-${item.id}`}>{TITLES[item.type]}</h2>
      <p>{item.explanation}</p>
      {item.application && <p className="fineprint">Application: {label(item.application)}</p>}
      {item.evidence && (
        <div className="evidence">
          <div className="evidence__meta">
            From {item.evidence.sender ?? "unknown sender"} · {item.evidence.subject ?? "(no subject)"} ·{" "}
            {new Date(item.evidence.date).toLocaleDateString()}
          </div>
          {item.evidence.excerpt && <div>“{item.evidence.excerpt}”</div>}
        </div>
      )}

      {canCreate && (
        <form
          className="row"
          style={{ marginTop: "0.75rem" }}
          onSubmit={(e) => {
            e.preventDefault();
            act({ action: "create", fields: { company, position } });
          }}
        >
          <div className="field">
            <label htmlFor={`c-${item.id}`}>Company</label>
            <input id={`c-${item.id}`} required value={company} onChange={(e) => setCompany(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor={`p-${item.id}`}>Position</label>
            <input id={`p-${item.id}`} value={position} onChange={(e) => setPosition(e.target.value)} />
          </div>
          <div className="field">
            <button type="submit" className="button button--primary">
              Create application{s.status ? ` (${STATUS_LABELS[s.status as keyof typeof STATUS_LABELS] ?? s.status})` : ""}
            </button>
          </div>
        </form>
      )}

      {item.candidates.length > 0 && (
        <div className="row" style={{ marginTop: "0.5rem" }}>
          <div className="field">
            <label htmlFor={`a-${item.id}`}>Attach to</label>
            <select id={`a-${item.id}`} value={target} onChange={(e) => setTarget(e.target.value)}>
              {item.candidates.map((c) => (
                <option key={c.id} value={c.id}>
                  {label(c)}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <button type="button" className="button" onClick={() => act({ action: "attach", applicationId: target })}>
              Attach email
            </button>
          </div>
        </div>
      )}

      {canApply && item.type === "missing_field" && (
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            act({ action: "apply", fields: { [s.field ?? "position"]: missingValue } });
          }}
        >
          <div className="field">
            <label htmlFor={`m-${item.id}`}>{(s.field ?? "position").replace("_", " ")}</label>
            <input id={`m-${item.id}`} required value={missingValue} onChange={(e) => setMissingValue(e.target.value)} />
          </div>
          <div className="field">
            <button type="submit" className="button button--primary">
              Save
            </button>
          </div>
        </form>
      )}
      {canApply && item.type !== "missing_field" && (
        <button type="button" className="button button--primary" onClick={() => act({ action: "apply" })}>
          Apply suggestion ({String(s.field ?? "status").replace("_", " ")} →{" "}
          {STATUS_LABELS[s.value as keyof typeof STATUS_LABELS] ?? String(s.value ?? "unknown")})
        </button>
      )}

      <div className="row" style={{ marginTop: "0.5rem" }}>
        <button type="button" className="button button--ghost" onClick={() => act({ action: "dismiss" })}>
          Dismiss
        </button>
      </div>
      {resolve.error instanceof ApiError && (
        <p role="alert" style={{ color: "var(--err)" }}>
          {resolve.error.message}
        </p>
      )}
    </article>
  );
}
