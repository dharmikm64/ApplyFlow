import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, del, get, patch, post, put, setCsrfToken } from "./client";
import type {
  AppStatus,
  ApplicationDetail,
  ApplicationList,
  CyclePreview,
  Me,
  ReviewList,
  ScanRun,
} from "./types";

export const keys = {
  me: ["me"] as const,
  scan: ["scan", "current"] as const,
  apps: (params: string) => ["applications", params] as const,
  app: (id: string) => ["application", id] as const,
  review: ["review-items"] as const,
};

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: async (): Promise<Me | null> => {
      try {
        const me = await get<Me>("/api/me");
        setCsrfToken(me.csrfToken);
        return me;
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          setCsrfToken(null);
          return null;
        }
        throw e;
      }
    },
    staleTime: 30_000,
  });
}

const ACTIVE: ScanRun["status"][] = ["queued", "running"];

export function isActive(run: ScanRun | null | undefined): boolean {
  return !!run && ACTIVE.includes(run.status);
}

export function useCurrentScan(enabled = true) {
  return useQuery({
    queryKey: keys.scan,
    enabled,
    queryFn: async () => (await get<ScanRun | undefined>("/api/scans/current")) ?? null,
    // Poll every 2 s while a run is queued or running (FR-009).
    refetchInterval: (q) => (isActive(q.state.data as ScanRun | null) ? 2000 : false),
  });
}

export function useStartScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kind: "initial" | "sync") => post<ScanRun>("/api/scans", { kind }),
    onSuccess: (run) => qc.setQueryData(keys.scan, run),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.scan }),
  });
}

export interface ListParams {
  q?: string;
  statuses?: AppStatus[];
  order?: "asc" | "desc";
  view?: "active" | "dismissed";
}

export function listQueryString(p: ListParams): string {
  const s = new URLSearchParams();
  if (p.q) s.set("q", p.q);
  for (const st of p.statuses ?? []) s.append("status", st);
  s.set("sort", "date_applied");
  s.set("order", p.order ?? "desc");
  s.set("view", p.view ?? "active");
  return s.toString();
}

export function useApplications(p: ListParams, enabled = true) {
  const qs = listQueryString(p);
  return useQuery({
    queryKey: keys.apps(qs),
    enabled,
    queryFn: () => get<ApplicationList>(`/api/applications?${qs}`),
  });
}

export function useApplication(id: string | null) {
  return useQuery({
    queryKey: keys.app(id ?? ""),
    enabled: !!id,
    queryFn: () => get<ApplicationDetail>(`/api/applications/${id}`),
  });
}

function useInvalidateTracker() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["applications"] });
    qc.invalidateQueries({ queryKey: ["application"] });
    qc.invalidateQueries({ queryKey: keys.review });
  };
}

export function useUpdateApplication(id: string) {
  const invalidate = useInvalidateTracker();
  return useMutation({
    mutationFn: (fields: Record<string, unknown>) =>
      patch<ApplicationDetail>(`/api/applications/${id}`, fields),
    onSuccess: invalidate,
  });
}

export function useDismissApplication() {
  const invalidate = useInvalidateTracker();
  return useMutation({
    mutationFn: ({ id, restore }: { id: string; restore?: boolean }) =>
      post(`/api/applications/${id}/${restore ? "restore" : "dismiss"}`),
    onSuccess: invalidate,
  });
}

export function useReviewItems(enabled = true) {
  return useQuery({
    queryKey: keys.review,
    enabled,
    queryFn: () => get<ReviewList>("/api/review-items?state=pending"),
  });
}

export function useResolveReview() {
  const invalidate = useInvalidateTracker();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; action: string; applicationId?: string; fields?: Record<string, string> }) =>
      post(`/api/review-items/${id}/resolve`, body),
    onSuccess: invalidate,
  });
}

export function useSetCycle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { startDate: string; timezone: string; confirm?: boolean }) =>
      put("/api/cycle", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.me });
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
  });
}

export function previewCycleChange(startDate: string) {
  return get<CyclePreview>(`/api/cycle/preview-change?startDate=${encodeURIComponent(startDate)}`);
}

export function useAccountActions() {
  const qc = useQueryClient();
  const refreshAll = () => qc.invalidateQueries();
  return {
    disconnect: useMutation({ mutationFn: () => del("/api/gmail"), onSuccess: refreshAll }),
    deleteData: useMutation({
      mutationFn: () => del("/api/data", { confirm: "DELETE" }),
      onSuccess: refreshAll,
    }),
    deleteAccount: useMutation({
      mutationFn: () => del("/api/account", { confirm: "DELETE" }),
      onSuccess: () => {
        setCsrfToken(null);
        qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
        qc.setQueryData(keys.me, null); // re-renders as signed out
      },
    }),
    signOut: useMutation({
      mutationFn: () => post("/auth/logout"),
      onSuccess: () => {
        setCsrfToken(null);
        qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
        qc.setQueryData(keys.me, null); // re-renders as signed out
      },
    }),
  };
}
