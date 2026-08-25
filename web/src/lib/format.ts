const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 })
const integer = new Intl.NumberFormat("en-US")
const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 })

export function formatNumber(value: number): string {
  return Math.abs(value) >= 10_000 ? compact.format(value) : integer.format(Math.round(value))
}

export function formatTokens(value: number): string {
  return compact.format(value)
}

export function formatPercent(value: number): string {
  return percent.format(value)
}

export function formatCost(value: number): string {
  if (value === 0) return "$0.00"
  if (value < 0.0001) return "<$0.0001"
  const digits = value < 0.01 ? 4 : value < 1 ? 3 : 2
  return `$${value.toFixed(digits)}`
}

export function formatDuration(ms: number): string {
  if (ms < 1) return "<1 ms"
  if (ms < 1000) return `${Math.round(ms)} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`
  const minutes = Math.floor(ms / 60_000)
  return `${minutes}m ${Math.round((ms % 60_000) / 1000)}s`
}

const relative = new Intl.RelativeTimeFormat("en-US", { numeric: "auto" })

export function formatRelative(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000)
  const abs = Math.abs(seconds)
  if (abs < 60) return relative.format(seconds, "second")
  if (abs < 3600) return relative.format(Math.round(seconds / 60), "minute")
  if (abs < 86_400) return relative.format(Math.round(seconds / 3600), "hour")
  return relative.format(Math.round(seconds / 86_400), "day")
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" })
}

export function shortId(id: string, length = 8): string {
  return id.slice(0, length)
}

export function delta(current: number, previous: number): number | null {
  if (!previous) return null
  return (current - previous) / previous
}

export function toText(value: unknown): string {
  if (value === null || value === undefined) return ""
  if (typeof value === "string") return value
  return JSON.stringify(value, null, 2)
}

export function lastUserMessage(input: unknown): string {
  if (input && typeof input === "object" && "messages" in input) {
    const messages = (input as { messages: unknown }).messages
    if (Array.isArray(messages)) {
      for (let i = messages.length - 1; i >= 0; i -= 1) {
        const message: unknown = messages[i]
        if (message && typeof message === "object" && "content" in message) {
          const content = (message as { content: unknown }).content
          if (typeof content === "string") return content
        }
      }
    }
  }
  return toText(input)
}
