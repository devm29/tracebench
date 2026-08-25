import { describe, expect, it } from "vitest"

import type { Dataset } from "@/lib/api/schemas"
import { defaultDatasetFor } from "@/lib/default-dataset"

const dataset = (name: string): Dataset => ({
  id: name,
  name,
  description: "",
  version: 1,
  item_count: 0,
  default_scorers: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
})

const listed = [dataset("ticket-triage-golden"), dataset("support-agent-golden")]

describe("defaultDatasetFor", () => {
  it("prefers the dataset named after the trace's service", () => {
    expect(defaultDatasetFor(listed, "support-agent")?.name).toBe("support-agent-golden")
  })

  it("matches the service only at the start of the dataset name", () => {
    const reversed = [dataset("support-agent-golden"), dataset("ticket-triage-golden")]
    expect(defaultDatasetFor(reversed, "triage")?.name).toBe("support-agent-golden")
  })

  it("falls back to the first dataset, or nothing when there are none", () => {
    expect(defaultDatasetFor(listed, "docs-qa")?.name).toBe("ticket-triage-golden")
    expect(defaultDatasetFor([], "support-agent")).toBeUndefined()
    expect(defaultDatasetFor(undefined, "support-agent")).toBeUndefined()
  })
})
