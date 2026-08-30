import type { Metadata } from "next"
import { Suspense } from "react"

import { TracesView } from "@/components/traces/traces-view"

export const metadata: Metadata = { title: "Traces" }

export default function TracesPage() {
  return (
    <Suspense>
      <TracesView />
    </Suspense>
  )
}
