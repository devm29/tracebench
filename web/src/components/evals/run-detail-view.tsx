"use client"

import { ChevronLeft, Loader2, TriangleAlert } from "lucide-react"
import Link from "next/link"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { PageTitle, Toolbar } from "@/components/page-header"
import { Segmented } from "@/components/segmented"
import { StatTile } from "@/components/stat-tile"
import { ErrorState, TableSkeleton } from "@/components/states"
import { GateBadge, RunStatusBadge } from "@/components/status"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useRun, useRunDiff, useRunResults, useRuns, useSetBaseline } from "@/lib/api/hooks"
import type { DiffStatus, EvalRun } from "@/lib/api/schemas"
import { formatDateTime, formatDuration, formatPercent } from "@/lib/format"

import { DiffList, STATUS_META } from "./diff-list"
import { ResultsList } from "./results-list"

const NONE = "__none__"
const CHANGED: ReadonlySet<DiffStatus> = new Set(["regressed", "fixed", "unchanged_fail", "added", "removed"])

function defaultComparison(run: EvalRun, runs: EvalRun[]): string | undefined {
  const candidates = runs.filter((r) => r.id !== run.id && r.status === "completed")
  if (!run.is_baseline) {
    const baseline = candidates.find((r) => r.is_baseline)
    if (baseline) return baseline.id
  }
  return candidates.find((r) => new Date(r.created_at) < new Date(run.created_at))?.id
}

