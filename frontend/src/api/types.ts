// Types mirroring specs/001-email-application-tracker/contracts/http-api.md

export type AppStatus = "submitted" | "in_progress" | "rejected";
export type DateSource = "stated" | "estimated" | "unknown" | "user";
export type GmailStatus = "not_connected" | "connected" | "denied" | "revoked";

export const STATUS_LABELS: Record<AppStatus, string> = {
  submitted: "Submitted",
  in_progress: "In progress",
  rejected: "Rejected",
};
export const ALL_STATUSES: AppStatus[] = ["submitted", "in_progress", "rejected"];

export interface Cycle {
  startDate: string | null;
  timezone: string | null;
  lastSuccessfulSyncAt: string | null;
}

export interface Me {
  user: { email: string; displayName: string | null };
  csrfToken: string;
  gmail: { status: GmailStatus; address: string | null };
  cycle: Cycle;
}

export type ScanStatus = "queued" | "running" | "succeeded" | "failed";
export type FailureCode =
  | "reconnect_required"
  | "gmail_disconnected"
  | "gmail_unavailable"
  | "internal_error";

export interface ScanRun {
  id: string;
  kind: "initial" | "sync";
  status: ScanStatus;
  windowStart: string;
  windowEnd: string;
  progress: {
    listed: number;
    estimatedTotal: number | null;
    screened: number;
    candidates: number;
    processed: number;
  };
  results: { createdApps: number; updatedApps: number; reviewItems: number };
  failureCode: FailureCode | null;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface ApplicationRow {
  id: string;
  company: string | null;
  position: string | null;
  dateApplied: string | null;
  dateAppliedSource: DateSource;
  status: AppStatus;
  beforeCycle: boolean;
  pendingReview: boolean;
}

export interface ApplicationList {
  items: ApplicationRow[];
  total: number;
}

export interface Evidence {
  sender: string | null;
  subject: string | null;
  date: string;
  excerpt: string | null;
}

export interface AppEvent {
  id: string;
  kind: string;
  occurredAt: string;
  evidence: Evidence | null;
  detail: Record<string, unknown> | null;
}

export interface ApplicationDetail {
  application: ApplicationRow & {
    reqId: string | null;
    overriddenFields: string[];
    dismissedAt: string | null;
  };
  dateAppliedExplanation: string;
  events: AppEvent[];
  reviewItems: { id: string; type: ReviewType; explanation: string }[];
}

export type ReviewType =
  | "possible_application"
  | "ambiguous_match"
  | "offer_or_withdrawal"
  | "contradictory_update"
  | "manual_conflict"
  | "missing_field";

export interface AppRef {
  id: string;
  company: string | null;
  position: string | null;
}

export interface ReviewItem {
  id: string;
  type: ReviewType;
  explanation: string;
  evidence: Evidence | null;
  application: AppRef | null;
  candidates: AppRef[];
  suggestion: Record<string, unknown>;
}

export interface ReviewList {
  items: ReviewItem[];
  pendingCount: number;
}

export interface CyclePreview {
  direction: "earlier" | "later" | "same";
  rowsMarkedBeforeCycle: number;
  rowsDeleted: number;
  willScanAddedPeriod: boolean;
  message: string;
}
