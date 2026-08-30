import { Badge } from "@/components/ui/badge"
import type { ScorerSpec } from "@/lib/api/schemas"

export function scorerLabel(spec: ScorerSpec): string {
  switch (spec.type) {
    case "exact_match":
      return "Exact match"
    case "json_schema":
      return "JSON schema"
    case "embedding_similarity":
      return `Similarity ≥ ${spec.threshold}`
    case "llm_judge":
      return `LLM judge ≥ ${spec.threshold}`
  }
}

export function ScorerBadges({ scorers }: { scorers: ScorerSpec[] }) {
  if (scorers.length === 0) return <span className="text-[12px] text-muted-foreground">Default scorers</span>
  return (
    <div className="flex flex-wrap gap-1">
      {scorers.map((spec, index) => (
        <Badge key={index} variant="secondary" className="font-normal">
          {scorerLabel(spec)}
        </Badge>
      ))}
    </div>
  )
}
