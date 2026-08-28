"use client"

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: ReadonlyArray<{ value: T; label: string }>
  onChange: (value: T) => void
  label: string
}) {
  return (
    <Tabs
      value={value}
      onValueChange={(next) => {
        const match = options.find((o) => o.value === next)
        if (match) onChange(match.value)
      }}
    >
      <TabsList aria-label={label} className="h-8 rounded-lg bg-secondary p-0.5">
        {options.map((option) => (
          <TabsTrigger
            key={option.value}
            value={option.value}
            className="h-7 rounded-md px-3 text-[13px] data-[state=active]:bg-background data-[state=active]:shadow-sm"
          >
            {option.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}
