import { describe, expect, it } from "vitest"

import { parseExpected } from "@/lib/expected-output"

describe("parseExpected", () => {
  it("keeps text answers as text, even when they look like JSON", () => {
    expect(parseExpected('{"a": 1}', "old answer")).toEqual({ ok: true, value: '{"a": 1}' })
  })

  it("parses JSON when the original was structured", () => {
    expect(parseExpected('{"priority": "high"}', { priority: "low" })).toEqual({ ok: true, value: { priority: "high" } })
  })

  it("rejects invalid JSON instead of silently saving a string", () => {
    const result = parseExpected('{"priority": ', { priority: "low" })
    expect(result.ok).toBe(false)
  })

  it("treats an empty editor as clearing the expected output", () => {
    expect(parseExpected("   ", { priority: "low" })).toEqual({ ok: true, value: null })
  })
})
