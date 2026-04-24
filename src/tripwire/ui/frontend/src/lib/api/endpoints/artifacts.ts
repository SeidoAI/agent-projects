import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

export interface ArtifactSpec {
  name: string;
  file: string;
  template: string;
  produced_at: string;
  produced_by: string;
  owned_by: string | null;
  required: boolean;
  approval_gate: boolean;
}

export interface ArtifactManifest {
  artifacts: ArtifactSpec[];
}

export interface ApprovalSidecar {
  approved: boolean;
  reviewer: string;
  reviewed_at: string;
  feedback: string | null;
}

export interface ArtifactStatus {
  spec: ArtifactSpec;
  present: boolean;
  size_bytes: number | null;
  last_modified: string | null;
  approval: ApprovalSidecar | null;
}

export interface ArtifactContent {
  name: string;
  file_path: string;
  body: string;
  mtime: string;
}

export const artifactsApi = {
  manifest: (pid: string) =>
    apiGet<ArtifactManifest>(`/api/projects/${encodeURIComponent(pid)}/artifact-manifest`),
  list: (pid: string, sid: string) =>
    apiGet<ArtifactStatus[]>(
      `/api/projects/${encodeURIComponent(pid)}/sessions/${encodeURIComponent(sid)}/artifacts`,
    ),
  get: (pid: string, sid: string, name: string) =>
    apiGet<ArtifactContent>(
      `/api/projects/${encodeURIComponent(pid)}/sessions/${encodeURIComponent(sid)}/artifacts/${encodeURIComponent(name)}`,
    ),
  approve: (pid: string, sid: string, name: string, feedback?: string) =>
    apiPost<ArtifactStatus>(
      `/api/projects/${encodeURIComponent(pid)}/sessions/${encodeURIComponent(sid)}/artifacts/${encodeURIComponent(name)}/approve`,
      { feedback: feedback ?? null },
    ),
  reject: (pid: string, sid: string, name: string, feedback: string) =>
    apiPost<ArtifactStatus>(
      `/api/projects/${encodeURIComponent(pid)}/sessions/${encodeURIComponent(sid)}/artifacts/${encodeURIComponent(name)}/reject`,
      { feedback },
    ),
};

export function useArtifactManifest(pid: string) {
  return useQuery({
    queryKey: queryKeys.artifactManifest(pid),
    queryFn: () => artifactsApi.manifest(pid),
    staleTime: staleTime.enum,
  });
}

export function useSessionArtifacts(pid: string, sid: string) {
  return useQuery({
    queryKey: queryKeys.sessionArtifacts(pid, sid),
    queryFn: () => artifactsApi.list(pid, sid),
    staleTime: staleTime.default,
  });
}

export function useArtifact(pid: string, sid: string, name: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.artifact(pid, sid, name),
    queryFn: () => artifactsApi.get(pid, sid, name),
    staleTime: staleTime.default,
    enabled,
  });
}

export function useApproveArtifact(pid: string, sid: string, name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (feedback?: string) => artifactsApi.approve(pid, sid, name, feedback),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.sessionArtifacts(pid, sid) });
      qc.invalidateQueries({ queryKey: queryKeys.artifact(pid, sid, name) });
    },
  });
}

export function useRejectArtifact(pid: string, sid: string, name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (feedback: string) => artifactsApi.reject(pid, sid, name, feedback),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.sessionArtifacts(pid, sid) });
      qc.invalidateQueries({ queryKey: queryKeys.artifact(pid, sid, name) });
    },
  });
}
