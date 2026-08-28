"use client"

import { useSyncExternalStore } from "react"

export function useMediaQuery(query: string, serverFallback = true): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query)
      list.addEventListener("change", onChange)
      return () => list.removeEventListener("change", onChange)
    },
    () => window.matchMedia(query).matches,
    () => serverFallback
  )
}
