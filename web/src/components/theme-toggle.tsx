"use client"

import { Monitor, Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { useEffect, useState } from "react"

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"

const OPTIONS = [
  { value: "light", label: "Light appearance", icon: Sun },
  { value: "dark", label: "Dark appearance", icon: Moon },
  { value: "system", label: "Match system appearance", icon: Monitor },
] as const

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  return (
    <ToggleGroup
      type="single"
      value={mounted ? (theme ?? "system") : "system"}
      onValueChange={(value) => value && setTheme(value)}
      className="h-8 w-full rounded-lg bg-secondary p-0.5 group-data-[collapsible=icon]:hidden"
      aria-label="Appearance"
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <ToggleGroupItem
          key={value}
          value={value}
          aria-label={label}
          className="h-7 flex-1 rounded-md data-[state=on]:bg-background data-[state=on]:shadow-sm"
        >
          <Icon className="size-3.5" strokeWidth={1.75} />
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}
