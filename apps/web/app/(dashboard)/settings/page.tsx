import { Settings } from "lucide-react"
import type { Metadata } from "next"
import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/ui/empty-state"

export const metadata: Metadata = { title: "settings" }

export default function SettingsPage() {
  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="settings" description="platform configuration and access control" />
      <EmptyState
        icon={Settings}
        title="nothing configurable yet"
        description="detection thresholds, retention and notification routing land here"
      />
    </section>
  )
}
