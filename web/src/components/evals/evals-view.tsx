"use client"

import { FlaskConical } from "lucide-react"

import { PageTitle, Toolbar } from "@/components/page-header"
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states"
import { Card } from "@/components/ui/card"
import { useRuns } from "@/lib/api/hooks"

import { RunsTable } from "./runs-table"

export function EvalsView() {
  const runs = useRuns(undefined, { poll: true })
  return (
    <>
      <Toolbar title="Eval runs" />
      <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        <PageTitle title="Eval runs" subtitle="Dataset replays from CI and the dashboard, compared against each dataset's baseline" />
        <Card className="gap-0 py-0">
          {runs.isPending ? (
            <TableSkeleton rows={5} />
          ) : runs.isError ? (
            <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />
          ) : runs.data.length === 0 ? (
            <EmptyState
              icon={FlaskConical}
              title="No eval runs yet"
              description="Run a dataset from its page, or call tracebench eval run from your CI pipeline."
            />
          ) : (
            <RunsTable runs={runs.data} />
          )}
        </Card>
      </main>
    </>
  )
}
