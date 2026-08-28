"use client"

import { useEffect, useRef, useSyncExternalStore, type ReactNode } from "react"

import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { cn } from "@/lib/utils"

// Large-title pattern: while a page's large title is on screen the toolbar title stays hidden,
// and it fades in once the large title scrolls under the toolbar.
let largeTitleOnScreen = false
const listeners = new Set<() => void>()

function setLargeTitleOnScreen(visible: boolean) {
  if (largeTitleOnScreen === visible) return
  largeTitleOnScreen = visible
  listeners.forEach((notify) => notify())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

const TOOLBAR_HEIGHT = 52

export function Toolbar({ title, children }: { title: ReactNode; children?: ReactNode }) {
  const hideTitle = useSyncExternalStore(
    subscribe,
    () => largeTitleOnScreen,
    () => false
  )
  return (
    <header className="material sticky top-0 z-30 flex h-13 items-center gap-2 border-b border-border/60 bg-background/72 px-4 backdrop-blur-xl backdrop-saturate-[1.8]">
      <SidebarTrigger className="-ml-1 size-8" aria-label="Toggle sidebar" />
      <Separator orientation="vertical" className="mx-1 h-4!" />
      <div
        className={cn("min-w-0 truncate text-[15px] font-semibold transition-opacity duration-150 ease-out", hideTitle && "opacity-0")}
        aria-hidden={hideTitle || undefined}
      >
        {title}
      </div>
      {children ? <div className="ml-auto flex items-center gap-2">{children}</div> : null}
    </header>
  )
}

export function PageTitle({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    const node = heading.current
    if (!node || typeof IntersectionObserver === "undefined") return
    const observer = new IntersectionObserver(([entry]) => setLargeTitleOnScreen(entry?.isIntersecting ?? false), {
      rootMargin: `-${TOOLBAR_HEIGHT}px 0px 0px 0px`,
    })
    observer.observe(node)
    return () => {
      observer.disconnect()
      setLargeTitleOnScreen(false)
    }
  }, [])

  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 ref={heading} className="text-[28px] leading-[34px] font-semibold tracking-tight">
          {title}
        </h1>
        {subtitle ? <p className="mt-1 text-[13px] text-muted-foreground">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}
