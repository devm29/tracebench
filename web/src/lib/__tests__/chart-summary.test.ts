import { describe, expect, it } from "vitest"

import type { Timeseries } from "@/lib/api/schemas"
import { latencySummary, spendSummary, trafficSummary } from "@/lib/chart-summary"

const point = (bucket: string, requests: number, p95: number | null, cost: number) => ({
  bucket,
  requests,
  errors: requests > 10 ? 2 : 0,
  p50_ms: p95 === null ? null : p95 / 2,
  p95_ms: p95,
  cost_usd: cost,
  input_tokens: 0,
  output_tokens: 0,
})

const series: Timeseries = {
  interval_seconds: 3600,
  points: [
    point("2026-10-04T10:00:00Z", 5, 800, 0.1),
    point("2026-10-04T11:00:00Z", 20, 2400, 0.5),
    point("2026-10-04T12:00:00Z", 0, null, 0),
  ],
}

describe("chart summaries", () => {
  it("describe peaks and totals", () => {
    expect(latencySummary(series)).toMatch(/^p95 latency peaked at 2\.40? ?s at /)
    expect(trafficSummary(series)).toMatch(/^25 requests and 2 errors/)
    expect(spendSummary(series)).toContain("$0.60")
  })

  it("say so when there is no data", () => {
    const empty: Timeseries = { interval_seconds: 60, points: [point("2026-10-04T10:00:00Z", 0, null, 0)] }
    expect(latencySummary(empty)).toBe("No requests in this time range.")
    expect(trafficSummary(empty)).toBe("No requests in this time range.")
    expect(spendSummary(empty)).toBe("No model spend in this time range.")
  })
})
