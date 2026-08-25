import { cn } from "@/lib/utils"
import { toText } from "@/lib/format"

export function CodeBlock({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre
      className={cn(
        "max-h-80 overflow-auto rounded-lg bg-secondary px-3 py-2 font-mono text-[12px] leading-[18px] whitespace-pre-wrap break-words",
        className
      )}
    >
      {toText(value) || <span className="text-muted-foreground">empty</span>}
    </pre>
  )
}
