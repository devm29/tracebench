import type { Timeseries } from "@/lib/api/schemas"
import { formatCost, formatDateTime, formatDuration, formatNumber } from "@/lib/format"

type Point = Timeseries["points"][number]

function peak(points: Point[], value: (p: Point) => number | null): { point: Point; value: number } | undefined {
  let best: { point: Point; value: number } | undefined
  for (const point of points) {
    const v = value(point)
    if (v !== null && (best === undefined || v > best.value)) best = { point, value: v }
  }
  return best
}

// Text alternatives for the overview charts; screen readers get the gist a sighted user reads off the plot.

export function latencySummary(data: Timeseries): string {
  const p95 = peak(data.points, (p) => p.p95_ms)
  const p50 = peak(data.points, (p) => p.p50_ms)
  if (!p95 || !p50) return "No requests in this time range."
  return `p95 latency peaked at ${formatDuration(p95.value)} at ${formatDateTime(p95.point.bucket)}; the highest p50 was ${formatDuration(p50.value)}.`
}

export function trafficSummary(data: Timeseries): string {
  const requests = data.points.reduce((sum, p) => sum + p.requests, 0)
  const errors = data.points.reduce((sum, p) => sum + p.errors, 0)
  const busiest = peak(data.points, (p) => p.requests)
  if (!busiest || requests === 0) return "No requests in this time range."
  return `${formatNumber(requests)} requests and ${formatNumber(errors)} errors in total; the busiest interval started ${formatDateTime(busiest.point.bucket)} with ${formatNumber(busiest.value)} requests.`
}

export function spendSummary(data: Timeseries): string {
  const total = data.points.reduce((sum, p) => sum + p.cost_usd, 0)
  const top = peak(data.points, (p) => p.cost_usd)
  if (!top || total === 0) return "No model spend in this time range."
  return `${formatCost(total)} spent in total; the most expensive interval started ${formatDateTime(top.point.bucket)} at ${formatCost(top.value)}.`
}
