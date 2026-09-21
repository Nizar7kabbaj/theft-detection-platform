"use client"
import { Compass } from "lucide-react"
import Link from "next/link"
import { buttonVariants } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"

export default function RootNotFound() {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-background p-6">
      <div className="flex w-full max-w-lg">
        <EmptyState
          description="this address does not match any page."
          icon={Compass}
          title="page not found"
        >
          <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">
            error 404
          </p>
          <Link className={`mt-2 ${buttonVariants({ size: "sm" })}`} href="/dashboard">
            go to the console
          </Link>
        </EmptyState>
      </div>
    </main>
  )
}
