import { useMemo } from "react"

import { wordDiff } from "@/lib/word-diff"

export function DiffText({ before, after }: { before: string; after: string }) {
  const ops = useMemo(() => wordDiff(before, after), [before, after])
  return (
    <p className="text-[13px] leading-5 whitespace-pre-wrap">
      {ops.map((op, index) =>
        op.kind === "same" ? (
          <span key={index}>{op.text}</span>
        ) : op.kind === "added" ? (
          <ins key={index} className="rounded-[3px] bg-success/20 no-underline decoration-success">
            {op.text}
          </ins>
        ) : (
          <del key={index} className="rounded-[3px] bg-destructive/15 text-muted-foreground decoration-destructive/60">
            {op.text}
          </del>
        )
      )}
    </p>
  )
}
