import { AlertTriangle, type LucideIcon } from "lucide-react"
import type { ReactNode } from "react"

import { Skeleton } from "@/components/ui/skeleton"

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <Icon className="size-10 text-muted-foreground/70" strokeWidth={1.5} aria-hidden />
      <h2 className="mt-4 text-[17px] leading-[22px] font-semibold">{title}</h2>
      <p className="mt-1 max-w-sm text-[13px] leading-[18px] text-muted-foreground">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong."
  return (
    <div role="alert" className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <AlertTriangle className="size-10 text-warning" strokeWidth={1.5} aria-hidden />
      <h2 className="mt-4 text-[17px] font-semibold">Couldn&apos;t load this</h2>
      <p className="mt-1 max-w-md text-[13px] text-muted-foreground">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-md px-2 py-1 text-[13px] font-medium text-primary outline-none hover:underline focus-visible:ring-4 focus-visible:ring-ring"
        >
          Try again
        </button>
      ) : null}
    </div>
  )
}

export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-4" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-9 w-full rounded-md" />
      ))}
    </div>
  )
}
