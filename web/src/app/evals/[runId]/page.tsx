import type { Metadata } from "next"

import { RunDetailView } from "@/components/evals/run-detail-view"

export const metadata: Metadata = { title: "Eval run" }

export default async function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params
  return <RunDetailView runId={runId} />
}
