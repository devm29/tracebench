"use client"

import type { ReactNode } from "react"

import { CodeBlock } from "@/components/code-block"
import { Badge } from "@/components/ui/badge"
import type { SpanNode } from "@/lib/api/schemas"
import { formatCost, formatDuration, formatTime, formatTokens } from "@/lib/format"

import { MessageList } from "./messages"
import { categorize } from "./span-kind"

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{title}</h3>
      {children}
    </section>
  )
}

function Rows({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl className="divide-y divide-border/60 rounded-xl bg-card ring-1 ring-border/60">
      {rows.map(([label, value]) => (
        <div key={label} className="flex min-h-9 items-center justify-between gap-4 px-3 py-1.5 text-[13px]">
          <dt className="shrink-0 text-muted-foreground">{label}</dt>
          <dd className="min-w-0 truncate text-right tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function SpanInspector({ span }: { span: SpanNode }) {
  const category = categorize(span)
  const isLlm = category.key === "llm"
  const usage = span.usage
  const extraAttributes = Object.entries(span.attributes)

  return (
    <div className="space-y-6">
      <div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary">{category.label}</Badge>
          {span.status === "error" ? <Badge variant="destructive">{span.error_type || "Error"}</Badge> : null}
          {span.provider ? <Badge variant="outline">{span.provider}</Badge> : null}
        </div>
        <h2 className="mt-2 text-[17px] leading-[22px] font-semibold break-words">{span.name}</h2>
        <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{span.span_id}</p>
        {span.status_message ? <p className="mt-2 text-[13px] text-destructive">{span.status_message}</p> : null}
      </div>

      <Section title="Timing">
        <Rows
          rows={[
            ["Duration", formatDuration(span.duration_ms)],
            ["Starts at", `+${formatDuration(span.offset_ms)}`],
            ["Started", formatTime(span.start_time)],
            ["Service", span.service_name],
          ]}
        />
      </Section>

      {isLlm || usage.input_tokens + usage.output_tokens > 0 ? (
        <Section title="Model and cost">
          <Rows
            rows={[
              ["Model", span.model || "unknown"],
              ["Input tokens", formatTokens(usage.input_tokens)],
              ["Cached input", formatTokens(usage.cache_read_tokens)],
              ["Output tokens", formatTokens(usage.output_tokens)],
              [
                "Cost",
                span.price_version ? (
                  <span>
                    {formatCost(span.cost_usd)} <span className="text-muted-foreground">· prices v{span.price_version}</span>
                  </span>
                ) : (
                  <span className="text-muted-foreground">No price for this model</span>
                ),
              ],
              ...(span.finish_reasons.length ? [["Finish reason", span.finish_reasons.join(", ")] as [string, ReactNode]] : []),
            ]}
          />
        </Section>
      ) : null}

      {span.children.length > 0 ? (
        <Section title="Including children">
          <Rows
            rows={[
              ["Spans", span.subtree.span_count],
              ["LLM calls", span.subtree.llm_calls],
              ["Tool calls", span.subtree.tool_calls],
              ["Tokens", formatTokens(span.subtree.input_tokens + span.subtree.output_tokens)],
              ["Cost", formatCost(span.subtree.cost_usd)],
            ]}
          />
        </Section>
      ) : null}

      {span.tool ? (
        <Section title={`Tool · ${span.tool.name}`}>
          <div className="space-y-2">
            <div className="text-[12px] text-muted-foreground">Arguments</div>
            <CodeBlock value={span.tool.arguments} />
            <div className="text-[12px] text-muted-foreground">Result</div>
            <CodeBlock value={span.tool.result ?? (span.status === "error" ? span.status_message : null)} />
          </div>
        </Section>
      ) : null}

      {span.system_instructions ? (
        <Section title="System instructions">
          <MessageList
            messages={[
              {
                role: "system",
                parts: [{ type: "text", content: systemText(span.system_instructions) }],
              },
            ]}
          />
        </Section>
      ) : null}
      {span.input_messages.length ? (
        <Section title="Input">
          <MessageList messages={span.input_messages} />
        </Section>
      ) : null}
      {span.output_messages.length ? (
        <Section title="Output">
          <MessageList messages={span.output_messages} />
        </Section>
      ) : null}

      {span.events.length ? (
        <Section title="Events">
          <ul className="space-y-2">
            {span.events.map((event, index) => (
              <li key={index} className="rounded-lg bg-secondary px-3 py-2 text-[12px] dark:bg-accent/30">
                <div className="flex justify-between font-medium">
                  <span>{event.name}</span>
                  <span className="text-muted-foreground tabular-nums">+{formatDuration(event.offset_ms)}</span>
                </div>
                {Object.keys(event.attributes).length ? <CodeBlock value={event.attributes} className="mt-1 bg-transparent px-0" /> : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {extraAttributes.length ? (
        <Section title="Attributes">
          <Rows rows={extraAttributes.map(([key, value]) => [key, <span key={key} className="font-mono text-[12px]">{value}</span>])} />
        </Section>
      ) : null}
    </div>
  )
}

function systemText(raw: string): string {
  try {
    const parsed: unknown = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      return parsed
        .map((part: unknown) =>
          part && typeof part === "object" && "content" in part ? String((part as { content: unknown }).content) : ""
        )
        .join("\n")
    }
  } catch {
    return raw
  }
  return raw
}
