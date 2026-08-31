"use client"

import { ChevronRight } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import type { DiffStatus, ItemDiff } from "@/lib/api/schemas"
import { formatDuration, lastUserMessage, toText } from "@/lib/format"
import { cn } from "@/lib/utils"

import { DiffText } from "./diff-text"

export const STATUS_META: Record<DiffStatus, { label: string; variant: "destructive" | "success" | "secondary" | "warning" | "info" }> = {
  regressed: { label: "Regressed", variant: "destructive" },
  fixed: { label: "Fixed", variant: "success" },
  unchanged_fail: { label: "Still failing", variant: "warning" },
  unchanged_pass: { label: "Passing", variant: "secondary" },
  added: { label: "New case", variant: "info" },
  removed: { label: "Removed", variant: "secondary" },
}

function Column({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 space-y-1.5">
      <div className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{title}</div>
      <div className="rounded-lg bg-secondary px-3 py-2 dark:bg-accent/30">{children}</div>
    </div>
  )
}

function DiffRow({ item, defaultOpen }: { item: ItemDiff; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const meta = STATUS_META[item.status]
  const base = item.base_error ?? toText(item.base_output)
  const head = item.head_error ?? toText(item.head_output)
  return (
    <li className="border-b border-border/60 last:border-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-5 py-3 text-left outline-none transition-colors hover:bg-accent/40 focus-visible:bg-accent/40"
      >
        <ChevronRight className={cn("size-4 shrink-0 text-muted-foreground transition-transform duration-150", open && "rotate-90")} aria-hidden />
        <Badge variant={meta.variant} className="w-24 justify-center">
          {meta.label}
        </Badge>
        <span className="min-w-0 flex-1 truncate text-[13px]">{lastUserMessage(item.input)}</span>
        <span className="hidden gap-2 sm:flex">
          {item.score_deltas
            .filter((d) => d.delta !== null && Math.abs(d.delta) >= 0.01)
            .map((d) => (
              <span
                key={d.scorer}
                className={cn("text-[12px] tabular-nums", (d.delta ?? 0) < 0 ? "text-destructive" : "text-success")}
              >
                {d.scorer.replace("_", " ")} {(d.delta ?? 0) > 0 ? "+" : ""}
                {(d.delta ?? 0).toFixed(2)}
              </span>
            ))}
        </span>
      </button>
      {open ? (
        <div className="grid gap-4 px-5 pb-5 pl-12 lg:grid-cols-3">
          <Column title="Expected">
            <p className="text-[13px] leading-5 whitespace-pre-wrap">{toText(item.expected_output) || "—"}</p>
          </Column>
          <Column title={`Baseline${item.base_latency_ms ? ` · ${formatDuration(item.base_latency_ms)}` : ""}`}>
            <p className="text-[13px] leading-5 whitespace-pre-wrap">{base || "—"}</p>
          </Column>
          <Column title={`This run${item.head_latency_ms ? ` · ${formatDuration(item.head_latency_ms)}` : ""}`}>
            {item.base_output !== null && item.head_output !== null ? <DiffText before={base} after={head} /> : <p className="text-[13px] whitespace-pre-wrap">{head || "—"}</p>}
          </Column>
          {item.score_deltas.length ? (
            <div className="lg:col-span-3">
              <table className="w-full max-w-md text-[12px] tabular-nums">
                <thead>
                  <tr className="text-muted-foreground">
                    <th className="py-1 text-left font-medium">Scorer</th>
                    <th className="py-1 text-right font-medium">Baseline</th>
                    <th className="py-1 text-right font-medium">This run</th>
                    <th className="py-1 text-right font-medium">Change</th>
                  </tr>
                </thead>
                <tbody>
                  {item.score_deltas.map((d) => (
                    <tr key={d.scorer} className="border-t border-border/60">
                      <td className="py-1">{d.scorer}</td>
                      <td className="py-1 text-right">{d.base?.toFixed(3) ?? "-"}</td>
                      <td className="py-1 text-right">{d.head?.toFixed(3) ?? "-"}</td>
                      <td className={cn("py-1 text-right", (d.delta ?? 0) < 0 ? "text-destructive" : (d.delta ?? 0) > 0 ? "text-success" : "")}>
                        {d.delta === null ? "-" : `${d.delta > 0 ? "+" : ""}${d.delta.toFixed(3)}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  )
}

export function DiffList({ items }: { items: ItemDiff[] }) {
  return (
    <ul>
      {items.map((item, index) => (
        <DiffRow key={item.item_key} item={item} defaultOpen={index === 0 && item.status === "regressed"} />
      ))}
    </ul>
  )
}
