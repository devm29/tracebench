"use client"

import { useId, type ComponentProps, type ReactNode } from "react"
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts"

import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import type { Timeseries } from "@/lib/api/schemas"
import { latencySummary, spendSummary, trafficSummary } from "@/lib/chart-summary"
import { formatCost, formatDuration, formatNumber } from "@/lib/format"

const AXIS = { tickLine: false, axisLine: false, tick: { fontSize: 11 }, stroke: "var(--muted-foreground)" } as const

function tickFormatter(intervalSeconds: number) {
  return (value: string) => {
    const date = new Date(value)
    return intervalSeconds >= 86_400 || (intervalSeconds >= 3600 * 3 && date.getHours() === 0)
      ? date.toLocaleDateString("en-US", { month: "short", day: "numeric" })
      : date.toLocaleTimeString("en-US", { hour: "numeric", minute: intervalSeconds < 3600 ? "2-digit" : undefined })
  }
}

function tooltipLabel(value: unknown): string {
  return typeof value === "string"
    ? new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : ""
}

function seriesLabel(config: ChartConfig, name: unknown): ReactNode {
  const key = String(name)
  return (key in config ? config[key]?.label : undefined) ?? key
}

/** A chart image plus a visually hidden sentence that carries its data for screen readers. */
function DescribedChart({
  config,
  label,
  summary,
  className,
  children,
}: {
  config: ChartConfig
  label: string
  summary: string
  className: string
  children: ComponentProps<typeof ChartContainer>["children"]
}) {
  const id = useId()
  return (
    <figure className="m-0">
      <ChartContainer config={config} className={className} role="img" aria-label={label} aria-describedby={id}>
        {children}
      </ChartContainer>
      <figcaption id={id} className="sr-only">
        {summary}
      </figcaption>
    </figure>
  )
}

const latencyConfig = {
  p50_ms: { label: "p50", color: "var(--chart-1)" },
  p95_ms: { label: "p95", color: "var(--chart-4)" },
} satisfies ChartConfig

export function LatencyChart({ data }: { data: Timeseries }) {
  return (
    <DescribedChart
      config={latencyConfig}
      className="aspect-auto h-64 w-full"
      label="Request latency p50 and p95 over time"
      summary={latencySummary(data)}
    >
      <LineChart data={data.points} margin={{ left: 4, right: 12, top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey="bucket" {...AXIS} minTickGap={32} tickFormatter={tickFormatter(data.interval_seconds)} />
        <YAxis {...AXIS} width={56} tickFormatter={(v: number) => (v === 0 ? "0" : formatDuration(v))} />
        <ChartTooltip
          cursor={{ stroke: "var(--border)" }}
          content={
            <ChartTooltipContent
              labelFormatter={(_, payload) => tooltipLabel(payload[0]?.payload?.bucket)}
              formatter={(value, name) => (
                <div className="flex w-full justify-between gap-4">
                  <span className="text-muted-foreground">{seriesLabel(latencyConfig, name)}</span>
                  <span className="font-medium tabular-nums">{formatDuration(Number(value))}</span>
                </div>
              )}
            />
          }
        />
        <ChartLegend content={<ChartLegendContent />} />
        <Line
          dataKey="p50_ms"
          type="monotone"
          stroke="var(--color-p50_ms)"
          strokeWidth={2}
          dot={false}
          connectNulls={false}
          isAnimationActive={false}
        />
        <Line
          dataKey="p95_ms"
          type="monotone"
          stroke="var(--color-p95_ms)"
          strokeWidth={2}
          dot={false}
          connectNulls={false}
          isAnimationActive={false}
        />
      </LineChart>
    </DescribedChart>
  )
}

const trafficConfig = {
  requests: { label: "Requests", color: "var(--chart-1)" },
  errors: { label: "Errors", color: "var(--destructive)" },
} satisfies ChartConfig

export function TrafficChart({ data }: { data: Timeseries }) {
  return (
    <DescribedChart
      config={trafficConfig}
      className="aspect-auto h-64 w-full"
      label="Requests and errors over time"
      summary={trafficSummary(data)}
    >
      <AreaChart data={data.points} margin={{ left: 4, right: 12, top: 8 }}>
        <defs>
          <linearGradient id="fill-requests" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-requests)" stopOpacity={0.2} />
            <stop offset="100%" stopColor="var(--color-requests)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey="bucket" {...AXIS} minTickGap={32} tickFormatter={tickFormatter(data.interval_seconds)} />
        <YAxis {...AXIS} width={40} allowDecimals={false} tickFormatter={(v: number) => formatNumber(v)} />
        <ChartTooltip
          cursor={{ stroke: "var(--border)" }}
          content={<ChartTooltipContent labelFormatter={(_, payload) => tooltipLabel(payload[0]?.payload?.bucket)} />}
        />
        <ChartLegend content={<ChartLegendContent />} />
        <Area
          dataKey="requests"
          type="monotone"
          stroke="var(--color-requests)"
          strokeWidth={2}
          fill="url(#fill-requests)"
          isAnimationActive={false}
        />
        <Area dataKey="errors" type="monotone" stroke="var(--color-errors)" strokeWidth={2} fill="transparent" isAnimationActive={false} />
      </AreaChart>
    </DescribedChart>
  )
}

const spendConfig = { cost_usd: { label: "Spend", color: "var(--chart-1)" } } satisfies ChartConfig

export function SpendChart({ data }: { data: Timeseries }) {
  return (
    <DescribedChart config={spendConfig} className="aspect-auto h-56 w-full" label="Model spend over time" summary={spendSummary(data)}>
      <BarChart data={data.points} margin={{ left: 4, right: 12, top: 8 }} barCategoryGap={2}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey="bucket" {...AXIS} minTickGap={32} tickFormatter={tickFormatter(data.interval_seconds)} />
        <YAxis {...AXIS} width={56} tickFormatter={(v: number) => formatCost(v)} />
        <ChartTooltip
          cursor={{ fill: "var(--accent)", opacity: 0.5 }}
          content={
            <ChartTooltipContent
              hideIndicator
              labelFormatter={(_, payload) => tooltipLabel(payload[0]?.payload?.bucket)}
              formatter={(value) => <span className="font-medium tabular-nums">{formatCost(Number(value))}</span>}
            />
          }
        />
        <Bar dataKey="cost_usd" fill="var(--color-cost_usd)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </DescribedChart>
  )
}
