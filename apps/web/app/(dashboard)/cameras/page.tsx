import { Video } from "lucide-react"
import type { Metadata } from "next"
import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/ui/empty-state"

export const metadata: Metadata = { title: "cameras" }
export const dynamic = "force-dynamic"

export default function CamerasPage() {
  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="cameras" description="registered capture sources and their state" />
      <EmptyState
        icon={Video}
        title="no cameras registered"
        description="capture sources appear here once a camera reports in"
      />
    </section>
  )
}
