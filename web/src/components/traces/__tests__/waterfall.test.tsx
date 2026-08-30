// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import traceDetail from "@/lib/__tests__/fixtures/trace-detail.json"
import { traceDetailSchema } from "@/lib/api/schemas"

import { Waterfall } from "../waterfall"

const trace = traceDetailSchema.parse(traceDetail)

function Harness({ onOpen }: { onOpen: (spanId: string) => void }) {
  const [selected, setSelected] = useState<string>()
  return <Waterfall roots={trace.roots} totalMs={trace.duration_ms} selectedId={selected} onSelect={setSelected} onOpen={onOpen} />
}

const rows = () => screen.getAllByRole("treeitem")

afterEach(cleanup)

describe("Waterfall keyboard navigation", () => {
  it("moves the selection with the arrow keys without opening details", () => {
    const onOpen = vi.fn()
    render(<Harness onOpen={onOpen} />)
    const [root, chat] = rows()
    act(() => root?.focus())
    fireEvent.keyDown(root as HTMLElement, { key: "ArrowDown" })
    expect(document.activeElement).toBe(chat)
    expect(chat?.getAttribute("aria-selected")).toBe("true")
    expect(chat?.tabIndex).toBe(0)
    fireEvent.keyDown(chat as HTMLElement, { key: "ArrowUp" })
    expect(document.activeElement).toBe(root)
    expect(onOpen).not.toHaveBeenCalled()
  })

  it("opens the focused span with Enter and on click", () => {
    const onOpen = vi.fn()
    render(<Harness onOpen={onOpen} />)
    const [root, chat] = rows()
    fireEvent.keyDown(root as HTMLElement, { key: "Enter" })
    expect(onOpen).toHaveBeenLastCalledWith(trace.roots[0]?.span_id)
    fireEvent.click(chat as HTMLElement)
    expect(onOpen).toHaveBeenLastCalledWith(trace.roots[0]?.children[0]?.span_id)
  })

  it("collapses and expands children with left and right", () => {
    render(<Harness onOpen={vi.fn()} />)
    const [root] = rows()
    expect(rows()).toHaveLength(3)
    fireEvent.keyDown(root as HTMLElement, { key: "ArrowLeft" })
    expect(rows()).toHaveLength(1)
    expect(root?.getAttribute("aria-expanded")).toBe("false")
    fireEvent.keyDown(root as HTMLElement, { key: "ArrowRight" })
    expect(rows()).toHaveLength(3)
  })
})
