"use client"

import { Receipt } from "lucide-react"
import { useState } from "react"

import { PageTitle, Toolbar } from "@/components/page-header"
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states"
import { Badge } from "@/components/ui/badge"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { usePriceVersion, usePriceVersions } from "@/lib/api/hooks"
import { formatDate } from "@/lib/format"
import { cn } from "@/lib/utils"

function rate(value: number | null): string {
  return value === null ? "-" : `$${value.toFixed(value < 1 ? 3 : 2)}`
}

export function PricesView() {
  const versions = usePriceVersions()
  const now = Date.now()
  const active = versions.data?.find((v) => new Date(v.effective_from).getTime() <= now)
  const [chosen, setChosen] = useState<number>()
  const selectedId = chosen ?? active?.id
  const version = usePriceVersion(selectedId)

  return (
    <>
      <Toolbar title="Model prices" />
      <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        <PageTitle
          title="Model prices"
          subtitle="Spans are priced at ingest with the version in effect when they started, so history never changes"
        />
        {versions.isError ? (
          <Card>
            <ErrorState error={versions.error} onRetry={() => void versions.refetch()} />
          </Card>
        ) : (
          <div className="grid items-start gap-4 lg:grid-cols-[280px_1fr]">
            <Card className="gap-0 py-2">
              <h2 className="px-4 py-2 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Versions</h2>
              {versions.isPending ? (
                <TableSkeleton rows={3} />
              ) : (
                <ul className="px-2" role="listbox" aria-label="Price versions">
                  {versions.data.map((v) => (
                    <li key={v.id}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={v.id === selectedId}
                        onClick={() => setChosen(v.id)}
                        className={cn(
                          "w-full rounded-lg px-3 py-2 text-left outline-none transition-colors focus-visible:ring-4 focus-visible:ring-ring",
                          v.id === selectedId ? "bg-primary/10" : "hover:bg-accent/60"
                        )}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-[13px] font-medium">{v.label}</span>
                          {v.id === active?.id ? <Badge variant="success">Active</Badge> : null}
                        </div>
                        <div className="text-[12px] text-muted-foreground tabular-nums">
                          v{v.id} · from {formatDate(v.effective_from)} · {v.model_count} models
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card className="gap-2 pb-2">
              <CardHeader>
                <CardTitle>{version.data?.label ?? "Prices"}</CardTitle>
                <CardDescription>USD per million tokens. Prefix rules match dated model ids, longest prefix wins.</CardDescription>
              </CardHeader>
              {!version.data ? (
                versions.data?.length === 0 ? (
                  <EmptyState icon={Receipt} title="No prices yet" description="The API seeds list prices on first start." />
                ) : (
                  <TableSkeleton rows={6} />
                )
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-5 text-[12px]">Model</TableHead>
                      <TableHead className="text-[12px]">Provider</TableHead>
                      <TableHead className="text-right text-[12px]">Input</TableHead>
                      <TableHead className="text-right text-[12px]">Cached input</TableHead>
                      <TableHead className="text-right text-[12px]">Cache write</TableHead>
                      <TableHead className="pr-5 text-right text-[12px]">Output</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {version.data.prices.map((price) => (
                      <TableRow key={`${price.model}-${price.match}`} className="h-11 hover:bg-accent/50">
                        <TableCell className="pl-5">
                          <span className="font-medium">{price.model}</span>
                          {price.match === "prefix" ? <span className="ml-1 text-muted-foreground">*</span> : null}
                        </TableCell>
                        <TableCell className="text-[13px] text-muted-foreground">{price.provider}</TableCell>
                        <TableCell className="text-right tabular-nums">{rate(price.input_per_mtok)}</TableCell>
                        <TableCell className="text-right tabular-nums">{rate(price.cache_read_per_mtok)}</TableCell>
                        <TableCell className="text-right tabular-nums">{rate(price.cache_write_per_mtok)}</TableCell>
                        <TableCell className="pr-5 text-right tabular-nums">{rate(price.output_per_mtok)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </Card>
          </div>
        )}
      </main>
    </>
  )
}
