import type { Metadata } from "next"
import { fetchAlertDetail } from "@/features/alerts/api/alerts-server"
import { AbsentPanel } from "@/features/alerts/components/absent-panel"
import { DecisionControls } from "@/features/alerts/components/decision-controls"
import { DetailHeader } from "@/features/alerts/components/detail-header"
import { EvidencePanel } from "@/features/alerts/components/evidence-panel"
import { PoseOverlay } from "@/features/alerts/components/pose-overlay"
import { VerdictPanel } from "@/features/alerts/components/verdict-panel"
import { fetchIdentity } from "@/features/auth/api/identity-server"

export const metadata: Metadata = { title: "alert" }
export const dynamic = "force-dynamic"

export default async function AlertDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const [alert, identity] = await Promise.all([fetchAlertDetail(id), fetchIdentity()])
  const canDecide = identity.permissions.includes("alert:acknowledge")

  return (
    <section className="flex flex-1 flex-col gap-6">
      <DetailHeader alert={alert} />
      <PoseOverlay alert={alert} />
      <div className="grid gap-4 lg:grid-cols-2">
        <EvidencePanel concealment={alert.concealment} />
        <VerdictPanel score={alert.classifier_score} state={alert.classifier_state} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <AbsentPanel title="zone" reason="the pipeline records no zone for a detection yet" />
        <AbsentPanel
          title="incident timeline"
          reason="alerts are stored one at a time, with nothing linking them into an incident"
        />
        <AbsentPanel
          title="precedent"
          reason="no lookup exists for earlier alerts on this person or object"
        />
        <AbsentPanel
          title="scene description"
          reason="the vision language judge is not wired into the pipeline"
        />
      </div>
      {canDecide ? <DecisionControls alert={alert} /> : null}
    </section>
  )
}
