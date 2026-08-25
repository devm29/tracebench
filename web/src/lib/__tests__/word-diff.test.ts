import { describe, expect, it } from "vitest"

import { wordDiff } from "../word-diff"

const render = (before: string, after: string) =>
  wordDiff(before, after)
    .map((op) => (op.kind === "same" ? op.text : op.kind === "added" ? `[+${op.text}]` : `[-${op.text}]`))
    .join("")

describe("wordDiff", () => {
  it("returns a single unchanged run for identical text", () => {
    expect(wordDiff("refund issued", "refund issued")).toEqual([{ kind: "same", text: "refund issued" }])
  })

  it("marks inserted and removed words while keeping shared ones", () => {
    expect(render("Your refund of $89 was issued", "Your refund was issued today")).toBe("Your refund [-of $89 ]was issued[+ today]")
  })

  it("handles empty sides", () => {
    expect(wordDiff("", "new")).toEqual([{ kind: "added", text: "new" }])
    expect(wordDiff("old", "")).toEqual([{ kind: "removed", text: "old" }])
  })

  it("falls back to a whole replacement for very long inputs", () => {
    const long = "word ".repeat(2000)
    expect(wordDiff(long, "short").map((op) => op.kind)).toEqual(["removed", "added"])
  })
})
