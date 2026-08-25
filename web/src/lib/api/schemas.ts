import { z } from "zod"

const money = z.union([z.string(), z.number()]).transform((value) => Number(value))
const json = z.json()

export const tokenUsageSchema = z.object({
  input_tokens: z.number(),
  output_tokens: z.number(),
  cache_read_tokens: z.number(),
  cache_write_tokens: z.number(),
})

export const traceSummarySchema = z.object({
  trace_id: z.string(),
  root_name: z.string(),
  service_name: z.string(),
  session_id: z.string(),
  start_time: z.string(),
  end_time: z.string(),
  duration_ms: z.number(),
  span_count: z.number(),
  error_count: z.number(),
  root_error: z.boolean(),
  llm_calls: z.number(),
  tool_calls: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  cost_usd: money,
  services: z.array(z.string()),
  models: z.array(z.string()),
})
export type TraceSummary = z.infer<typeof traceSummarySchema>

export const tracePageSchema = z.object({
  items: z.array(traceSummarySchema),
  next_cursor: z.string().nullable(),
})
export type TracePage = z.infer<typeof tracePageSchema>

export const messagePartSchema = z.object({
  type: z.string(),
  content: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
  id: z.string().nullable().optional(),
  arguments: json.optional(),
  response: json.optional(),
})
export type MessagePart = z.infer<typeof messagePartSchema>

export const chatMessageSchema = z.object({
  role: z.string(),
  parts: z.array(messagePartSchema),
  finish_reason: z.string().nullable().optional(),
})
export type ChatMessage = z.infer<typeof chatMessageSchema>

export const rollupSchema = z.object({
  span_count: z.number(),
  llm_calls: z.number(),
  tool_calls: z.number(),
  error_count: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  cache_read_tokens: z.number(),
  cost_usd: money,
})
export type Rollup = z.infer<typeof rollupSchema>

const spanStatus = z.enum(["unset", "ok", "error"])

export interface SpanNode {
  span_id: string
  parent_span_id: string | null
  name: string
  kind: string
  service_name: string
  start_time: string
  end_time: string
  offset_ms: number
  duration_ms: number
  depth: number
  status: z.infer<typeof spanStatus>
  status_message: string
  operation: string
  provider: string
  model: string
  request_model: string
  response_model: string
  usage: z.infer<typeof tokenUsageSchema>
  cost_usd: number
  price_version: number
  tool: {
    name: string
    call_id: string
    arguments?: z.infer<typeof json> | undefined
    result?: z.infer<typeof json> | undefined
  } | null
  agent_name: string
  session_id: string
  system_instructions: string
  input_messages: ChatMessage[]
  output_messages: ChatMessage[]
  finish_reasons: string[]
  error_type: string
  attributes: Record<string, string>
  resource_attributes: Record<string, string>
  events: { name: string; timestamp: string; offset_ms: number; attributes: Record<string, unknown> }[]
  subtree: Rollup
  children: SpanNode[]
}

export const spanNodeSchema: z.ZodType<SpanNode, unknown> = z.lazy(() =>
  z.object({
    span_id: z.string(),
    parent_span_id: z.string().nullable(),
    name: z.string(),
    kind: z.string(),
    service_name: z.string(),
    start_time: z.string(),
    end_time: z.string(),
    offset_ms: z.number(),
    duration_ms: z.number(),
    depth: z.number(),
    status: spanStatus,
    status_message: z.string(),
    operation: z.string(),
    provider: z.string(),
    model: z.string(),
    request_model: z.string(),
    response_model: z.string(),
    usage: tokenUsageSchema,
    cost_usd: money,
    price_version: z.number(),
    tool: z.object({ name: z.string(), call_id: z.string(), arguments: json.optional(), result: json.optional() }).nullable(),
    agent_name: z.string(),
    session_id: z.string(),
    system_instructions: z.string(),
    input_messages: z.array(chatMessageSchema),
    output_messages: z.array(chatMessageSchema),
    finish_reasons: z.array(z.string()),
    error_type: z.string(),
    attributes: z.record(z.string(), z.string()),
    resource_attributes: z.record(z.string(), z.string()),
    events: z.array(
      z.object({
        name: z.string(),
        timestamp: z.string(),
        offset_ms: z.number(),
        attributes: z.record(z.string(), z.unknown()),
      })
    ),
    subtree: rollupSchema,
    children: z.array(spanNodeSchema),
  })
)

export const modelUsageSchema = z.object({
  model: z.string(),
  provider: z.string(),
  calls: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  cache_read_tokens: z.number(),
  cost_usd: money,
})