export function RunDetailView({ runId }: { runId: string }) {
  const run = useRun(runId)
  const siblings = useRuns(run.data?.dataset_id)
  const completed = run.data?.status === "completed"
  const results = useRunResults(runId, completed)
  const [chosen, setChosen] = useState<string>()
  const [filter, setFilter] = useState<"changed" | "all">("changed")
  const setBaseline = useSetBaseline()

  const others = useMemo(() => (siblings.data ?? []).filter((r) => r.id !== runId && r.status === "completed"), [siblings.data, runId])
  const compareWith = chosen === NONE ? undefined : (chosen ?? (run.data ? defaultComparison(run.data, others) : undefined))
  const diff = useRunDiff(compareWith, completed ? runId : undefined)
  const summary = run.data?.summary
  const baseSummary = diff.data?.base.summary
  const regressions = diff.data?.counts.regressed ?? 0
  const visibleItems = diff.data?.items.filter((item) => filter === "all" || CHANGED.has(item.status)) ?? []

  if (run.isError) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-10">
        <Card>
          <ErrorState error={run.error} onRetry={() => void run.refetch()} />
        </Card>
      </main>
    )
  }

  return (
    <>
      <Toolbar
        title={
          <Link href="/evals" className="inline-flex items-center text-primary hover:underline">
            <ChevronLeft className="size-4" aria-hidden />
            Eval runs
          </Link>
        }
      >
        {run.data && completed && !run.data.is_baseline ? (
          <Button
            variant="secondary"
            disabled={setBaseline.isPending}
            onClick={() =>
              setBaseline.mutate(runId, {
                onSuccess: () => toast.success("This run is now the baseline"),
                onError: (error) => toast.error("Couldn't set the baseline", { description: error.message }),
              })
            }
          >
            Make baseline
          </Button>
        ) : null}
      </Toolbar>
      <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        {!run.data ? (
          <TableSkeleton rows={6} />
        ) : (
          <>
            <PageTitle
              title={
                <span className="flex flex-wrap items-center gap-2">
                  {run.data.name ?? `Run ${run.data.id.slice(0, 8)}`}
                  {run.data.is_baseline ? <Badge variant="info">Baseline</Badge> : null}
                </span>
              }
              subtitle={
                <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <Link href={`/datasets/${run.data.dataset_id}`} className="text-primary hover:underline">
                    {run.data.dataset_name} v{run.data.dataset_version}
                  </Link>
                  <span className="font-mono">{run.data.target_url}</span>
                  {run.data.git_ref ? <span className="font-mono">{run.data.git_ref}</span> : null}
                  {run.data.git_sha ? <span className="font-mono">{run.data.git_sha.slice(0, 7)}</span> : null}
                  <span>{formatDateTime(run.data.created_at)}</span>
                </span>
              }
              actions={
                <div className="flex items-center gap-2">
                  <RunStatusBadge status={run.data.status} />
                  {run.data.gate ? <GateBadge passed={run.data.gate.passed} /> : null}
                </div>
              }
            />

            {run.data.gate && !run.data.gate.passed ? (
              <Card className="gap-1 px-5 text-[13px]" aria-label="Why the CI gate failed">
                <span className="font-medium">The CI gate failed this run</span>
                <ul className="list-disc pl-5 text-muted-foreground">
                  {run.data.gate.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </Card>
            ) : null}

            {run.data.status === "failed" ? (
              <Card role="alert" className="px-5 text-[13px] text-destructive">
                {run.data.error ?? "The run failed."}
              </Card>
            ) : null}

            {!completed && run.data.status !== "failed" ? (
              <Card className="items-center py-12 text-[13px] text-muted-foreground" aria-live="polite">
                <Loader2 className="size-5 animate-spin" aria-hidden />
                Replaying cases against your app…
              </Card>
            ) : null}

            {summary ? (
              <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Run summary">
                <StatTile
                  label="Pass rate"
                  value={formatPercent(summary.pass_rate)}
                  change={baseSummary ? summary.pass_rate - baseSummary.pass_rate : null}
                  hint={`${summary.passed} of ${summary.total} cases`}
                />
                <StatTile
                  label="Failed"
                  value={String(summary.failed)}
                  hint={summary.errored ? `${summary.errored} errored` : "no target errors"}
                />
                {Object.entries(summary.mean_scores)
                  .slice(0, 1)
                  .map(([scorer, mean]) => (
                    <StatTile
                      key={scorer}
                      label={`Mean ${scorer.replace("_", " ")}`}
                      value={mean.toFixed(3)}
                      change={baseSummary?.mean_scores[scorer] !== undefined ? mean - (baseSummary.mean_scores[scorer] ?? 0) : null}
                      hint={Object.entries(summary.mean_scores)
                        .slice(1)
                        .map(([name, value]) => `${name.replace("_", " ")} ${value.toFixed(2)}`)
                        .join(" · ")}
                    />
                  ))}
                <StatTile
                  label="p95 latency"
                  value={summary.latency_p95_ms !== null ? formatDuration(summary.latency_p95_ms) : "-"}
                  goodWhen="down"
                  hint={summary.latency_p50_ms !== null ? `p50 ${formatDuration(summary.latency_p50_ms)}` : undefined}
                />
              </section>
            ) : null}

            {completed ? (
              <Card className="gap-3 pb-0">
                <CardHeader className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <CardTitle>{compareWith ? "Compared with" : "Results"}</CardTitle>
                    <CardDescription>
                      {compareWith ? "Cases that changed outcome between the two runs come first" : "Failing cases first"}
                    </CardDescription>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Select value={compareWith ?? NONE} onValueChange={setChosen}>
                      <SelectTrigger size="sm" className="h-8 min-w-56 rounded-lg text-[13px]" aria-label="Compare with run">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NONE}>No comparison</SelectItem>
                        {others.map((other) => (
                          <SelectItem key={other.id} value={other.id}>
                            {other.is_baseline ? "Baseline · " : ""}
                            {other.name ?? other.id.slice(0, 8)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {diff.data ? (
                      <Segmented
                        label="Show"
                        value={filter}
                        onChange={setFilter}
                        options={[
                          { value: "changed", label: "Needs attention" },
                          { value: "all", label: "All" },
                        ]}
                      />
                    ) : null}
                  </div>
                </CardHeader>
                {compareWith ? (
                  diff.data ? (
                    <>
                      <div className="flex flex-wrap gap-2 px-5">
                        {(Object.keys(STATUS_META) as DiffStatus[])
                          .filter((status) => (diff.data.counts[status] ?? 0) > 0)
                          .map((status) => (
                            <Badge key={status} variant={STATUS_META[status].variant}>
                              {diff.data.counts[status]} {STATUS_META[status].label.toLowerCase()}
                            </Badge>
                          ))}
                        <span className="text-[12px] text-muted-foreground tabular-nums">
                          {regressions === 0 ? "No regressions" : `${regressions} regressed`} · pass rate{" "}
                          {diff.data.pass_rate_delta >= 0 ? "+" : ""}
                          {(diff.data.pass_rate_delta * 100).toFixed(1)} pp vs {diff.data.base.name ?? diff.data.base.id.slice(0, 8)}
                        </span>
                      </div>
                      {diff.data.warnings.length ? (
                        <ul className="mt-2 space-y-1 px-5 text-[12px] text-muted-foreground" aria-label="Comparison warnings">
                          {diff.data.warnings.map((warning) => (
                            <li key={warning} className="flex gap-1.5">
                              <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden />
                              {warning}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      <div className="mt-2 border-t border-border/60">
                        {visibleItems.length ? (
                          <DiffList items={visibleItems} />
                        ) : (
                          <p className="px-5 py-8 text-center text-[13px] text-muted-foreground">
                            Every case has the same outcome as the comparison run.
                          </p>
                        )}
                      </div>
                    </>
                  ) : (
                    <TableSkeleton rows={4} />
                  )
                ) : results.data ? (
                  <div className="border-t border-border/60">
                    <ResultsList results={results.data} />
                  </div>
                ) : (
                  <TableSkeleton rows={4} />
                )}
              </Card>
            ) : null}
          </>
        )}
      </main>
    </>
  )
}
