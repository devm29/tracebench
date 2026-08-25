"use client"

import { Activity } from "lucide-react"
import Link from "next/link"

import { PageTitle, Toolbar } from "@/components/page-header"
import { CostBreakdownList } from "@/components/overview/cost-breakdown"
import { LatencyChart, SpendChart, TrafficChart } from "@/components/overview/charts"
import { RANGE_LABEL, RANGES, RangeControl, ServiceSelect } from "@/components/overview/filters"
import { ModelTable } from "@/components/overview/model-table"
import { ToolHeatmap } from "@/components/overview/tool-heatmap"
import { StatTile } from "@/components/stat-tile"
import { EmptyState, ErrorState } from "@/components/states"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useUrlState } from "@/hooks/use-url-state"
import { useModelLatency, useOverview, useTimeseries, useToolHeatmap, type RangeKey } from "@/lib/api/hooks"
import { delta, formatCost, formatDuration, formatNumber, formatPercent, formatTokens } from "@/lib/format"

function ChartSkeleton({ height = "h-64" }: { height?: string }) {
  return <Skeleton className={`mx-5 ${height}`} />
}

export function OverviewView() {
  const [range, setRange] = useUrlState<RangeKey>("range", "7d", RANGES)
  const [serviceParam, setService] = useUrlState<string>("service", "")
  const service = serviceParam || undefined

  const overview = useOverview(range, service)
  const series = useTimeseries(range, service)
  const models = useModelLatency(range, service)
  const tools = useToolHeatmap(range, service)

  const current = overview.data?.current
  const previous = overview.data?.previous
  // Percent changes against a nearly empty previous window are noise, not signal.
  const comparable = Boolean(previous && current && previous.requests >= Math.max(20, current.requests * 0.1))
  const change = (now: number, before: number) => (comparable ? delta(now, before) : null)
  const empty = overview.isSuccess && current?.requests === 0 && previous?.requests === 0

  return (
    <>
      <Toolbar title="Overview">
        <ServiceSelect value={service} onChange={(next) => setService(next)} />
        <RangeControl value={range} onChange={setRange} />
      </Toolbar>
      <main className="mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
        <PageTitle title="Overview" subtitle={`${RANGE_LABEL[range]} · ${service ?? "all services"}`} />

        {overview.isError ? (
          <Card>
            <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />
          </Card>
        ) : empty ? (
          <Card>
            <EmptyState
              icon={Activity}
              title="No traces in this range"
              description="Point any OpenTelemetry exporter at /v1/traces, or run `make seed` to load a week of demo traffic."
              action={
                <Button asChild>
                  <Link href="/traces">Open traces</Link>
                </Button>
              }
            />
          </Card>
        ) : (
          <>
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5" aria-label="Key metrics">
              <StatTile
                label="Requests"
                loading={!current}
                value={current ? formatNumber(current.requests) : null}
                change={current && previous ? change(current.requests, previous.requests) : null}
                hint={current ? `${formatNumber(current.llm_calls)} model calls` : undefined}
              />
              <StatTile
                label="p95 latency"
                loading={!current}
                value={current ? formatDuration(current.p95_ms) : null}
                change={current && previous ? change(current.p95_ms, previous.p95_ms) : null}
                goodWhen="down"
                hint={current ? `p50 ${formatDuration(current.p50_ms)}` : undefined}
              />
              <StatTile
                label="Error rate"
                loading={!current}
                value={current ? formatPercent(current.error_rate) : null}
                change={current && previous ? change(current.error_rate, previous.error_rate) : null}
                goodWhen="down"
                hint={current ? `${formatNumber(current.errors)} failed` : undefined}
              />
              <StatTile
                label="Spend"
                loading={!current}
                value={current ? formatCost(current.cost_usd) : null}
                change={current && previous ? change(current.cost_usd, previous.cost_usd) : null}
                goodWhen="down"
                hint={current?.requests ? `${formatCost(current.cost_usd / current.requests)}/request` : undefined}
              />
              <StatTile
                label="Tokens"
                loading={!current}
                value={current ? formatTokens(current.input_tokens + current.output_tokens) : null}
                change={
                  current && previous
                    ? change(current.input_tokens + current.output_tokens, previous.input_tokens + previous.output_tokens)
                    : null
                }
                goodWhen="down"
                hint={current ? `${formatTokens(current.output_tokens)} output` : undefined}
              />
            </section>

            <section className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Latency</CardTitle>
                  <CardDescription>End-to-end request duration, root spans only</CardDescription>
                </CardHeader>
                <CardContent className="px-1">
                  {series.data ? <LatencyChart data={series.data} /> : <ChartSkeleton />}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Traffic</CardTitle>
                  <CardDescription>Requests and failed requests per interval</CardDescription>
                </CardHeader>
                <CardContent className="px-1">
                  {series.data ? <TrafficChart data={series.data} /> : <ChartSkeleton />}
                </CardContent>
              </Card>
            </section>

            <section className="grid items-start gap-4 lg:grid-cols-3">
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle>Spend over time</CardTitle>
                  <CardDescription>Priced from the model price table in effect when each span started</CardDescription>
                </CardHeader>
                <CardContent className="px-1">
                  {series.data ? <SpendChart data={series.data} /> : <ChartSkeleton height="h-56" />}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Where the money goes</CardTitle>
                </CardHeader>
                <CostBreakdownList range={range} service={service} />
              </Card>
            </section>

            <Card className="gap-4">
              <CardHeader>
                <CardTitle>Tool health</CardTitle>
                <CardDescription>Share of tool calls that failed, by tool and time</CardDescription>
              </CardHeader>
              {tools.data ? <ToolHeatmap data={tools.data} /> : <ChartSkeleton height="h-32" />}
            </Card>

            <Card className="gap-2 pb-2">
              <CardHeader>
                <CardTitle>Models</CardTitle>
                <CardDescription>LLM call latency, reliability and spend by model</CardDescription>
              </CardHeader>
              {models.data ? <ModelTable rows={models.data} /> : <ChartSkeleton height="h-40" />}
            </Card>
          </>
        )}
      </main>
    </>
  )
}
