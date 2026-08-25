"use client"

import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useCallback } from "react"

export function useUrlState<T extends string>(key: string, fallback: T, allowed?: readonly T[]) {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const raw = params.get(key)
  const value = (raw !== null && (!allowed || (allowed as readonly string[]).includes(raw)) ? raw : fallback) as T

  const setValue = useCallback(
    (next: T | undefined) => {
      const updated = new URLSearchParams(params.toString())
      if (next === undefined || next === fallback) updated.delete(key)
      else updated.set(key, next)
      const query = updated.toString()
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false })
    },
    [fallback, key, params, pathname, router]
  )
  return [value, setValue] as const
}
