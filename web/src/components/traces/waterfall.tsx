"use client"

import { ChevronRight } from "lucide-react"
import { useMemo, useState, type KeyboardEvent } from "react"

import type { SpanNode } from "@/lib/api/schemas"
import { formatCost, formatDuration } from "@/lib/format"
import { cn } from "@/lib/utils"

import { CATEGORIES, categorize } from "./span-kind"

interface Row {
  node: SpanNode
  hasChildren: boolean
}

function visibleRows(roots: SpanNode[], collapsed: ReadonlySet<string>): Row[] {
  const rows: Row[] = []
  const walk = (node: SpanNode) => {
    rows.push({ node, hasChildren: node.children.length > 0 })
    if (!collapsed.has(node.span_id)) node.children.forEach(walk)
  }
  roots.forEach(walk)
  return rows
}

const TICKS = [0, 0.25, 0.5, 0.75, 1] as const

export function Waterfall({
  roots,
  totalMs,
  selectedId,
  onSelect,
  onOpen,
}: {
  roots: SpanNode[]
  totalMs: number
  selectedId: string | undefined
  /** Moves the highlight; arrow keys call only this, so keyboard navigation never opens a sheet. */
  onSelect: (spanId: string) => void
  /** Explicit activation (click, Enter, Space), e.g. to show details in a sheet on narrow screens. */
  onOpen?: (spanId: string) => void
}) {
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set())
  const rows = useMemo(() => visibleRows(roots, collapsed), [roots, collapsed])
  const total = Math.max(totalMs, 1)

  const toggle = (spanId: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(spanId)) next.delete(spanId)
      else next.add(spanId)
      return next
    })

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>, index: number) => {
    const row = rows[index]
    if (!row) return
    const focusRow = (target: number) => {
      const next = rows[target]
      if (!next) return
      onSelect(next.node.span_id)
      document.getElementById(`span-row-${next.node.span_id}`)?.focus()
    }
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault()
        focusRow(index + 1)
        break
      case "ArrowUp":
        event.preventDefault()
        focusRow(index - 1)
        break
      case "ArrowLeft":
        if (row.hasChildren && !collapsed.has(row.node.span_id)) toggle(row.node.span_id)
        break
      case "ArrowRight":
        if (row.hasChildren && collapsed.has(row.node.span_id)) toggle(row.node.span_id)
        break
      case "Enter":
      case " ":
        event.preventDefault()
        onSelect(row.node.span_id)
        onOpen?.(row.node.span_id)
        break
    }
  }

  return (
    <div className="text-[13px]">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 pb-3 text-[12px] text-muted-foreground">
        {CATEGORIES.map((category) => (
          <span key={category.key} className="inline-flex items-center gap-1.5">
            <span className={cn("h-2 w-3 rounded-[2px]", category.bar)} aria-hidden />
            {category.label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-3 rounded-[2px] bg-destructive" aria-hidden />
          Error
        </span>
      </div>
      <div className="grid grid-cols-[minmax(220px,38%)_1fr] border-y border-border/60 bg-secondary/50 text-[11px] text-muted-foreground dark:bg-accent/20">
        <div className="px-5 py-1.5 font-medium">Span</div>
        <div className="relative h-full">
          {TICKS.map((tick) => (
            <span
              key={tick}
              className={cn(
                "absolute top-1.5 -translate-x-full pr-1 whitespace-nowrap tabular-nums first:translate-x-0 first:pl-1",
                tick !== 0 && tick !== 1 && "hidden sm:inline"
              )}
              style={{ left: `${tick * 100}%` }}
            >
              {formatDuration(total * tick)}
            </span>
          ))}
        </div>
      </div>
      <div role="tree" aria-label="Span tree">
        {rows.map(({ node, hasChildren }, index) => {
          const category = categorize(node)
          const Icon = category.icon
          const left = (node.offset_ms / total) * 100
          const width = Math.max((node.duration_ms / total) * 100, 0.4)
          const selected = node.span_id === selectedId
          const error = node.status === "error"
          const meta = node.tool?.name ?? node.model
          const labelInside = width > 30 && left + width > 78
          return (
            <div
              key={node.span_id}
              id={`span-row-${node.span_id}`}
              role="treeitem"
              aria-selected={selected}
              aria-level={node.depth + 1}
              aria-expanded={hasChildren ? !collapsed.has(node.span_id) : undefined}
              tabIndex={selected || (!selectedId && index === 0) ? 0 : -1}
              onClick={() => {
                onSelect(node.span_id)
                onOpen?.(node.span_id)
              }}
              onKeyDown={(event) => onKeyDown(event, index)}
              className={cn(
                "group grid h-9 cursor-default grid-cols-[minmax(220px,38%)_1fr] items-center border-b border-border/40 outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
                selected ? "bg-primary/10" : "hover:bg-accent/50"
              )}
            >
              <div className="flex min-w-0 items-center gap-1.5 pr-3 pl-3" style={{ paddingLeft: 12 + node.depth * 16 }}>
                {hasChildren ? (
                  <button
                    type="button"
                    tabIndex={-1}
                    aria-label={collapsed.has(node.span_id) ? "Expand" : "Collapse"}
                    onClick={(event) => {
                      event.stopPropagation()
                      toggle(node.span_id)
                    }}
                    className="grid size-5 shrink-0 place-items-center rounded text-muted-foreground hover:bg-accent"
                  >
                    <ChevronRight
                      className={cn("size-3.5 transition-transform duration-150", !collapsed.has(node.span_id) && "rotate-90")}
                    />
                  </button>
                ) : (
                  <span className="size-5 shrink-0" />
                )}
                <Icon
                  className={cn("size-3.5 shrink-0", error ? "text-destructive" : "text-muted-foreground")}
                  strokeWidth={1.75}
                  aria-hidden
                />
                <span className={cn("truncate", error && "text-destructive")}>{node.name}</span>
                {meta && !node.name.includes(meta) ? <span className="truncate text-[11px] text-muted-foreground">{meta}</span> : null}
              </div>
              <div className="relative mr-4 h-full">
                {TICKS.slice(1, -1).map((tick) => (
                  <span key={tick} className="absolute inset-y-0 w-px bg-border/50" style={{ left: `${tick * 100}%` }} aria-hidden />
                ))}
                <div
                  className={cn("absolute top-1/2 h-3.5 -translate-y-1/2 rounded-[4px]", error ? "bg-destructive" : category.bar)}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  aria-hidden
                />
                <span
                  className={cn(
                    "absolute top-1/2 -translate-y-1/2 text-[11px] whitespace-nowrap tabular-nums",
                    labelInside
                      ? cn("pr-2 font-medium", error ? "text-white dark:text-neutral-950" : category.barText)
                      : "text-muted-foreground",
                    !labelInside && (left + width > 78 ? "pr-1.5" : "pl-1.5")
                  )}
                  style={
                    labelInside || left + width > 78
                      ? { right: `${100 - left - (labelInside ? width : 0)}%` }
                      : { left: `${left + width}%` }
                  }
                >
                  {formatDuration(node.duration_ms)}
                  {node.cost_usd > 0 ? <span className="hidden sm:inline"> · {formatCost(node.cost_usd)}</span> : null}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
