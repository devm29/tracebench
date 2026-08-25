"use client"

import { ChevronLeft, Copy } from "lucide-react"
import Link from "next/link"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { Toolbar } from "@/components/page-header"
import { ErrorState } from "@/components/states"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { useMediaQuery } from "@/hooks/use-media-query"
import { useTrace } from "@/lib/api/hooks"
import type { SpanNode } from "@/lib/api/schemas"
import { formatCost, formatDateTime, formatDuration, formatTokens } from "@/lib/format"

import { PromoteDialog } from "./promote-dialog"
import { SpanInspector } from "./span-inspector"
import { Waterfall } from "./waterfall"

function findSpan(nodes: SpanNode[], spanId: string | undefined): SpanNode | undefined {
  for (const node of nodes) {
    if (node.span_id === spanId) return node
    const found = findSpan(node.children, spanId)
    if (found) return found
  }
  return undefined
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "error" }) {
  return (
    <div className="min-w-24">
      <div className="text-[12px] text-muted-foreground">{label}</div>
      <div
        className={tone === "error" ? "text-[17px] font-semibold text-destructive tabular-nums" : "text-[17px] font-semibold tabular-nums"}
      >
        {value}
      </div>
    </div>
  )
}

export function TraceDetailView({ traceId }: { traceId: string }) {
  const trace = useTrace(traceId)
  const wide = useMediaQuery("(min-width: 1280px)")
  const phone = !useMediaQuery("(min-width: 768px)")
  const [selectedId, setSelectedId] = useState<string>()
  const [sheetOpen, setSheetOpen] = useState(false)
  const roots = trace.data?.roots
  const selected = useMemo(() => (roots ? (findSpan(roots, selectedId) ?? roots[0]) : undefined), [roots, selectedId])

  const open = (spanId: string) => {
    setSelectedId(spanId)
    if (!wide) setSheetOpen(true)
  }

  return (
    <>
      <Toolbar
        title={
          <span className="flex items-center gap-1">
            <Link href="/traces" className="inline-flex items-center text-primary hover:underline">
              <ChevronLeft className="size-4" aria-hidden />
              Traces
            </Link>
          </span>
        }
      >
        {trace.data && selected ? (
          <PromoteDialog
            traceId={traceId}
            spanId={selected.input_messages.length ? selected.span_id : undefined}
            spanName={selected.input_messages.length ? selected.name : trace.data.root_name}
          />
        ) : null}
      </Toolbar>
      {trace.isError ? (
        <main className="mx-auto max-w-3xl px-6 py-10">
          <Card>
            <ErrorState error={trace.error} onRetry={() => void trace.refetch()} />
          </Card>
        </main>
      ) : !trace.data || !selected ? (
        <main className="mx-auto max-w-7xl space-y-4 px-6 py-8">
          <Skeleton className="h-10 w-80" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-96 w-full" />
        </main>
      ) : (
        <div className="grid min-h-[calc(100dvh-52px)] grid-cols-1 xl:grid-cols-[1fr_400px]">
          <main className="min-w-0 space-y-6 px-4 py-8 sm:px-6 lg:px-8">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-[28px] leading-[34px] font-semibold tracking-tight break-all">{trace.data.root_name}</h1>
                {trace.data.rollup.error_count > 0 ? (
                  <Badge variant="destructive">
                    {trace.data.rollup.error_count} {trace.data.rollup.error_count === 1 ? "error" : "errors"}
                  </Badge>
                ) : (
                  <Badge variant="success">OK</Badge>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
                <button
                  type="button"
                  className="inline-flex items-center gap-1 font-mono text-[12px] hover:text-foreground"
                  onClick={() => {
                    void navigator.clipboard.writeText(traceId)
                    toast.success("Trace id copied")
                  }}
                  aria-label="Copy trace id"
                >
                  {traceId}
                  <Copy className="size-3" aria-hidden />
                </button>
                <span>{trace.data.services.join(", ")}</span>
                <span>{formatDateTime(trace.data.start_time)}</span>
                {trace.data.session_id ? (
                  <Link href={`/traces?session_id=${encodeURIComponent(trace.data.session_id)}`} className="text-primary hover:underline">
                    Session {trace.data.session_id}
                  </Link>
                ) : null}
              </div>
            </div>

            <Card className="py-4">
              <div className="grid grid-cols-3 gap-x-6 gap-y-4 px-5 md:grid-cols-6">
                <Metric label="Duration" value={formatDuration(trace.data.duration_ms)} />
                <Metric label="Spans" value={String(trace.data.rollup.span_count)} />
                <Metric label="LLM calls" value={String(trace.data.rollup.llm_calls)} />
                <Metric label="Tool calls" value={String(trace.data.rollup.tool_calls)} />
                <Metric label="Tokens" value={formatTokens(trace.data.rollup.input_tokens + trace.data.rollup.output_tokens)} />
                <Metric label="Cost" value={formatCost(trace.data.rollup.cost_usd)} />
              </div>
            </Card>

            <Card className="gap-0 pb-0">
              <CardHeader className="pb-3">
                <CardTitle>Timeline</CardTitle>
              </CardHeader>
              <Waterfall
                roots={trace.data.roots}
                totalMs={trace.data.duration_ms}
                selectedId={selected.span_id}
                onSelect={setSelectedId}
                onOpen={open}
              />
            </Card>

            {trace.data.models.length ? (
              <Card className="gap-3">
                <CardHeader>
                  <CardTitle>Model usage</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="divide-y divide-border/60">
                    {trace.data.models.map((usage) => (
                      <li key={usage.model} className="flex items-center justify-between gap-4 py-2 text-[13px]">
                        <span className="font-medium">{usage.model}</span>
                        <span className="text-muted-foreground tabular-nums">
                          {usage.calls} {usage.calls === 1 ? "call" : "calls"} · {formatTokens(usage.input_tokens)} in ·{" "}
                          {formatTokens(usage.cache_read_tokens)} cached · {formatTokens(usage.output_tokens)} out
                        </span>
                        <span className="font-medium tabular-nums">{formatCost(usage.cost_usd)}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            ) : null}
          </main>
          <aside className="hidden border-l border-border/60 bg-background/60 xl:block" aria-label="Span details">
            <div className="sticky top-13 max-h-[calc(100dvh-52px)] overflow-y-auto p-5">
              <SpanInspector span={selected} />
            </div>
          </aside>
          <Sheet open={sheetOpen && !wide} onOpenChange={setSheetOpen}>
            <SheetContent
              side={phone ? "bottom" : "right"}
              className={phone ? "max-h-[85dvh] overflow-y-auto rounded-t-2xl" : "w-[420px] overflow-y-auto sm:max-w-[420px]"}
            >
              <SheetHeader className="sr-only">
                <SheetTitle>Span details</SheetTitle>
              </SheetHeader>
              <div className="p-5">
                <SpanInspector span={selected} />
              </div>
            </SheetContent>
          </Sheet>
        </div>
      )}
    </>
  )
}