export const traceDetailSchema = z.object({
  trace_id: z.string(),
  root_name: z.string(),
  service_name: z.string(),
  session_id: z.string(),
  start_time: z.string(),
  end_time: z.string(),
  duration_ms: z.number(),
  services: z.array(z.string()),
  rollup: rollupSchema,
  models: z.array(modelUsageSchema),
  roots: z.array(spanNodeSchema),
})
export type TraceDetail = z.infer<typeof traceDetailSchema>

export const facetsSchema = z.object({
  services: z.array(z.string()),
  models: z.array(z.string()),
  operations: z.array(z.string()),
  tools: z.array(z.string()),
})
export type Facets = z.infer<typeof facetsSchema>

const windowStatsSchema = z.object({
  requests: z.number(),
  errors: z.number(),
  error_rate: z.number(),
  p50_ms: z.number(),
  p95_ms: z.number(),
  p99_ms: z.number(),
  llm_calls: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  cost_usd: money,
})
export type WindowStats = z.infer<typeof windowStatsSchema>

export const overviewSchema = z.object({
  window: z.object({ start: z.string(), end: z.string(), service: z.string().nullable() }),
  current: windowStatsSchema,
  previous: windowStatsSchema,
})
export type Overview = z.infer<typeof overviewSchema>

export const timeseriesSchema = z.object({
  interval_seconds: z.number(),
  points: z.array(
    z.object({
      bucket: z.string(),
      requests: z.number(),
      errors: z.number(),
      p50_ms: z.number().nullable(),
      p95_ms: z.number().nullable(),
      cost_usd: money,
      input_tokens: z.number(),
      output_tokens: z.number(),
    })
  ),
})
export type Timeseries = z.infer<typeof timeseriesSchema>

export const modelLatencySchema = z.array(
  z.object({
    model: z.string(),
    calls: z.number(),
    errors: z.number(),
    p50_ms: z.number(),
    p95_ms: z.number(),
    input_tokens: z.number(),
    output_tokens: z.number(),
    cost_usd: money,
  })
)
export type ModelLatency = z.infer<typeof modelLatencySchema>[number]

export const costDimensionSchema = z.enum(["service", "model", "session"])
export type CostDimension = z.infer<typeof costDimensionSchema>

export const costBreakdownSchema = z.object({
  group_by: costDimensionSchema,
  total_cost_usd: money,
  rows: z.array(
    z.object({
      key: z.string(),
      calls: z.number(),
      input_tokens: z.number(),
      output_tokens: z.number(),
      cost_usd: money,
      share: z.number(),
    })
  ),
})
export type CostBreakdown = z.infer<typeof costBreakdownSchema>

export const toolHeatmapSchema = z.object({
  interval_seconds: z.number(),
  buckets: z.array(z.string()),
  tools: z.array(
    z.object({
      tool_name: z.string(),
      calls: z.number(),
      failures: z.number(),
      failure_rate: z.number(),
      p95_ms: z.number(),
      cells: z.array(z.object({ calls: z.number(), failures: z.number() })),
    })
  ),
})
export type ToolHeatmap = z.infer<typeof toolHeatmapSchema>

export const scorerSpecSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("exact_match"), case_sensitive: z.boolean(), normalize_whitespace: z.boolean() }),
  z.object({ type: z.literal("json_schema"), schema: z.record(z.string(), z.unknown()) }),
  z.object({ type: z.literal("embedding_similarity"), threshold: z.number() }),
  z.object({ type: z.literal("llm_judge"), rubric: z.string(), threshold: z.number() }),
])
export type ScorerSpec = z.infer<typeof scorerSpecSchema>

export const datasetSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  version: z.number(),
  item_count: z.number(),
  default_scorers: z.array(scorerSpecSchema),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Dataset = z.infer<typeof datasetSchema>

export const datasetItemSchema = z.object({
  id: z.string(),
  item_key: z.string(),
  dataset_id: z.string(),
  revision: z.number(),
  input: json,
  expected_output: json.nullable(),
  metadata: z.record(z.string(), z.unknown()),
  source_trace_id: z.string().nullable(),
  source_span_id: z.string().nullable(),
  created_at: z.string(),
})
export type DatasetItem = z.infer<typeof datasetItemSchema>

export const datasetVersionSchema = z.object({
  dataset: datasetSchema,
  version: z.number(),
  items: z.array(datasetItemSchema),
})
export type DatasetVersion = z.infer<typeof datasetVersionSchema>

