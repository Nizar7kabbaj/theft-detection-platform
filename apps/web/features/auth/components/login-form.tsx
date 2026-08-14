"use client"

import { useRouter, useSearchParams } from "next/navigation"
import { useActionState, useId } from "react"
import { Button } from "@/components/ui/button"
import { submitLogin } from "@/features/auth/api/login"
import { loginSchema } from "@/features/auth/schemas/login"
import { safeReturnPath } from "@/lib/auth/return-path"

type FormState = {
  message: string | null
  username: string
}

const EMPTY: FormState = { message: null, username: "" }

const FIELD_CLASS =
  "h-9 rounded-lg border border-input bg-background px-3 text-sm outline-none transition-all focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 disabled:pointer-events-none disabled:opacity-50"

function lockoutMessage(retryAfter: number | null): string {
  if (retryAfter === null) {
    return "too many attempts, wait a few minutes before trying again"
  }
  const minutes = Math.ceil(retryAfter / 60)
  if (minutes <= 1) {
    return "too many attempts, try again in about a minute"
  }
  return `too many attempts, try again in about ${minutes} minutes`
}

export function LoginForm() {
  const router = useRouter()
  const params = useSearchParams()
  const usernameId = useId()
  const passwordId = useId()
  const errorId = useId()

  const [state, formAction, pending] = useActionState(
    async (_previous: FormState, data: FormData): Promise<FormState> => {
      const username = String(data.get("username") ?? "")
      const parsed = loginSchema.safeParse({
        username,
        password: String(data.get("password") ?? ""),
      })
      if (!parsed.success) {
        return { message: parsed.error.issues[0]?.message ?? "check the fields", username }
      }

      const result = await submitLogin(parsed.data)
      if (result.ok) {
        router.replace(safeReturnPath(params.get("from")))
        router.refresh()
        return { message: null, username }
      }

      const failure = result.failure
      if (failure.kind === "credentials") {
        return { message: "wrong username or password", username }
      }
      if (failure.kind === "locked") {
        return { message: lockoutMessage(failure.retryAfter), username }
      }
      if (failure.kind === "unreachable") {
        return { message: "cannot reach the sign-in service, try again shortly", username }
      }
      return { message: failure.message, username }
    },
    EMPTY,
  )

  const invalid = state.message !== null

  return (
    <form action={formAction} className="flex w-full flex-col gap-4">
      <div className="flex flex-col gap-2">
        <label htmlFor={usernameId} className="text-sm font-medium">
          username
        </label>
        <input
          id={usernameId}
          name="username"
          type="text"
          defaultValue={state.username}
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          maxLength={50}
          required
          disabled={pending}
          aria-invalid={invalid}
          aria-describedby={invalid ? errorId : undefined}
          className={FIELD_CLASS}
        />
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor={passwordId} className="text-sm font-medium">
          password
        </label>
        <input
          id={passwordId}
          name="password"
          type="password"
          autoComplete="current-password"
          required
          disabled={pending}
          aria-invalid={invalid}
          aria-describedby={invalid ? errorId : undefined}
          className={FIELD_CLASS}
        />
      </div>

      <p id={errorId} role="alert" aria-live="polite" className="min-h-5 text-sm text-destructive">
        {state.message}
      </p>

      <Button type="submit" size="lg" className="w-full" disabled={pending}>
        {pending ? "signing in" : "sign in"}
      </Button>
    </form>
  )
}
