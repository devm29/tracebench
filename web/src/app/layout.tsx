import type { Metadata, Viewport } from "next"
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google"
import type { ReactNode } from "react"

import { AppSidebar } from "@/components/app-sidebar"
import { Providers } from "@/components/providers"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

import "./globals.css"

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-sans",
  display: "swap",
})
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-plex-mono", display: "swap" })

export const metadata: Metadata = {
  title: { default: "Tracebench", template: "%s · Tracebench" },
  description: "OpenTelemetry-native observability and regression testing for LLM apps.",
}

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbf9f4" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1418" },
  ],
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <body>
        <Providers>
          <SidebarProvider>
            <AppSidebar />
            <SidebarInset className="min-w-0 bg-background">{children}</SidebarInset>
          </SidebarProvider>
        </Providers>
      </body>
    </html>
  )
}
