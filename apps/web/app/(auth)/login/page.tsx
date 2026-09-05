import type { Metadata } from "next"
import { Suspense } from "react"
import { LoginForm } from "@/features/auth/components/login-form"
import { SessionNotice } from "@/features/auth/components/session-notice"

export const metadata: Metadata = {
  title: "sign in",
}

export const dynamic = "force-dynamic"

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const params = await searchParams
  const raw = params.reason
  const reason = Array.isArray(raw) ? raw[0] : raw

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="font-semibold text-xl">sign in</h1>
        <p className="text-muted-foreground text-sm">operator access to the alert console</p>
      </div>
      <SessionNotice reason={reason} />
      <Suspense fallback={<div className="min-h-64" />}>
        <LoginForm />
      </Suspense>
    </div>
  )
}
