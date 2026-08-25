"use client"

import { Activity, Database, FlaskConical, Gauge, Receipt } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { ThemeToggle } from "@/components/theme-toggle"

const OBSERVE = [
  { href: "/", label: "Overview", icon: Gauge },
  { href: "/traces", label: "Traces", icon: Activity },
] as const

const TEST = [
  { href: "/datasets", label: "Datasets", icon: Database },
  { href: "/evals", label: "Eval runs", icon: FlaskConical },
] as const

const SETTINGS = [{ href: "/prices", label: "Model prices", icon: Receipt }] as const

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`)
}

function NavGroup({ label, items }: { label: string; items: ReadonlyArray<{ href: string; label: string; icon: typeof Gauge }> }) {
  const pathname = usePathname()
  return (
    <SidebarGroup>
      <SidebarGroupLabel className="text-[11px] font-medium tracking-wide uppercase">{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map(({ href, label: text, icon: Icon }) => (
            <SidebarMenuItem key={href}>
              <SidebarMenuButton
                asChild
                isActive={isActive(pathname, href)}
                className="h-8 text-[13px] data-[active=true]:font-medium"
                tooltip={text}
              >
                <Link href={href}>
                  <Icon strokeWidth={1.75} />
                  <span>{text}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}

export function AppSidebar() {
  return (
    <Sidebar collapsible="icon" className="material border-r border-border/60">
      <SidebarHeader className="px-3 pt-4 pb-2">
        <Link href="/" className="flex items-center gap-2 rounded-md px-1 py-1 outline-none focus-visible:ring-4 focus-visible:ring-ring">
          <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground">
            <Activity className="size-4" strokeWidth={2} />
          </span>
          <span className="text-[15px] font-semibold tracking-tight group-data-[collapsible=icon]:hidden">Tracebench</span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <NavGroup label="Observe" items={OBSERVE} />
        <NavGroup label="Test" items={TEST} />
        <NavGroup label="Settings" items={SETTINGS} />
      </SidebarContent>
      <SidebarFooter className="px-3 pb-3">
        <ThemeToggle />
      </SidebarFooter>
    </Sidebar>
  )
}
