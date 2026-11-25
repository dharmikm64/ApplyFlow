import { useMemo, useState } from "react";
import { useSetCycle } from "../api/hooks";
import { ApiError } from "../api/client";

export function detectTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function todayIn(tz: string): string {
  // en-CA formats as YYYY-MM-DD
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(new Date());
}

function allTimezones(current: string): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (k: string) => string[] };
  const list = intl.supportedValuesOf ? intl.supportedValuesOf("timeZone") : [];
  return list.includes(current) ? list : [current, ...list];
}

interface Props {
  initialDate?: string | null;
  initialTimezone?: string | null;
  onSaved?: () => void;
}

/** First-time start-date selection (FR-006). Changing it later happens in Settings. */
export function StartDatePicker({ initialDate, initialTimezone, onSaved }: Props) {
  const [tz, setTz] = useState(initialTimezone || detectTimezone());
  const [date, setDate] = useState(initialDate || "");
  const setCycle = useSetCycle();
  const zones = useMemo(() => allTimezones(tz), [tz]);
  const error = setCycle.error instanceof ApiError ? setCycle.error.message : null;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (date) setCycle.mutate({ startDate: date, timezone: tz }, { onSuccess: () => onSaved?.() });
      }}
    >
      <div className="row">
        <div className="field">
          <label htmlFor="start-date">
            Recruiting cycle start date
            <span className="hint"> Included from 00:00 on this day.</span>
          </label>
          <input
            id="start-date"
            type="date"
            required
            max={todayIn(tz)}
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="timezone">Time zone</label>
          <select id="timezone" value={tz} onChange={(e) => setTz(e.target.value)}>
            {zones.map((z) => (
              <option key={z} value={z}>
                {z}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <button type="submit" className="button button--primary" disabled={!date || setCycle.isPending}>
            Save start date
          </button>
        </div>
      </div>
      {error && (
        <p role="alert" className="fineprint" style={{ color: "var(--err)" }}>
          {error}
        </p>
      )}
    </form>
  );
}
