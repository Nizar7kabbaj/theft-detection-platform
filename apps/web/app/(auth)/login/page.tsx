import type { Metadata } from "next"
import { Suspense } from "react"
import { LoginForm } from "@/features/auth/components/login-form"

export const metadata: Metadata = {
  title: "sign in",
}

export const dynamic = "force-dynamic"

export default function LoginPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">sign in</h1>
        <p className="text-sm text-muted-foreground">operator access to the alert console</p>
      </div>
      <Suspense fallback={<div className="min-h-64" />}>
        <LoginForm />
      </Suspense>
    </div>
  )
}
