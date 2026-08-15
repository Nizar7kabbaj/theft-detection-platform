import { Clock } from "lucide-react"
import type { Metadata } from "next"
import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/ui/empty-state"

export const metadata: Metadata = { title: "history" }

export default function HistoryPage() {
  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="history" description="past alerts and the decisions taken on them" />
      <EmptyState
        icon={Clock}
        title="no history"
        description="reviewed alerts are recorded here with the reviewer and the outcome"
      />
    </section>
  )
}
