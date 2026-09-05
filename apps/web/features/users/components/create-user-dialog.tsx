"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { createUser } from "@/features/users/api/users-client"
import { RolePicker } from "@/features/users/components/role-picker"
import { UserDialog } from "@/features/users/components/user-dialog"
import { MIN_PASSWORD_LENGTH, type UserSummary } from "@/features/users/schemas/user"

const FIELD_CLASS =
  "h-8 w-full rounded-lg border border-border bg-background px-2.5 text-sm outline-none focus-visible:border-ring"
const LABEL_CLASS = "text-[11px] text-muted-foreground uppercase tracking-widest"

function problem(username: string, password: string, confirm: string, roles: string[]): string {
  if (username.length < 3) {
    return "username needs at least three characters"
  }
  if (!/^[a-z0-9][a-z0-9._-]*$/.test(username)) {
    return "username takes lowercase letters, digits, dot, dash and underscore"
  }
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `password needs at least ${MIN_PASSWORD_LENGTH} characters`
  }
  if (password !== confirm) {
    return "passwords do not match"
  }
  if (roles.length === 0) {
    return "pick at least one role"
  }
  return ""
}

export function CreateUserDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (user: UserSummary) => void
}) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [roles, setRoles] = useState<string[]>([])
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  function reset() {
    setUsername("")
    setPassword("")
    setConfirm("")
    setRoles([])
    setError("")
    setBusy(false)
  }

  function close(next: boolean) {
    if (!next) {
      reset()
    }
    onOpenChange(next)
  }

  async function submit() {
    const found = problem(username, password, confirm, roles)
    if (found !== "") {
      setError(found)
      return
    }
    setBusy(true)
    setError("")
    try {
      const created = await createUser({ username, password, roles })
      onCreated(created)
      close(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "could not create the account")
      setBusy(false)
    }
  }

  return (
    <UserDialog
      open={open}
      onOpenChange={close}
      title="create user"
      description="the account can sign in as soon as it exists"
    >
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1.5">
          <span className={LABEL_CLASS}>username</span>
          <input
            className={FIELD_CLASS}
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="off"
            disabled={busy}
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL_CLASS}>password</span>
          <input
            className={FIELD_CLASS}
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            disabled={busy}
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL_CLASS}>confirm password</span>
          <input
            className={FIELD_CLASS}
            type="password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            autoComplete="new-password"
            disabled={busy}
          />
        </label>
        <div className="flex flex-col gap-1.5">
          <span className={LABEL_CLASS}>roles</span>
          <RolePicker selected={roles} onChange={setRoles} disabled={busy} />
        </div>
      </div>

      {error === "" ? null : <p className="text-destructive text-xs">{error}</p>}

      <div className="flex justify-end gap-2 border-border/50 border-t pt-3">
        <Button variant="ghost" size="sm" onClick={() => close(false)} disabled={busy}>
          cancel
        </Button>
        <Button variant="default" size="sm" onClick={submit} disabled={busy}>
          {busy ? "creating" : "create user"}
        </Button>
      </div>
    </UserDialog>
  )
}
