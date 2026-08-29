"use client"

import { Segmented } from "@/components/segmented"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useFacets, type RangeKey } from "@/lib/api/hooks"

export const RANGES = ["1h", "24h", "7d", "30d"] as const satisfies readonly RangeKey[]

const RANGE_OPTIONS = RANGES.map((value) => ({ value, label: value.toUpperCase() }))

export const RANGE_LABEL: Record<RangeKey, string> = {
  "1h": "Last hour",
  "24h": "Last 24 hours",
  "7d": "Last 7 days",
  "30d": "Last 30 days",
}

const ALL = "__all__"

export function ServiceSelect({ value, onChange }: { value: string | undefined; onChange: (v: string | undefined) => void }) {
  const facets = useFacets()
  return (
    <Select value={value ?? ALL} onValueChange={(next) => onChange(next === ALL ? undefined : next)}>
      <SelectTrigger size="sm" className="h-8 min-w-40 rounded-lg text-[13px]" aria-label="Service">
        <SelectValue placeholder="All services" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>All services</SelectItem>
        {facets.data?.services.map((service) => (
          <SelectItem key={service} value={service}>
            {service}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function RangeControl({ value, onChange }: { value: RangeKey; onChange: (v: RangeKey) => void }) {
  return <Segmented label="Time range" value={value} options={RANGE_OPTIONS} onChange={onChange} />
}
