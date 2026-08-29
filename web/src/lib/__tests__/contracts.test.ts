import { describe, expect, it } from "vitest"

import { isActive } from "@/lib/api/hooks"
import { runDiffSchema, traceDetailSchema } from "@/lib/api/schemas"

import runDiff from "./fixtures/run-diff.json"
import traceDetail from "./fixtures/trace-detail.json"

// The fixtures are serialized from the backend's Pydantic response models, so these tests fail
// when the API contract and the zod schemas drift apart.
describe("API contracts", () => {
  it("parses a trace detail and coerces decimal strings to numbers", () => {
    const parsed = traceDetailSchema.parse(traceDetail)
    expect(parsed.rollup.cost_usd).toBeCloseTo(0.0042)
    const [root] = parsed.roots
    expect(root?.children.map((c) => c.operation)).toEqual(["chat", "execute_tool"])
    expect(root?.children[1]?.tool?.name).toBe("lookup_order")
  })

  it("parses a run diff with its recorded gate and warnings", () => {
    const parsed = runDiffSchema.parse(runDiff)
    expect(parsed.head.gate?.passed).toBe(false)
    expect(parsed.counts.regressed).toBe(1)
    expect(parsed.warnings[0]).toMatch(/not comparable/)
  })

  it("rejects a response that is missing fields", () => {
    expect(traceDetailSchema.safeParse({ ...traceDetail, roots: undefined }).success).toBe(false)
  })
})

describe("isActive", () => {
  const now = Date.parse("2026-10-04T12:00:00Z")
  it("polls pending and running runs only while they are recent", () => {
    expect(isActive({ status: "running", created_at: "2026-10-04T11:55:00Z" }, now)).toBe(true)
    expect(isActive({ status: "pending", created_at: "2026-10-04T10:00:00Z" }, now)).toBe(false)
    expect(isActive({ status: "completed", created_at: "2026-10-04T11:59:00Z" }, now)).toBe(false)
  })
})
