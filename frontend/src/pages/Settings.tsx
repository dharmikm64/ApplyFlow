import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { previewCycleChange, useAccountActions, useSetCycle } from "../api/hooks";
import { ApiError } from "../api/client";
import type { CyclePreview, Me } from "../api/types";
import { StateBanner } from "../components/StateBanner";
import { detectTimezone, todayIn } from "../components/StartDatePicker";

function TypedConfirm({
  id,
  title,
  description,
  confirmLabel,
  onConfirm,
  onCancel,
  pending,
}: {
  id: string;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  pending: boolean;
}) {
  const [typed, setTyped] = useState("");
  return (
    <div role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} className="card" style={{ borderColor: "var(--err)" }}>
      <h3 id={`${id}-title`}>{title}</h3>
      <p>{description}</p>
      <div className="field">
        <label htmlFor={`${id}-input`}>Type DELETE to confirm</label>
        <input id={`${id}-input`} value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus />
      </div>
      <div className="row">
        <button type="button" className="button button--danger" disabled={typed !== "DELETE" || pending} onClick={onConfirm}>
          {confirmLabel}
        </button>
        <button type="button" className="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function StartDateChange({ me }: { me: Me }) {
  const [date, setDate] = useState(me.cycle.startDate ?? "");
  const tz = me.cycle.timezone ?? detectTimezone();
  const [preview, setPreview] = useState<CyclePreview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const setCycle = useSetCycle();

  return (
    <section className="card" aria-labelledby="cycle-h">
      <h2 id="cycle-h">Recruiting start date</h2>
      <p className="fineprint">
        Current: {me.cycle.startDate ?? "not set"} ({tz}). Changing it never deletes rows.
      </p>
      <form
        className="row"
        onSubmit={async (e) => {
          e.preventDefault();
          setErr(null);
          try {
            setPreview(await previewCycleChange(date));
          } catch (x) {
            setErr(x instanceof ApiError ? x.message : "Couldn't preview the change.");
          }
        }}
      >
        <div className="field">
          <label htmlFor="new-start">New start date</label>
          <input id="new-start" type="date" max={todayIn(tz)} required value={date} onChange={(e) => { setDate(e.target.value); setPreview(null); }} />
        </div>
        <div className="field">
          <button type="submit" className="button">
            Preview change
          </button>
        </div>
      </form>
      {err && <p role="alert" style={{ color: "var(--err)" }}>{err}</p>}
      {preview && (
        <div role="status" data-testid="cycle-preview">
          <p>{preview.message}</p>
          {preview.direction !== "same" && (
            <button
              type="button"
              className="button button--primary"
              disabled={setCycle.isPending}
              onClick={() => setCycle.mutate({ startDate: date, timezone: tz, confirm: true }, { onSuccess: () => setPreview(null) })}
            >
              Confirm change
            </button>
          )}
        </div>
      )}
    </section>
  );
}

export function Settings({ me }: { me: Me }) {
  const { disconnect, deleteData, deleteAccount } = useAccountActions();
  const [open, setOpen] = useState<"disconnect" | "data" | "account" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const navigate = useNavigate();
  const connected = me.gmail.status === "connected";

  return (
    <main className="page">
      <h1>Settings</h1>
      {notice && <StateBanner variant="success" title={notice} />}

      <section className="card" aria-labelledby="gmail-h">
        <h2 id="gmail-h">Gmail connection</h2>
        <p>
          Status: <strong>{connected ? "Connected (read-only)" : me.gmail.status === "not_connected" ? "Not connected" : `Not connected (${me.gmail.status})`}</strong>
          {me.gmail.address && <> · {me.gmail.address}</>}
        </p>
        {connected ? (
          open === "disconnect" ? (
            <div role="dialog" aria-modal="true" aria-labelledby="disc-title" className="card">
              <h3 id="disc-title">Disconnect Gmail?</h3>
              <p>
                ApplyFlow will stop any running scan, revoke its access at Google, and delete the
                stored credentials. Your application table is kept. You can reconnect later.
              </p>
              <div className="row">
                <button
                  type="button"
                  className="button button--danger"
                  disabled={disconnect.isPending}
                  onClick={() => disconnect.mutate(undefined, { onSuccess: () => { setOpen(null); setNotice("Gmail disconnected."); } })}
                >
                  Disconnect
                </button>
                <button type="button" className="button" onClick={() => setOpen(null)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button type="button" className="button" onClick={() => setOpen("disconnect")}>
              Disconnect Gmail
            </button>
          )
        ) : (
          <a className="button button--primary" href="/connect">
            Connect Gmail
          </a>
        )}
      </section>

      <StartDateChange me={me} />

      <section className="card" aria-labelledby="data-h">
        <h2 id="data-h">Imported data</h2>
        <p>Delete every application, event, evidence excerpt, and review item. Your Gmail connection and start date are kept.</p>
        {open === "data" ? (
          <TypedConfirm
            id="del-data"
            title="Delete imported data?"
            description="This permanently removes your whole application table. It can't be undone."
            confirmLabel="Delete imported data"
            pending={deleteData.isPending}
            onCancel={() => setOpen(null)}
            onConfirm={() => deleteData.mutate(undefined, { onSuccess: () => { setOpen(null); setNotice("Imported data deleted."); } })}
          />
        ) : (
          <button type="button" className="button button--danger" onClick={() => setOpen("data")}>
            Delete imported data
          </button>
        )}
        {deleteData.error instanceof ApiError && <p role="alert" style={{ color: "var(--err)" }}>{deleteData.error.message}</p>}
      </section>

      <section className="card" aria-labelledby="acct-h">
        <h2 id="acct-h">Delete account</h2>
        <p>Remove your ApplyFlow account and everything in it, revoke Gmail access, and sign out.</p>
        {open === "account" ? (
          <TypedConfirm
            id="del-account"
            title="Delete your ApplyFlow account?"
            description="Everything is removed: your account, Gmail connection, start date, applications, evidence, review items, and scan history. You will be signed out."
            confirmLabel="Delete account"
            pending={deleteAccount.isPending}
            onCancel={() => setOpen(null)}
            onConfirm={() => deleteAccount.mutate(undefined, { onSuccess: () => navigate("/") })}
          />
        ) : (
          <button type="button" className="button button--danger" onClick={() => setOpen("account")}>
            Delete account
          </button>
        )}
      </section>
    </main>
  );
}
