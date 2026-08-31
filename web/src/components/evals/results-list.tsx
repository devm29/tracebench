"use client"

import { ChevronRight } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import type { CaseResult } from "@/lib/api/schemas"
import { formatDuration, lastUserMessage, toText } from "@/lib/format"
import { cn } from "@/lib/utils"

import { DiffText } from "./diff-text"

function ResultRow({ result }: { result: CaseResult }) {
  const [open, setOpen] = useState(false)
  const output = result.error ?? toText(result.output)
  return (
    <li className="border-b border-border/60 last:border-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-5 py-3 text-left outline-none hover:bg-accent/40 focus-visible:bg-accent/40"
      >
        <ChevronRight className={cn("size-4 shrink-0 text-muted-foreground transition-transform duration-150", open && "rotate-90")} aria-hidden />
        <Badge variant={result.error ? "warning" : result.passed ? "success" : "destructive"} className="w-16 justify-center">
          {result.error ? "Error" : result.passed ? "Pass" : "Fail"}
        </Badge>
        <span className="min-w-0 flex-1 truncate text-[13px]">{lastUserMessage(result.input)}</span>
        <span className="text-[12px] text-muted-foreground tabular-nums">
          {result.latency_ms !== null ? formatDuration(result.latency_ms) : ""}
        </span>
      </button>
      {open ? (
        <div className="space-y-4 px-5 pb-5 pl-12">
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-1.5">
              <div className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Expected</div>
              <p className="rounded-lg bg-secondary px-3 py-2 text-[13px] whitespace-pre-wrap dark:bg-accent/30">
                {toText(result.expected_output) || "—"}
              </p>
            </div>
            <div className="space-y-1.5">
              <div className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Output vs expected</div>
              <div className="rounded-lg bg-secondary px-3 py-2 dark:bg-accent/30">
                {result.error || result.expected_output === null ? (
                  <p className="text-[13px] whitespace-pre-wrap">{output}</p>
                ) : (
                  <DiffText before={toText(result.expected_output)} after={output} />
                )}
              </div>
            </div>
          </div>
          <ul className="space-y-1 text-[12px]">
            {result.scores.map((score) => (
              <li key={score.scorer} className="flex flex-wrap items-baseline gap-2">
                <span className={score.passed ? "text-success" : "text-destructive"}>{score.passed ? "Passed" : "Failed"}</span>
                <span className="font-medium">{score.scorer}</span>
                <span className="tabular-nums">{score.value.toFixed(3)}</span>
                {score.detail ? <span className="text-muted-foreground">{score.detail}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </li>
  )
}

export function ResultsList({ results }: { results: CaseResult[] }) {
  const ordered = [...results].sort((a, b) => Number(a.passed) - Number(b.passed))
  return (
    <ul>
      {ordered.map((result) => (
        <ResultRow key={result.item_key} result={result} />
      ))}
    </ul>
  )
}
