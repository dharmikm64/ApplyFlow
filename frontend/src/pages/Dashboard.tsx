import { useCallback, useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { isActive, keys, useApplications, useCurrentScan, useStartScan } from "../api/hooks";
import { ApiError } from "../api/client";
import type { AppStatus, FailureCode, Me } from "../api/types";
import { ALL_STATUSES } from "../api/types";
import { ApplicationDetailDrawer } from "../components/ApplicationDetailDrawer";
import { ApplicationsTable } from "../components/ApplicationsTable";
import { Filters } from "../components/Filters";
import { ScanProgress } from "../components/ScanProgress";
import { StartDatePicker } from "../components/StartDatePicker";
import { StateBanner } from "../components/StateBanner";

const FAILURES: Record<FailureCode, string> = {
  reconnect_required: "Gmail access was revoked or expired.",
  gmail_disconnected: "The scan stopped because Gmail was disconnected.",
  gmail_unavailable: "Gmail couldn't be reached. Rows saved so far are kept.",
  internal_error: "Something went wrong during the scan. Rows saved so far are kept.",
};

const GMAIL_NOTICES: Record<string, { variant: "success" | "error"; title: string; text: string }> = {
  connected: { variant: "success", title: "Gmail connected", text: "Read-only access granted." },
  mailbox_mismatch: {
    variant: "error",
    title: "Different Gmail account",
    text: "Your imported data came from another Gmail account. Delete imported data in Settings before connecting a different account.",
  },
  error: { variant: "error", title: "Couldn't connect Gmail", text: "Please try again." },
};

export function relativeTime(iso: string, now = Date.now()): string {
  const diff = Math.round((now - new Date(iso).getTime()) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return `${Math.floor(diff / 86400)} d ago`;
}

function ReconnectBanner({ status }: { status: "revoked" | "denied" }) {
  return (
    <StateBanner
      variant="reconnect"
      title={status === "denied" ? "Gmail access was not granted" : "Reconnect Gmail to keep syncing"}
      action={
        <Link className="button button--primary" to="/connect">
          {status === "denied" ? "Try again" : "Reconnect Gmail"}
        </Link>
      }
    >
      {status === "denied"
        ? "ApplyFlow can't scan without read-only Gmail access. Your existing rows are safe."
        : "Google limits apps in testing to 7 days of access, or access was removed from your Google account. Reconnect to continue. Your rows are kept."}
    </StateBanner>
  );
}

export function Dashboard({ me }: { me: Me }) {
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const q = params.get("q") ?? "";
  const statuses = params.getAll("status").filter((s): s is AppStatus => (ALL_STATUSES as string[]).includes(s));
  const order = params.get("order") === "asc" ? "asc" : "desc";
  const view = params.get("view") === "dismissed" ? "dismissed" : "active";
  const openId = params.get("app");
  const gmailNotice = params.get("gmail");

  const update = useCallback(
    (patch: Record<string, string | string[] | null>) => {
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(patch)) {
          next.delete(k);
          if (Array.isArray(v)) v.forEach((x) => next.append(k, x));
          else if (v) next.set(k, v);
        }
        return next;
      });
    },
    [setParams],
  );

  const connected = me.gmail.status === "connected";
  const ready = connected && !!me.cycle.startDate;
  const scan = useCurrentScan(!!me.cycle.startDate);
  const run = scan.data ?? null;
  const active = isActive(run);
  const apps = useApplications({ q, statuses, order, view }, !!me.cycle.startDate);
  const start = useStartScan();

  // When a run finishes, refresh the table, review count, and last-sync time.
  const wasActive = useRef(active);
  useEffect(() => {
    if (wasActive.current && !active) {
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: keys.review });
      qc.invalidateQueries({ queryKey: keys.me });
    }
    wasActive.current = active;
  }, [active, qc]);

  const filtering = q !== "" || statuses.length > 0;
  const neverScanned = !me.cycle.lastSuccessfulSyncAt;
  const items = apps.data?.items ?? [];
  const startError = start.error instanceof ApiError ? start.error.message : null;
  const notice = gmailNotice ? GMAIL_NOTICES[gmailNotice] : undefined;

  return (
    <main className="page">
      <h1>Applications</h1>

      {notice && (
        <StateBanner variant={notice.variant} title={notice.title}>
          {notice.text}
        </StateBanner>
      )}
      {(me.gmail.status === "revoked" || me.gmail.status === "denied" || gmailNotice === "denied") && (
        <ReconnectBanner status={me.gmail.status === "revoked" ? "revoked" : "denied"} />
      )}

      {me.gmail.status === "not_connected" && (
        <section className="card" aria-labelledby="step-connect">
          <h2 id="step-connect">Step 1: Connect Gmail</h2>
          <p>ApplyFlow needs read-only access to find application confirmations, progress updates, and rejections.</p>
          <Link className="button button--primary" to="/connect">
            Connect Gmail (read-only)
          </Link>
        </section>
      )}

      {!me.cycle.startDate && (
        <section className="card" aria-labelledby="step-date">
          <h2 id="step-date">{me.gmail.status === "not_connected" ? "Step 2" : "Step 1"}: Choose your recruiting start date</h2>
          <StartDatePicker />
        </section>
      )}

      {me.cycle.startDate && (
        <section className="row" style={{ justifyContent: "space-between", marginBottom: "0.75rem" }}>
          <div className="fineprint" data-testid="last-sync">
            {me.cycle.lastSuccessfulSyncAt
              ? `Last synced ${relativeTime(me.cycle.lastSuccessfulSyncAt)} (${new Date(me.cycle.lastSuccessfulSyncAt).toLocaleString()})`
              : "Not scanned yet"}
            {" · "}Cycle starts {me.cycle.startDate} ({me.cycle.timezone})
          </div>
          <button
            type="button"
            className="button button--primary"
            disabled={!ready || active || start.isPending}
            onClick={() => start.mutate(neverScanned ? "initial" : "sync")}
          >
            {neverScanned ? "Scan emails" : "Sync now"}
          </button>
        </section>
      )}
      {startError && <StateBanner variant="error" title={startError} />}

      {run && active && <ScanProgress run={run} />}
      {run && run.status === "failed" && run.failureCode && run.failureCode !== "reconnect_required" && (
        <StateBanner
          variant="error"
          title="The last scan didn't finish"
          action={
            ready ? (
              <button type="button" className="button" onClick={() => start.mutate(me.cycle.lastSuccessfulSyncAt ? "sync" : "initial")}>
                Retry
              </button>
            ) : undefined
          }
        >
          {FAILURES[run.failureCode]}
        </StateBanner>
      )}

      {me.cycle.startDate && (
        <>
          <p className="disclaimer">
            Only applications with available, recognizable email evidence can be imported, so this
            table may not include every application you've made.
          </p>
          <div className="tabs" role="group" aria-label="Which applications to show">
            <button type="button" className="button" aria-pressed={view === "active"} onClick={() => update({ view: null })}>
              Applications
            </button>
            <button type="button" className="button" aria-pressed={view === "dismissed"} onClick={() => update({ view: "dismissed" })}>
              Dismissed
            </button>
          </div>
          {view === "active" && (
            <Filters
              q={q}
              statuses={statuses}
              onChange={(n) => update({ ...(n.q !== undefined ? { q: n.q } : {}), ...(n.statuses ? { status: n.statuses } : {}) })}
              onClear={() => update({ q: null, status: null })}
            />
          )}

          {apps.isLoading && <StateBanner variant="loading" title="Loading applications…" />}
          {apps.isError && <StateBanner variant="error" title="Couldn't load applications." />}
          {apps.data && items.length === 0 && (
            filtering ? (
              <StateBanner
                variant="empty"
                title="No matching applications"
                action={
                  <button type="button" className="button" onClick={() => update({ q: null, status: null })}>
                    Clear filters
                  </button>
                }
              />
            ) : view === "dismissed" ? (
              <StateBanner variant="empty" title="No dismissed rows" />
            ) : neverScanned ? (
              <StateBanner variant="empty" title="No applications yet">
                {ready ? "Click “Scan emails” to build your table from your recruiting emails." : "Connect Gmail and choose a start date to begin."}
              </StateBanner>
            ) : !active ? (
              <StateBanner variant="empty" title="No applications found">
                The scan didn't find recognizable application emails in this period. Only
                applications with recognizable email evidence can be imported.
              </StateBanner>
            ) : null
          )}
          {items.length > 0 && (
            <ApplicationsTable
              items={items}
              order={order}
              caption={view === "dismissed" ? "Rows you marked as not an application" : `${items.length} application${items.length === 1 ? "" : "s"}`}
              onToggleSort={() => update({ order: order === "asc" ? null : "asc" })}
              onOpen={(id) => update({ app: id })}
            />
          )}
        </>
      )}

      {openId && <ApplicationDetailDrawer id={openId} onClose={() => update({ app: null })} />}
    </main>
  );
}
