import type { ChatMessage, MessagePart } from "@/lib/api/schemas"
import { toText } from "@/lib/format"
import { cn } from "@/lib/utils"

function Part({ part }: { part: MessagePart }) {
  switch (part.type) {
    case "text":
      return <p className="text-[13px] leading-5 whitespace-pre-wrap">{part.content}</p>
    case "tool_call":
      return (
        <div className="rounded-md bg-chart-4/10 px-2.5 py-1.5 text-[12px]">
          <div className="font-medium">
            Calls <span className="font-mono">{part.name}</span>
          </div>
          <pre className="mt-1 font-mono text-[11px] whitespace-pre-wrap text-muted-foreground">{toText(part.arguments)}</pre>
        </div>
      )
    case "tool_call_response":
      return (
        <div className="rounded-md bg-secondary px-2.5 py-1.5 text-[12px] dark:bg-accent/40">
          <div className="font-medium text-muted-foreground">Tool result</div>
          <pre className="mt-1 max-h-40 overflow-auto font-mono text-[11px] whitespace-pre-wrap">{toText(part.response)}</pre>
        </div>
      )
    default:
      return <pre className="font-mono text-[11px] whitespace-pre-wrap text-muted-foreground">{part.content ?? part.type}</pre>
  }
}

const ROLE_LABEL: Record<string, string> = { user: "User", assistant: "Assistant", system: "System", tool: "Tool" }

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <ol className="space-y-2">
      {messages.map((message, index) => (
        <li
          key={index}
          className={cn(
            "rounded-lg px-3 py-2",
            message.role === "assistant" ? "bg-primary/8 dark:bg-primary/15" : "bg-secondary dark:bg-accent/30"
          )}
        >
          <div className="mb-1 flex items-center justify-between text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            <span>{ROLE_LABEL[message.role] ?? message.role}</span>
            {message.finish_reason ? <span className="normal-case">{message.finish_reason}</span> : null}
          </div>
          <div className="space-y-1.5">
            {message.parts.map((part, i) => (
              <Part key={i} part={part} />
            ))}
          </div>
        </li>
      ))}
    </ol>
  )
}