export const scoreResultSchema = z.object({
  scorer: z.string(),
  value: z.number(),
  passed: z.boolean(),
  detail: z.string().nullable(),
})

export const runSummarySchema = z.object({
  total: z.number(),
  passed: z.number(),
  failed: z.number(),
  errored: z.number(),
  pass_rate: z.number(),
  mean_scores: z.record(z.string(), z.number()),
  latency_p50_ms: z.number().nullable(),
  latency_p95_ms: z.number().nullable(),
})
export type RunSummary = z.infer<typeof runSummarySchema>

export const gatePolicySchema = z.object({
  fail_on_regression: z.boolean(),
  min_pass_rate: z.number().nullable(),
  max_pass_rate_drop: z.number().nullable(),
})

export const recordedGateSchema = z.object({
  passed: z.boolean(),
  reasons: z.array(z.string()),
  policy: gatePolicySchema,
  baseline_run_id: z.string().nullable(),
})
export type RecordedGate = z.infer<typeof recordedGateSchema>

export const evalRunSchema = z.object({
  id: z.string(),
  dataset_id: z.string(),
  dataset_name: z.string(),
  dataset_version: z.number(),
  name: z.string().nullable(),
  target_url: z.string(),
  status: z.enum(["pending", "running", "completed", "failed"]),
  scorers: z.array(scorerSpecSchema),
  git_sha: z.string().nullable(),
  git_ref: z.string().nullable(),
  is_baseline: z.boolean(),
  summary: runSummarySchema.nullable(),
  error: z.string().nullable(),
  embedder: z.string().nullable(),
  gate: recordedGateSchema.nullable(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
})
export type EvalRun = z.infer<typeof evalRunSchema>

export const caseResultSchema = z.object({
  item_key: z.string(),
  item_id: z.string(),
  input: json,
  expected_output: json.nullable(),
  output: json.nullable(),
  passed: z.boolean(),
  scores: z.array(scoreResultSchema),
  latency_ms: z.number().nullable(),
  error: z.string().nullable(),
})
export type CaseResult = z.infer<typeof caseResultSchema>

export const diffStatusSchema = z.enum(["regressed", "fixed", "unchanged_pass", "unchanged_fail", "added", "removed"])
export type DiffStatus = z.infer<typeof diffStatusSchema>

export const runDiffSchema = z.object({
  base: evalRunSchema,
  head: evalRunSchema,
  pass_rate_delta: z.number(),
  mean_score_deltas: z.record(z.string(), z.number()),
  counts: z.record(diffStatusSchema, z.number()),
  items: z.array(
    z.object({
      item_key: z.string(),
      status: diffStatusSchema,
      input: json,
      expected_output: json.nullable(),
      base_output: json.nullable(),
      head_output: json.nullable(),
      base_passed: z.boolean().nullable(),
      head_passed: z.boolean().nullable(),
      base_error: z.string().nullable(),
      head_error: z.string().nullable(),
      score_deltas: z.array(
        z.object({
          scorer: z.string(),
          base: z.number().nullable(),
          head: z.number().nullable(),
          delta: z.number().nullable(),
        })
      ),
      base_latency_ms: z.number().nullable(),
      head_latency_ms: z.number().nullable(),
    })
  ),
  warnings: z.array(z.string()),
})
export type RunDiff = z.infer<typeof runDiffSchema>
export type ItemDiff = RunDiff["items"][number]

const modelPriceSchema = z.object({
  provider: z.string(),
  model: z.string(),
  match: z.enum(["exact", "prefix"]),
  input_per_mtok: money,
  output_per_mtok: money,
  cache_read_per_mtok: money.nullable(),
  cache_write_per_mtok: money.nullable(),
})
export type ModelPrice = z.infer<typeof modelPriceSchema>

export const priceVersionSchema = z.object({
  id: z.number(),
  label: z.string(),
  effective_from: z.string(),
  created_at: z.string(),
  prices: z.array(modelPriceSchema),
})
export type PriceVersion = z.infer<typeof priceVersionSchema>

export const priceVersionSummarySchema = z.array(
  z.object({
    id: z.number(),
    label: z.string(),
    effective_from: z.string(),
    created_at: z.string(),
    model_count: z.number(),
  })
)
export type PriceVersionSummary = z.infer<typeof priceVersionSummarySchema>[number]

export const apiErrorSchema = z.object({
  error: z.object({ code: z.string(), message: z.string(), details: z.record(z.string(), z.unknown()).optional() }),
})
