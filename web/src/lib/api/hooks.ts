"use client"

import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"

import { request } from "./client"
import {
  caseResultSchema,
  costBreakdownSchema,
  type CostDimension,
  datasetItemSchema,
  datasetSchema,
  datasetVersionSchema,
  type EvalRun,
  evalRunSchema,
  facetsSchema,
  modelLatencySchema,
  overviewSchema,
  priceVersionSchema,
  priceVersionSummarySchema,
  runDiffSchema,
  type ScorerSpec,
  timeseriesSchema,
  toolHeatmapSchema,
  traceDetailSchema,
  tracePageSchema,
} from "./schemas"

export type RangeKey = "1h" | "24h" | "7d" | "30d"

export interface TraceFilters {
  range: RangeKey
  service?: string | undefined
  model?: string | undefined
  status?: "ok" | "error" | undefined
  q?: string | undefined
  session_id?: string | undefined
}

export const keys = {
  facets: ["facets"] as const,
  traces: (filters: TraceFilters) => ["traces", filters] as const,
  trace: (id: string) => ["trace", id] as const,
  metrics: (kind: string, range: RangeKey, service: string | undefined, extra?: string) =>
    ["metrics", kind, range, service ?? "", extra ?? ""] as const,
  datasets: ["datasets"] as const,
  dataset: (id: string) => ["dataset", id] as const,
  datasetItems: (id: string, version: number | undefined) => ["dataset-items", id, version ?? "latest"] as const,
  runs: (datasetId: string | undefined) => ["runs", datasetId ?? "all"] as const,
  run: (id: string) => ["run", id] as const,
  runResults: (id: string) => ["run-results", id] as const,
  diff: (base: string, head: string) => ["diff", base, head] as const,
  prices: ["prices"] as const,
  priceVersion: (id: number) => ["price-version", id] as const,
}

const STALE = 15_000
const POLL_MS = 1500
// The API fails orphaned runs on restart, but stop polling a run that looks stuck anyway.
const MAX_POLL_AGE_MS = 30 * 60_000

export function isActive(run: Pick<EvalRun, "status" | "created_at">, now = Date.now()): boolean {
  return (run.status === "pending" || run.status === "running") && now - Date.parse(run.created_at) < MAX_POLL_AGE_MS
}

export function useFacets() {
  return useQuery({
    queryKey: keys.facets,
    queryFn: ({ signal }) => request("/api/traces/facets", facetsSchema, { signal }),
    staleTime: 60_000,
  })
}

export function useTraces(filters: TraceFilters) {
  return useInfiniteQuery({
    queryKey: keys.traces(filters),
    queryFn: ({ pageParam, signal }) =>
      request("/api/traces", tracePageSchema, { query: { ...filters, limit: 50, cursor: pageParam }, signal }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  })
}

export function useTrace(traceId: string) {
  return useQuery({
    queryKey: keys.trace(traceId),
    queryFn: ({ signal }) => request(`/api/traces/${traceId}`, traceDetailSchema, { signal }),
    staleTime: 60_000,
  })
}

export function useOverview(range: RangeKey, service?: string) {
  return useQuery({
    queryKey: keys.metrics("overview", range, service),
    queryFn: ({ signal }) => request("/api/metrics/overview", overviewSchema, { query: { range, service }, signal }),
    placeholderData: keepPreviousData,
    staleTime: STALE,
  })
}

export function useTimeseries(range: RangeKey, service?: string) {
  return useQuery({
    queryKey: keys.metrics("timeseries", range, service),
    queryFn: ({ signal }) => request("/api/metrics/timeseries", timeseriesSchema, { query: { range, service }, signal }),
    placeholderData: keepPreviousData,
    staleTime: STALE,
  })
}

export function useModelLatency(range: RangeKey, service?: string) {
  return useQuery({
    queryKey: keys.metrics("models", range, service),
    queryFn: ({ signal }) => request("/api/metrics/models", modelLatencySchema, { query: { range, service }, signal }),
    placeholderData: keepPreviousData,
    staleTime: STALE,
  })
}

export function useCostBreakdown(range: RangeKey, groupBy: CostDimension, service?: string, limit = 10) {
  return useQuery({
    queryKey: keys.metrics("cost", range, service, `${groupBy}:${limit}`),
    queryFn: ({ signal }) =>
      request("/api/metrics/cost", costBreakdownSchema, {
        query: { range, service, group_by: groupBy, limit },
        signal,
      }),
    placeholderData: keepPreviousData,
    staleTime: STALE,
  })
}

export function useToolHeatmap(range: RangeKey, service?: string) {
  return useQuery({
    queryKey: keys.metrics("tools", range, service),
    queryFn: ({ signal }) => request("/api/metrics/tools", toolHeatmapSchema, { query: { range, service }, signal }),
    placeholderData: keepPreviousData,
    staleTime: STALE,
  })
}

export function useDatasets() {
  return useQuery({
    queryKey: keys.datasets,
    queryFn: ({ signal }) => request("/api/datasets", z.array(datasetSchema), { signal }),
    staleTime: STALE,
  })
}

export function useDatasetItems(datasetId: string, version?: number) {
  return useQuery({
    queryKey: keys.datasetItems(datasetId, version),
    queryFn: ({ signal }) => request(`/api/datasets/${datasetId}/items`, datasetVersionSchema, { query: { version }, signal }),
    placeholderData: keepPreviousData,
  })
}

export function useRuns(datasetId?: string, options?: { poll?: boolean }) {
  return useQuery({
    queryKey: keys.runs(datasetId),
    queryFn: ({ signal }) => request("/api/eval-runs", z.array(evalRunSchema), { query: { dataset_id: datasetId, limit: 100 }, signal }),
    refetchInterval: (query) => (options?.poll && query.state.data?.some((r) => isActive(r)) ? POLL_MS : false),
    staleTime: STALE,
  })
}

export function useRun(runId: string) {
  return useQuery({
    queryKey: keys.run(runId),
    queryFn: ({ signal }) => request(`/api/eval-runs/${runId}`, evalRunSchema, { signal }),
    refetchInterval: (query) => (query.state.data && isActive(query.state.data) ? POLL_MS : false),
  })
}

export function useRunResults(runId: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.runResults(runId),
    queryFn: ({ signal }) => request(`/api/eval-runs/${runId}/results`, z.array(caseResultSchema), { signal }),
    enabled,
  })
}

