import { ArrowDownRight, ArrowUpRight } from "lucide-react"
import type { ReactNode } from "react"

import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

export function StatTile({
  label,
  value,
  hint,
  change,
  goodWhen = "up",
  loading,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  change?: number | null
  goodWhen?: "up" | "down"
  loading?: boolean
}) {
  const hasChange = change !== undefined && change !== null && Number.isFinite(change)
  const improving = hasChange && (goodWhen === "up" ? change >= 0 : change <= 0)
  return (
    <Card className="gap-1 py-4">
      <div className="px-5 text-[13px] text-muted-foreground">{label}</div>
      <div className="px-5 text-[28px] leading-[34px] font-semibold tracking-tight tabular-nums">
        {loading ? <Skeleton className="my-1 h-7 w-24" /> : value}
      </div>
      <div className="flex items-center gap-2 px-5 text-[13px] text-muted-foreground tabular-nums">
        {hasChange ? (
          <span className={cn("inline-flex items-center gap-0.5 font-medium", improving ? "text-success" : "text-destructive")}>
            {change >= 0 ? <ArrowUpRight className="size-3.5" aria-hidden /> : <ArrowDownRight className="size-3.5" aria-hidden />}
            {Math.abs(change * 100).toFixed(1)}%
            <span className="sr-only">{improving ? "improvement" : "regression"} vs previous period</span>
          </span>
        ) : null}
        {hint ? <span className="truncate">{hint}</span> : null}
      </div>
    </Card>
  )
}
