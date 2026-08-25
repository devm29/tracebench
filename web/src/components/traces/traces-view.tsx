"use client"

import { Activity, Search } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useRef, useState } from "react"

import { RANGE_LABEL, RANGES, RangeControl } from "@/components/overview/filters"
import { PageTitle, Toolbar } from "@/components/page-header"
import { Segmented } from "@/components/segmented"
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states"
import { StatusDot } from "@/components/status"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useUrlState } from "@/hooks/use-url-state"
import { type RangeKey, useFacets, useTraces } from "@/lib/api/hooks"
import { formatCost, formatDuration, formatRelative, formatTokens, shortId } from "@/lib/format"

const ALL = "__all__"
const STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "ok", label: "OK" },
  { value: "error", label: "Errors" },
] as const
type StatusFilter = (typeof STATUS_OPTIONS)[number]["value"]

function FacetSelect({
  label,
  allLabel,
  value,
  options,
  onChange,
}: {
  label: string
  allLabel: string
  value: string
  options: string[] | undefined
  onChange: (value: string | undefined) => void
}) {
  return (
    <Select value={value || ALL} onValueChange={(next) => onChange(next === ALL ? undefined : next)}>
      <SelectTrigger size="sm" className="h-8 min-w-36 rounded-lg text-[13px]" aria-label={label}>
        <SelectValue placeholder={allLabel} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{allLabel}</SelectItem>
        {options?.map((option) => (
          <SelectItem key={option} value={option}>
            {option}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function TracesView() {
  const router = useRouter()
  const facets = useFacets()
  const [range, setRange] = useUrlState<RangeKey>("range", "24h", RANGES)
  const [service, setService] = useUrlState<string>("service", "")
  const [model, setModel] = useUrlState<string>("model", "")
  const [status, setStatus] = useUrlState<StatusFilter>("status", "all", ["all", "ok", "error"])
  const [sessionId, setSessionId] = useUrlState<string>("session_id", "")
  const [q, setQ] = useUrlState<string>("q", "")
  const [search, setSearch] = useState(q)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const handle = window.setTimeout(() => setQ(search.trim() || undefined), 250)
    return () => window.clearTimeout(handle)
  }, [search, setQ])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        searchRef.current?.focus()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const traces = useTraces({
    range,
    service: service || undefined,
    model: model || undefined,
    status: status === "all" ? undefined : status,
    session_id: sessionId || undefined,
    q: q || undefined,
  })
  const rows = traces.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <>
      <Toolbar title="Traces">
        <div className="relative hidden md:block">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            ref={searchRef}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search name or trace id"
            aria-label="Search traces"
            className="h-8 w-72 rounded-full border-transparent bg-secondary pr-12 pl-9 text-[13px]"
          />
          <kbd className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-[11px] text-muted-foreground">⌘K</kbd>
        </div>
      </Toolbar>
      <main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        <PageTitle
          title="Traces"
          subtitle={`Requests your instrumented apps sent, newest first · ${RANGE_LABEL[range]}`}
          actions={
            <>
              <RangeControl value={range} onChange={setRange} />
              <FacetSelect label="Service" allLabel="All services" value={service} options={facets.data?.services} onChange={setService} />
              <FacetSelect label="Model" allLabel="All models" value={model} options={facets.data?.models} onChange={setModel} />
              <Segmented label="Status" value={status} options={STATUS_OPTIONS} onChange={setStatus} />
            </>
          }
        />
        {sessionId ? (
          <div className="flex items-center gap-2 text-[13px]">
            <span className="text-muted-foreground">Session</span>
            <Badge variant="info" className="font-mono">
              {sessionId}
            </Badge>
            <Button variant="link" size="sm" className="h-auto px-1 text-[13px]" onClick={() => setSessionId(undefined)}>
              Clear
            </Button>
          </div>
        ) : null}
        <Card className="gap-0 py-0">
          {traces.isPending ? (
            <TableSkeleton />
          ) : traces.isError ? (
            <ErrorState error={traces.error} onRetry={() => void traces.refetch()} />
          ) : rows.length === 0 ? (
            <EmptyState
              icon={Activity}
              title="No matching traces"
              description="Try a wider time range or filter, or send spans to /v1/traces with any OpenTelemetry exporter."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-10 pl-5 text-[12px]">
                    <span className="sr-only">Status</span>
                  </TableHead>
                  <TableHead className="text-[12px]">Trace</TableHead>
                  <TableHead className="text-[12px]">Service</TableHead>
                  <TableHead className="hidden text-[12px] lg:table-cell">Models</TableHead>
                  <TableHead className="text-right text-[12px]">Duration</TableHead>
                  <TableHead className="hidden text-right text-[12px] md:table-cell">Spans</TableHead>
                  <TableHead className="hidden text-right text-[12px] md:table-cell">Tokens</TableHead>
                  <TableHead className="text-right text-[12px]">Cost</TableHead>
                  <TableHead className="pr-5 text-right text-[12px]">Started</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((trace) => (
                  <TableRow
                    key={trace.trace_id}
                    className="h-12 cursor-pointer hover:bg-accent/50"
                    onClick={() => router.push(`/traces/${trace.trace_id}`)}
                  >
                    <TableCell className="pl-5">
                      <StatusDot error={trace.error_count > 0} />
                    </TableCell>
                    <TableCell className="max-w-72">
                      <Link
                        href={`/traces/${trace.trace_id}`}
                        className="block truncate font-medium outline-none hover:underline focus-visible:ring-4 focus-visible:ring-ring"
                        onClick={(event) => event.stopPropagation()}
                      >
                        {trace.root_name || "(missing root span)"}
                      </Link>
                      <div className="font-mono text-[11px] text-muted-foreground">{shortId(trace.trace_id, 16)}</div>
                    </TableCell>
                    <TableCell className="text-[13px]">{trace.service_name}</TableCell>
                    <TableCell className="hidden lg:table-cell">
                      <div className="flex flex-wrap gap-1">
                        {trace.models.slice(0, 2).map((m) => (
                          <Badge key={m} variant="secondary" className="font-normal">
                            {m}
                          </Badge>
                        ))}
                        {trace.models.length > 2 ? (
                          <Badge variant="secondary" className="font-normal">
                            +{trace.models.length - 2}
                          </Badge>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatDuration(trace.duration_ms)}</TableCell>
                    <TableCell className="hidden text-right text-muted-foreground tabular-nums md:table-cell">{trace.span_count}</TableCell>
                    <TableCell className="hidden text-right text-muted-foreground tabular-nums md:table-cell">
                      {formatTokens(trace.input_tokens + trace.output_tokens)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatCost(trace.cost_usd)}</TableCell>
                    <TableCell className="pr-5 text-right text-[13px] text-muted-foreground tabular-nums">
                      <time dateTime={trace.start_time} title={new Date(trace.start_time).toLocaleString()}>
                        {formatRelative(trace.start_time)}
                      </time>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {traces.hasNextPage ? (
            <div className="flex justify-center border-t border-border/60 py-3">
              <Button variant="secondary" onClick={() => void traces.fetchNextPage()} disabled={traces.isFetchingNextPage}>
                {traces.isFetchingNextPage ? "Loading…" : "Load more"}
              </Button>
            </div>
          ) : null}
        </Card>
      </main>
    </>
  )
}
