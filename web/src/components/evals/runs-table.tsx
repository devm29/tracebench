"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"

import { RunStatusBadge } from "@/components/status"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { EvalRun } from "@/lib/api/schemas"
import { formatPercent, formatRelative } from "@/lib/format"
import { cn } from "@/lib/utils"

export function PassRate({ value }: { value: number }) {
  const tone = value >= 0.95 ? "bg-success" : value >= 0.8 ? "bg-warning" : "bg-destructive"
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-secondary dark:bg-accent/50" aria-hidden>
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${value * 100}%` }} />
      </div>
      <span className="w-12 text-right font-medium tabular-nums">{formatPercent(value)}</span>
    </div>
  )
}

export function RunsTable({ runs, showDataset = true }: { runs: EvalRun[]; showDataset?: boolean }) {
  const router = useRouter()
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="pl-5 text-[12px]">Run</TableHead>
          {showDataset ? <TableHead className="text-[12px]">Dataset</TableHead> : null}
          <TableHead className="hidden text-[12px] md:table-cell">Branch</TableHead>
          <TableHead className="text-[12px]">Status</TableHead>
          <TableHead className="text-right text-[12px]">Pass rate</TableHead>
          <TableHead className="hidden text-right text-[12px] sm:table-cell">Cases</TableHead>
          <TableHead className="pr-5 text-right text-[12px]">Started</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((run) => (
          <TableRow key={run.id} className="h-12 cursor-pointer hover:bg-accent/50" onClick={() => router.push(`/evals/${run.id}`)}>
            <TableCell className="max-w-72 pl-5">
              <div className="flex items-center gap-2">
                <Link
                  href={`/evals/${run.id}`}
                  onClick={(event) => event.stopPropagation()}
                  className="truncate font-medium hover:underline"
                >
                  {run.name ?? `Run ${run.id.slice(0, 8)}`}
                </Link>
                {run.is_baseline ? <Badge variant="info">Baseline</Badge> : null}
              </div>
              <div className="font-mono text-[11px] text-muted-foreground">{run.git_sha?.slice(0, 7) ?? run.id.slice(0, 8)}</div>
            </TableCell>
            {showDataset ? (
              <TableCell className="text-[13px]">
                {run.dataset_name} <span className="text-muted-foreground">v{run.dataset_version}</span>
              </TableCell>
            ) : null}
            <TableCell className="hidden font-mono text-[12px] text-muted-foreground md:table-cell">{run.git_ref ?? "-"}</TableCell>
            <TableCell>
              <RunStatusBadge status={run.status} />
            </TableCell>
            <TableCell className="text-right">{run.summary ? <PassRate value={run.summary.pass_rate} /> : "-"}</TableCell>
            <TableCell className="hidden text-right text-muted-foreground tabular-nums sm:table-cell">
              {run.summary ? `${run.summary.passed}/${run.summary.total}` : "-"}
            </TableCell>
            <TableCell className="pr-5 text-right text-[13px] text-muted-foreground">{formatRelative(run.created_at)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
