import type { Metadata } from "next"

import { PricesView } from "@/components/prices/prices-view"

export const metadata: Metadata = { title: "Model prices" }

export default function PricesPage() {
  return <PricesView />
}
