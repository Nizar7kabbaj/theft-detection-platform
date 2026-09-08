import type { Metadata } from "next"
import { cookies } from "next/headers"
import { redirect } from "next/navigation"
import { PageHeader } from "@/components/layout/page-header"
import { AbsentPanel } from "@/features/alerts/components/absent-panel"
import { fetchIdentity } from "@/features/auth/api/identity-server"
import type { Identity } from "@/features/auth/schemas/identity"
import { POLICY_SECTION_COOKIE_NAME, parseStoredSection } from "@/features/policy/api/policy-cookie"
import { fetchPolicy, fetchPolicyHistory } from "@/features/policy/api/policy-server"
import { PolicyConsole } from "@/features/policy/components/policy-console"
import { PolicyHistory } from "@/features/policy/components/policy-history"
import { PolicyState } from "@/features/policy/components/policy-state"
import { isApiError } from "@/lib/api/errors"

export const metadata: Metadata = { title: "settings" }
export const dynamic = "force-dynamic"

const DESCRIPTION = "what the detector counts as theft"

export default async function SettingsPage() {
  let identity: Identity
  try {
    identity = await fetchIdentity()
  } catch (error) {
    if (isApiError(error) && error.status === 401) {
      redirect("/login?reason=session_ended")
    }
    throw error
  }
  const permissions = new Set(identity.permissions)
  if (!permissions.has("settings:read")) {
    return (
      <section className="flex flex-1 flex-col gap-5">
        <PageHeader title="detection policy" description={DESCRIPTION} />
        <AbsentPanel
          title="detection policy"
          reason="reading detection policy requires the operator role"
        />
      </section>
    )
  }
  const [policy, revisions, jar] = await Promise.all([
    fetchPolicy(),
    fetchPolicyHistory(),
    cookies(),
  ])
  const section = parseStoredSection(jar.get(POLICY_SECTION_COOKIE_NAME)?.value)
  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="detection policy" description={DESCRIPTION} />
      <PolicyState
        version={policy.version}
        changedBy={policy.changed_by}
        changedAt={policy.changed_at}
        runtime={policy.runtime}
        renderedAt={Date.now()}
      />
      <PolicyConsole
        version={policy.version}
        saved={policy.policy}
        canWrite={permissions.has("settings:write")}
        history={<PolicyHistory revisions={revisions} />}
        initialSection={section}
      />
    </section>
  )
}
