"use client"

import { Wrench } from "lucide-react"

import { EmptyState } from "@/components/states"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { ToolHeatmap as ToolHeatmapData } from "@/lib/api/schemas"
import { formatDuration, formatPercent } from "@/lib/format"

const STEPS = [0.04, 0.12, 0.25, 0.5] as const

function intensity(rate: number): number {
  const index = STEPS.findIndex((step) => rate < step)
  return index === -1 ? STEPS.length : index
}

const SHADES = ["bg-destructive/10", "bg-destructive/25", "bg-destructive/45", "bg-destructive/70", "bg-destructive"]

function bucketLabel(iso: string, intervalSeconds: number): string {
  const start = new Date(iso)
  const end = new Date(start.getTime() + intervalSeconds * 1000)
  const day = start.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })
  const time = (d: Date) => d.toLocaleTimeString("en-US", { hour: "numeric" })
  return `${day}, ${time(start)}–${time(end)}`
}

function heatmapCaption(data: ToolHeatmapData): string {
  const worst = data.tools[0]
  const intro = `Tool failure rate by time bucket for ${data.tools.length} ${data.tools.length === 1 ? "tool" : "tools"}.`
  return worst && worst.failures > 0
    ? `${intro} ${worst.tool_name} fails most often: ${worst.failures} of ${worst.calls} calls (${formatPercent(worst.failure_rate)}).`
    : `${intro} No tool calls failed.`
}

export function ToolHeatmap({ data }: { data: ToolHeatmapData }) {
  if (data.tools.length === 0) {
    return (
      <EmptyState
        icon={Wrench}
        title="No tool calls yet"
        description="Spans with gen_ai.tool.name show up here, so you can spot failing tools at a glance."
      />
    )
  }
  const columns = data.buckets.length
  return (
    <div className="overflow-x-auto px-5 pb-5">
      <table className="w-full border-separate border-spacing-0.5">
        <caption className="sr-only">{heatmapCaption(data)}</caption>
        <thead>
          <tr>
            <th scope="col" className="w-40 pr-3 text-left text-[12px] font-medium text-muted-foreground">
              Tool
            </th>
            <th scope="col" colSpan={columns} className="text-left text-[12px] font-medium text-muted-foreground">
              Failure rate over time
            </th>
            <th scope="col" className="pl-3 text-right text-[12px] font-medium text-muted-foreground">
              Calls
            </th>
            <th scope="col" className="pl-3 text-right text-[12px] font-medium text-muted-foreground">
              Failed
            </th>
            <th scope="col" className="pl-3 text-right text-[12px] font-medium text-muted-foreground">
              p95
            </th>
          </tr>
        </thead>
        <tbody>
          {data.tools.map((tool) => (
            <tr key={tool.tool_name}>
              <th scope="row" className="truncate pr-3 text-left font-mono text-[12px] font-normal">
                {tool.tool_name}
              </th>
              {tool.cells.map((cell, index) => {
                const bucket = data.buckets[index] ?? ""
                const rate = cell.calls ? cell.failures / cell.calls : 0
                const label = `${tool.tool_name}, ${bucketLabel(bucket, data.interval_seconds)}: ${cell.failures} of ${cell.calls} calls failed`
                return (
                  <td key={bucket} className="p-0">
                    {/* Hover detail for pointer users; each cell's aria-label carries the same text. */}
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div
                          role="img"
                          aria-label={label}
                          className={`h-6 min-w-2.5 rounded-[3px] transition-opacity hover:opacity-80 ${
                            cell.calls === 0 ? "bg-secondary dark:bg-accent/40" : SHADES[intensity(rate)]
                          }`}
                        />
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-xs">
                        <div className="font-medium">{bucketLabel(bucket, data.interval_seconds)}</div>
                        <div className="tabular-nums">
                          {cell.calls === 0 ? "No calls" : `${cell.failures} of ${cell.calls} failed (${formatPercent(rate)})`}
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </td>
                )
              })}
              <td className="pl-3 text-right text-[13px] tabular-nums">{tool.calls}</td>
              <td className="pl-3 text-right text-[13px] tabular-nums">
                <span className={tool.failure_rate >= 0.1 ? "font-medium text-destructive" : ""}>{formatPercent(tool.failure_rate)}</span>
              </td>
              <td className="pl-3 text-right text-[13px] text-muted-foreground tabular-nums">{formatDuration(tool.p95_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 flex items-center gap-2 text-[11px] text-muted-foreground" aria-hidden>
        <span>0%</span>
        {SHADES.map((shade) => (
          <span key={shade} className={`h-2.5 w-5 rounded-[2px] ${shade}`} />
        ))}
        <span>50%+ failed</span>
        <span className="ml-3 h-2.5 w-5 rounded-[2px] bg-secondary dark:bg-accent/40" />
        <span>no calls</span>
      </div>
    </div>
  )
}