export function useRunDiff(base: string | undefined, head: string | undefined) {
  return useQuery({
    queryKey: keys.diff(base ?? "", head ?? ""),
    queryFn: ({ signal }) => request("/api/eval-runs/compare", runDiffSchema, { query: { base, head }, signal }),
    enabled: Boolean(base && head && base !== head),
  })
}

export function usePriceVersions() {
  return useQuery({
    queryKey: keys.prices,
    queryFn: ({ signal }) => request("/api/prices/versions", priceVersionSummarySchema, { signal }),
  })
}

export function usePriceVersion(id: number | undefined) {
  return useQuery({
    queryKey: keys.priceVersion(id ?? 0),
    queryFn: ({ signal }) => request(`/api/prices/versions/${id}`, priceVersionSchema, { signal }),
    enabled: id !== undefined,
  })
}

export function usePromoteTrace(traceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: { dataset_name: string; span_id?: string | undefined }) =>
      request(`/api/traces/${traceId}/promote`, datasetItemSchema, { method: "POST", body: payload }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.datasets })
      void client.invalidateQueries({ queryKey: ["dataset-items"] })
    },
  })
}

export function useCreateDataset() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: { name: string; description: string; default_scorers: ScorerSpec[] }) =>
      request("/api/datasets", datasetSchema, { method: "POST", body: payload }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.datasets }),
  })
}

export function useUpdateItem(datasetId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ itemKey, expected }: { itemKey: string; expected: unknown }) =>
      request(`/api/datasets/${datasetId}/items/${itemKey}`, datasetItemSchema, {
        method: "PATCH",
        body: { expected_output: expected },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["dataset-items", datasetId] })
      void client.invalidateQueries({ queryKey: keys.datasets })
    },
  })
}

export function useDeleteItem(datasetId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (itemKey: string) => request(`/api/datasets/${datasetId}/items/${itemKey}`, z.undefined(), { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["dataset-items", datasetId] })
      void client.invalidateQueries({ queryKey: keys.datasets })
    },
  })
}

export function useExecuteRun() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: { dataset_id: string; target_url: string; name?: string | undefined }) =>
      request("/api/eval-runs/execute", evalRunSchema, { method: "POST", body: payload }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["runs"] }),
  })
}

export function useSetBaseline() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => request(`/api/eval-runs/${runId}/baseline`, evalRunSchema, { method: "POST" }),
    onSuccess: (run) => {
      void client.invalidateQueries({ queryKey: ["runs"] })
      void client.invalidateQueries({ queryKey: keys.run(run.id) })
    },
  })
}
