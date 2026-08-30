import type { Metadata } from "next"

import { TraceDetailView } from "@/components/traces/trace-detail-view"

export const metadata: Metadata = { title: "Trace" }

export default async function TracePage({ params }: { params: Promise<{ traceId: string }> }) {
  const { traceId } = await params
  return <TraceDetailView traceId={traceId.toLowerCase()} />
}
