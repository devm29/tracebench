import { Compass } from "lucide-react"
import Link from "next/link"

import { EmptyState } from "@/components/states"
import { Button } from "@/components/ui/button"

export default function NotFound() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-16">
      <EmptyState
        icon={Compass}
        title="Page not found"
        description="The page you're looking for doesn't exist or has moved."
        action={
          <Button asChild>
            <Link href="/">Go to overview</Link>
          </Button>
        }
      />
    </main>
  )
}
