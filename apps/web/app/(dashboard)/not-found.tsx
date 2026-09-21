"use client"
import { Compass } from "lucide-react"
import Link from "next/link"
import { buttonVariants } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"

export default function DashboardNotFound() {
  return (
    <section className="flex flex-1 flex-col">
      <EmptyState
        description="this address does not match any page in the console. it may be mistyped, or the item it pointed to was deleted."
        icon={Compass}
        title="page not found"
      >
        <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">
          error 404
        </p>
        <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
          <Link className={buttonVariants({ size: "sm" })} href="/dashboard">
            back to dashboard
          </Link>
          <Link className={buttonVariants({ size: "sm", variant: "outline" })} href="/alerts">
            open alerts
          </Link>
        </div>
      </EmptyState>
    </section>
  )
}
