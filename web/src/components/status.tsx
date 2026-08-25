import { CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react"

import { Badge } from "@/components/ui/badge"

export function StatusDot({ error, label }: { error: boolean; label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px]">
      <span className={error ? "size-2 rounded-full bg-destructive" : "size-2 rounded-full bg-success"} aria-hidden />
      <span className={label ? "" : "sr-only"}>{label ?? (error ? "Error" : "OK")}</span>
    </span>
  )
}

export function RunStatusBadge({ status }: { status: "pending" | "running" | "completed" | "failed" }) {
  switch (status) {
    case "completed":
      return (
        <Badge variant="secondary">
          <CheckCircle2 aria-hidden />
          Completed
        </Badge>
      )
    case "failed":
      return (
        <Badge variant="destructive">
          <XCircle aria-hidden />
          Failed
        </Badge>
      )
    case "running":
      return (
        <Badge variant="info">
          <Loader2 className="animate-spin" aria-hidden />
          Running
        </Badge>
      )
    case "pending":
      return (
        <Badge variant="secondary">
          <CircleDashed aria-hidden />
          Queued
        </Badge>
      )
  }
}

/** The verdict the CLI recorded for this run, using its own gate policy. */
export function GateBadge({ passed }: { passed: boolean }) {
  return passed ? (
    <Badge variant="success">
      <CheckCircle2 aria-hidden />
      CI gate passed
    </Badge>
  ) : (
    <Badge variant="destructive">
      <XCircle aria-hidden />
      CI gate failed
    </Badge>
  )
}
