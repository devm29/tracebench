import { Bot, Database, MessageSquare, Search, Workflow, Wrench, type LucideIcon } from "lucide-react"

import type { SpanNode } from "@/lib/api/schemas"

export interface SpanCategory {
  key: "agent" | "llm" | "tool" | "retrieval" | "other"
  label: string
  bar: string
  /** Text color for labels drawn on top of the bar; light bars need dark text for 4.5:1 contrast. */
  barText: string
  icon: LucideIcon
}

const ON_LIGHT = "text-neutral-950"

const AGENT: SpanCategory = { key: "agent", label: "Agent", bar: "bg-chart-3", barText: "text-white", icon: Bot }
const LLM: SpanCategory = { key: "llm", label: "LLM call", bar: "bg-chart-1", barText: ON_LIGHT, icon: MessageSquare }
const TOOL: SpanCategory = { key: "tool", label: "Tool", bar: "bg-chart-4", barText: ON_LIGHT, icon: Wrench }
const RETRIEVAL: SpanCategory = { key: "retrieval", label: "Retrieval", bar: "bg-chart-2", barText: ON_LIGHT, icon: Search }
const OTHER: SpanCategory = {
  key: "other",
  label: "Other",
  bar: "bg-muted-foreground/40",
  barText: "text-foreground",
  icon: Database,
}

export const CATEGORIES = [AGENT, LLM, TOOL, RETRIEVAL, OTHER] as const

export function categorize(span: Pick<SpanNode, "operation" | "tool">): SpanCategory {
  switch (span.operation) {
    case "invoke_agent":
    case "create_agent":
      return AGENT
    case "invoke_workflow":
      return { ...AGENT, icon: Workflow }
    case "chat":
    case "text_completion":
    case "generate_content":
      return LLM
    case "execute_tool":
      return TOOL
    case "embeddings":
    case "retrieval":
      return RETRIEVAL
    default:
      return span.tool ? TOOL : OTHER
  }
}
