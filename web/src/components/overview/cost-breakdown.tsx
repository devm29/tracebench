"use client"

import Link from "next/link"
import { useState } from "react"

import { Segmented } from "@/components/segmented"
import { Skeleton } from "@/components/ui/skeleton"
import { useCostBreakdown, type RangeKey } from "@/lib/api/hooks"
import type { CostDimension } from "@/lib/api/schemas"
import { formatCost, formatNumber, formatPercent, formatTokens } from "@/lib/format"

const OPTIONS = [
  { value: "model", label: "Model" },
  { value: "service", label: "Service" },
  { value: "session", label: "Session" },
] as const satisfies ReadonlyArray<{ value: CostDimension; label: string }>

export function CostBreakdownList({ range, service }: { range: RangeKey; service: string | undefined }) {
  const [groupBy, setGroupBy] = useState<CostDimension>("model")
  const query = useCostBreakdown(range, groupBy, service, 6)
  return (
    <div className="flex flex-col gap-4 px-5">
      <Segmented label="Group spend by" value={groupBy} options={OPTIONS} onChange={setGroupBy} />
      {query.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : query.data && query.data.rows.length > 0 ? (
        <ul className="divide-y divide-border/60">
          {query.data.rows.map((row) => (
            <li key={row.key} className="py-2.5">
              <div className="flex items-baseline justify-between gap-3 text-[13px]">
                {groupBy === "session" ? (
                  <Link
                    href={`/traces?session_id=${encodeURIComponent(row.key)}`}
                    className="truncate font-mono text-[12px] text-primary hover:underline"
                  >
                    {row.key}
                  </Link>
                ) : (
                  <span className="truncate font-medium">{row.key}</span>
                )}
                <span className="font-medium tabular-nums">{formatCost(row.cost_usd)}</span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-secondary dark:bg-accent/50">
                <div className="h-full rounded-full bg-chart-1" style={{ width: `${Math.max(row.share * 100, 1)}%` }} />
              </div>
              <div className="mt-1 flex justify-between text-[12px] text-muted-foreground tabular-nums">
                <span>
                  {formatNumber(row.calls)} {groupBy === "model" ? "calls" : "requests"} · {formatTokens(row.input_tokens + row.output_tokens)} tokens
                </span>
                <span>{formatPercent(row.share)}</span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="py-8 text-center text-[13px] text-muted-foreground">No spend recorded in this range.</p>
      )}
    </div>
  )
}
