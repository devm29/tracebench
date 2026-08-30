"use client"

import { Database } from "lucide-react"
import Link from "next/link"

import { PageTitle, Toolbar } from "@/components/page-header"
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states"
import { Card } from "@/components/ui/card"
import { useDatasets } from "@/lib/api/hooks"
import { formatRelative } from "@/lib/format"

import { CreateDatasetDialog } from "./create-dataset-dialog"
import { ScorerBadges } from "./scorer-badges"

export function DatasetsView() {
  const datasets = useDatasets()
  return (
    <>
      <Toolbar title="Datasets" />
      <main className="mx-auto w-full max-w-5xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        <PageTitle
          title="Datasets"
          subtitle="Golden cases promoted from production traces, versioned on every edit"
          actions={<CreateDatasetDialog />}
        />
        <Card className="gap-0 py-0">
          {datasets.isPending ? (
            <TableSkeleton rows={4} />
          ) : datasets.isError ? (
            <ErrorState error={datasets.error} onRetry={() => void datasets.refetch()} />
          ) : datasets.data.length === 0 ? (
            <EmptyState
              icon={Database}
              title="No datasets yet"
              description="Open any trace and choose Add to dataset to turn it into a regression test."
              action={<CreateDatasetDialog />}
            />
          ) : (
            <ul className="divide-y divide-border/60">
              {datasets.data.map((dataset) => (
                <li key={dataset.id}>
                  <Link
                    href={`/datasets/${dataset.id}`}
                    className="flex flex-col gap-2 px-5 py-4 outline-none transition-colors hover:bg-accent/50 focus-visible:bg-accent/50 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[15px] font-semibold">{dataset.name}</span>
                        <span className="text-[12px] text-muted-foreground tabular-nums">v{dataset.version}</span>
                      </div>
                      {dataset.description ? (
                        <p className="mt-0.5 line-clamp-1 text-[13px] text-muted-foreground">{dataset.description}</p>
                      ) : null}
                      <div className="mt-2">
                        <ScorerBadges scorers={dataset.default_scorers} />
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-6 text-right text-[13px] tabular-nums">
                      <div>
                        <div className="text-[17px] font-semibold">{dataset.item_count}</div>
                        <div className="text-[12px] text-muted-foreground">cases</div>
                      </div>
                      <div>
                        <div className="text-[13px] font-medium">{formatRelative(dataset.updated_at)}</div>
                        <div className="text-[12px] text-muted-foreground">updated</div>
                      </div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </main>
    </>
  )
}
