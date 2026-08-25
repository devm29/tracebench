import { Suspense } from "react"

import { OverviewView } from "@/components/overview/overview-view"

export default function OverviewPage() {
  return (
    <Suspense>
      <OverviewView />
    </Suspense>
  )
}
