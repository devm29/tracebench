import type { Metadata, Viewport } from "next"
import { Inter } from "next/font/google"
import type { ReactNode } from "react"

import { AppSidebar } from "@/components/app-sidebar"
import { Providers } from "@/components/providers"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

import "./globals.css"

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" })

export const metadata: Metadata = {
  title: { default: "Tracebench", template: "%s · Tracebench" },
  description: "OpenTelemetry-native observability and regression testing for LLM apps.",
}

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#000000" },
  ],
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body>
        <Providers>
          <SidebarProvider>
            <AppSidebar />
            <SidebarInset className="min-w-0 bg-secondary/60 dark:bg-background">{children}</SidebarInset>
          </SidebarProvider>
        </Providers>
      </body>
    </html>
  )
}
