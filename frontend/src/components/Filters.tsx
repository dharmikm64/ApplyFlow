import { useEffect, useState } from "react";
import type { AppStatus } from "../api/types";
import { ALL_STATUSES, STATUS_LABELS } from "../api/types";

interface Props {
  q: string;
  statuses: AppStatus[];
  onChange: (next: { q?: string; statuses?: AppStatus[] }) => void;
  onClear: () => void;
  debounceMs?: number;
}

/** Company/position search + status filter (FR-031). State lives in the URL. */
export function Filters({ q, statuses, onChange, onClear, debounceMs = 300 }: Props) {
  const [text, setText] = useState(q);

  useEffect(() => setText(q), [q]);
  useEffect(() => {
    if (text === q) return;
    const t = setTimeout(() => onChange({ q: text }), debounceMs);
    return () => clearTimeout(t);
  }, [text, q, onChange, debounceMs]);

  const toggle = (s: AppStatus) =>
    onChange({ statuses: statuses.includes(s) ? statuses.filter((x) => x !== s) : [...statuses, s] });

  return (
    <div className="filters" role="search">
      <div className="field">
        <label htmlFor="search">Search company or position</label>
        <input
          id="search"
          type="search"
          value={text}
          placeholder="e.g. Acme or Engineer"
          onChange={(e) => setText(e.target.value)}
        />
      </div>
      <fieldset>
        <legend>Status</legend>
        {ALL_STATUSES.map((s) => (
          <label key={s} className="check">
            <input type="checkbox" checked={statuses.includes(s)} onChange={() => toggle(s)} /> {STATUS_LABELS[s]}
          </label>
        ))}
      </fieldset>
      {(q || statuses.length > 0) && (
        <button type="button" className="button button--ghost" onClick={onClear}>
          Clear filters
        </button>
      )}
    </div>
  );
}
