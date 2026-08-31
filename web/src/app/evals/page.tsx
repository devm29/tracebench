import type { Metadata } from "next"

import { EvalsView } from "@/components/evals/evals-view"

export const metadata: Metadata = { title: "Eval runs" }

export default function EvalsPage() {
  return <EvalsView />
}
