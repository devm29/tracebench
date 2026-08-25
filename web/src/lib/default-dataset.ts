import type { Dataset } from "@/lib/api/schemas"

/**
 * The dataset a promoted trace most likely belongs to: one named after the trace's service
 * (support-agent -> support-agent-golden), otherwise the first listed.
 */
export function defaultDatasetFor(datasets: readonly Dataset[] | undefined, serviceName: string): Dataset | undefined {
  if (!datasets?.length) return undefined
  const service = serviceName.trim().toLowerCase()
  const named = service ? datasets.find((d) => d.name === service || d.name.startsWith(`${service}-`)) : undefined
  return named ?? datasets[0]
}
