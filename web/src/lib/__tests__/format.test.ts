import { describe, expect, it } from "vitest"

import { delta, formatCost, formatDuration, lastUserMessage, toText } from "../format"

describe("format helpers", () => {
  it("formats durations across magnitudes", () => {
    expect(formatDuration(0.4)).toBe("<1 ms")
    expect(formatDuration(240)).toBe("240 ms")
    expect(formatDuration(5420)).toBe("5.42 s")
    expect(formatDuration(125_000)).toBe("2m 5s")
  })

  it("keeps small costs readable", () => {
    expect(formatCost(0)).toBe("$0.00")
    expect(formatCost(0.00004)).toBe("<$0.0001")
    expect(formatCost(0.0054)).toBe("$0.0054")
    expect(formatCost(2.544)).toBe("$2.54")
  })

  it("computes relative change only against a non-zero baseline", () => {
    expect(delta(150, 100)).toBe(0.5)
    expect(delta(5, 0)).toBeNull()
  })

  it("extracts the last user turn from a replay input", () => {
    const input = {
      messages: [
        { role: "user", content: "first" },
        { role: "assistant", content: "x" },
        { role: "user", content: "last" },
      ],
    }
    expect(lastUserMessage(input)).toBe("last")
    expect(lastUserMessage("plain")).toBe("plain")
    expect(toText({ a: 1 })).toBe('{\n  "a": 1\n}')
  })
})
