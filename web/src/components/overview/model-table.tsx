import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ModelLatency } from "@/lib/api/schemas"
import { formatCost, formatDuration, formatNumber, formatPercent, formatTokens } from "@/lib/format"

export function ModelTable({ rows }: { rows: ModelLatency[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="pl-5 text-[12px]">Model</TableHead>
          <TableHead className="text-right text-[12px]">Calls</TableHead>
          <TableHead className="text-right text-[12px]">p50</TableHead>
          <TableHead className="text-right text-[12px]">p95</TableHead>
          <TableHead className="text-right text-[12px]">Error rate</TableHead>
          <TableHead className="text-right text-[12px]">Tokens in / out</TableHead>
          <TableHead className="pr-5 text-right text-[12px]">Spend</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.model} className="h-11 hover:bg-accent/50">
            <TableCell className="pl-5 font-medium">{row.model}</TableCell>
            <TableCell className="text-right tabular-nums">{formatNumber(row.calls)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatDuration(row.p50_ms)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatDuration(row.p95_ms)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatPercent(row.calls ? row.errors / row.calls : 0)}</TableCell>
            <TableCell className="text-right text-muted-foreground tabular-nums">
              {formatTokens(row.input_tokens)} / {formatTokens(row.output_tokens)}
            </TableCell>
            <TableCell className="pr-5 text-right font-medium tabular-nums">{formatCost(row.cost_usd)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
