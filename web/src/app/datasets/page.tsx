import type { Metadata } from "next"

import { DatasetsView } from "@/components/datasets/datasets-view"

export const metadata: Metadata = { title: "Datasets" }

export default function DatasetsPage() {
  return <DatasetsView />
}
