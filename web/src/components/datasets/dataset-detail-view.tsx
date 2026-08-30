"use client"

import { ChevronLeft, ChevronRight, FileQuestion, FlaskConical } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { PageTitle, Toolbar } from "@/components/page-header"
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states"
import { RunsTable } from "@/components/evals/runs-table"
import { Badge } from "@/components/ui/badge"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useDatasetItems, useRuns } from "@/lib/api/hooks"
import type { DatasetItem } from "@/lib/api/schemas"
import { formatRelative, lastUserMessage, toText } from "@/lib/format"

import { ItemSheet } from "./item-sheet"
import { RunEvalDialog } from "./run-eval-dialog"
import { ScorerBadges } from "./scorer-badges"

const LATEST = "latest"

export function DatasetDetailView({ datasetId }: { datasetId: string }) {
  const [version, setVersion] = useState<number>()
  const [openKey, setOpenKey] = useState<string>()
  const snapshot = useDatasetItems(datasetId, version)
  const runs = useRuns(datasetId, { poll: true })
  const dataset = snapshot.data?.dataset
  const items = snapshot.data?.items ?? []
  const openItem: DatasetItem | undefined = items.find((item) => item.item_key === openKey)
  const viewingOld = version !== undefined && dataset !== undefined && version < dataset.version

  return (
    <>
      <Toolbar
        title={
          <Link href="/datasets" className="inline-flex items-center text-primary hover:underline">
            <ChevronLeft className="size-4" aria-hidden />
            Datasets
          </Link>
        }
      >
        <RunEvalDialog datasetId={datasetId} disabled={!dataset || dataset.item_count === 0} />
      </Toolbar>
      <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        {snapshot.isError ? (
          <Card>
            <ErrorState error={snapshot.error} onRetry={() => void snapshot.refetch()} />
          </Card>
        ) : (
          <>
            <PageTitle
              title={dataset?.name ?? "Loading…"}
              subtitle={dataset?.description || "Golden cases for regression testing"}
              actions={
                dataset ? (
                  <Select
                    value={version === undefined ? LATEST : String(version)}
                    onValueChange={(next) => setVersion(next === LATEST ? undefined : Number(next))}
                  >
                    <SelectTrigger size="sm" className="h-8 min-w-36 rounded-lg text-[13px]" aria-label="Dataset version">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={LATEST}>Latest (v{dataset.version})</SelectItem>
                      {Array.from({ length: Math.max(dataset.version - 1, 0) }, (_, i) => dataset.version - 1 - i).map((v) => (
                        <SelectItem key={v} value={String(v)}>
                          Version {v}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : null
              }
            />
            {dataset ? (
              <div className="flex flex-wrap items-center gap-3 text-[13px] text-muted-foreground">
                <span>Scored by</span>
                <ScorerBadges scorers={dataset.default_scorers} />
                {viewingOld ? <Badge variant="warning">Viewing version {version} (read only)</Badge> : null}
              </div>
            ) : null}

            <Card className="gap-0 py-0">
              {snapshot.isPending ? (
                <TableSkeleton rows={6} />
              ) : items.length === 0 ? (
                <EmptyState
                  icon={FileQuestion}
                  title="No cases yet"
                  description="Open a trace and choose Add to dataset. Its input and output become a case here."
                />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-5 text-[12px]">Input</TableHead>
                      <TableHead className="text-[12px]">Expected output</TableHead>
                      <TableHead className="hidden text-[12px] md:table-cell">Source</TableHead>
                      <TableHead className="hidden text-right text-[12px] sm:table-cell">Since</TableHead>
                      <TableHead className="w-8 pr-5">
                        <span className="sr-only">Open</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((item) => (
                      <TableRow
                        key={item.id}
                        className="h-14 cursor-pointer hover:bg-accent/50"
                        onClick={() => setOpenKey(item.item_key)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") setOpenKey(item.item_key)
                        }}
                        tabIndex={0}
                        aria-label={`Open case ${item.item_key.slice(0, 8)}`}
                      >
                        <TableCell className="max-w-64 pl-5">
                          <span className="line-clamp-2 text-[13px] whitespace-normal">{lastUserMessage(item.input)}</span>
                        </TableCell>
                        <TableCell className="max-w-md">
                          {item.expected_output === null ? (
                            <span className="text-[13px] text-muted-foreground italic">No expected output</span>
                          ) : (
                            <span className="line-clamp-2 text-[13px] whitespace-normal text-muted-foreground">
                              {toText(item.expected_output)}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="hidden md:table-cell">
                          {item.source_trace_id ? (
                            <Link
                              href={`/traces/${item.source_trace_id}`}
                              onClick={(event) => event.stopPropagation()}
                              className="font-mono text-[12px] text-primary hover:underline"
                            >
                              {item.source_trace_id.slice(0, 8)}
                            </Link>
                          ) : (
                            <span className="text-[12px] text-muted-foreground">manual</span>
                          )}
                          <div className="text-[11px] text-muted-foreground">{formatRelative(item.created_at)}</div>
                        </TableCell>
                        <TableCell className="hidden text-right text-muted-foreground tabular-nums sm:table-cell">
                          v{item.revision}
                        </TableCell>
                        <TableCell className="pr-5 text-muted-foreground">
                          <ChevronRight className="size-4" aria-hidden />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </Card>

            <Card className="gap-2 pb-2">
              <CardHeader>
                <CardTitle>Runs</CardTitle>
                <CardDescription>Every replay of this dataset, from CI or from here</CardDescription>
              </CardHeader>
              {runs.data && runs.data.length > 0 ? (
                <RunsTable runs={runs.data} showDataset={false} />
              ) : runs.isPending ? (
                <TableSkeleton rows={3} />
              ) : (
                <EmptyState
                  icon={FlaskConical}
                  title="Not run yet"
                  description="Start a run here, or add tracebench eval run to your CI pipeline."
                />
              )}
            </Card>
          </>
        )}
      </main>
      <ItemSheet item={openItem} datasetId={datasetId} readOnly={viewingOld} onClose={() => setOpenKey(undefined)} />
    </>
  )
}
