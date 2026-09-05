"use client"

import { KeyRound, LogOut, Power, ShieldCheck, Trash2 } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  deleteUser,
  resetPassword,
  revokeUserSessions,
  setUserActive,
  updateRoles,
} from "@/features/users/api/users-client"
import { RolePicker } from "@/features/users/components/role-picker"
import { UserDialog } from "@/features/users/components/user-dialog"
import { MIN_PASSWORD_LENGTH, type UserSummary } from "@/features/users/schemas/user"

type Kind = "roles" | "password" | "active" | "sessions" | "erase"

const FIELD_CLASS =
  "h-8 w-full rounded-lg border border-border bg-background px-2.5 text-sm outline-none focus-visible:border-ring"
const LABEL_CLASS = "text-[11px] text-muted-foreground uppercase tracking-widest"

function reason(cause: unknown, fallback: string): string {
  return cause instanceof Error ? cause.message : fallback
}

export function UserActions({
  user,
  isSelf,
  onUpdated,
  onDeleted,
}: {
  user: UserSummary
  isSelf: boolean
  onUpdated: (user: UserSummary) => void
  onDeleted: (userId: string) => void
}) {
  const router = useRouter()
  const [open, setOpen] = useState<Kind | null>(null)
  const [roles, setRoles] = useState<string[]>([...user.roles])
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [typedName, setTypedName] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState("")

  function close() {
    setOpen(null)
    setError("")
    setPassword("")
    setConfirm("")
    setTypedName("")
    setBusy(false)
  }

  function start(kind: Kind) {
    setError("")
    setNote("")
    if (kind === "roles") {
      setRoles([...user.roles])
    }
    setOpen(kind)
  }

  async function saveRoles() {
    if (roles.length === 0) {
      setError("pick at least one role")
      return
    }
    setBusy(true)
    try {
      onUpdated(await updateRoles(user.id, roles))
      close()
    } catch (cause) {
      setError(reason(cause, "could not save the roles"))
      setBusy(false)
    }
  }

  async function savePassword() {
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`password needs at least ${MIN_PASSWORD_LENGTH} characters`)
      return
    }
    if (password !== confirm) {
      setError("passwords do not match")
      return
    }
    setBusy(true)
    try {
      await resetPassword(user.id, password)
      setNote("password changed, that account is signed out")
      close()
      router.refresh()
    } catch (cause) {
      setError(reason(cause, "could not change the password"))
      setBusy(false)
    }
  }

  async function toggleActive() {
    setBusy(true)
    try {
      onUpdated(await setUserActive(user.id, !user.is_active))
      close()
    } catch (cause) {
      setError(reason(cause, "could not change the account state"))
      setBusy(false)
    }
  }

  async function dropSessions() {
    setBusy(true)
    try {
      const result = await revokeUserSessions(user.id)
      setNote(
        result.revoked === 0
          ? "that account had no live session"
          : `${result.revoked} session${result.revoked === 1 ? "" : "s"} ended`,
      )
      close()
      router.refresh()
    } catch (cause) {
      setError(reason(cause, "could not end the sessions"))
      setBusy(false)
    }
  }

  async function erase() {
    if (typedName !== user.username) {
      setError("type the username exactly to confirm")
      return
    }
    setBusy(true)
    try {
      const result = await deleteUser(user.id)
      onDeleted(user.id)
      setNote(
        result.records_erased === 0
          ? "account removed, no audit payload named this person"
          : `account removed, ${result.records_erased} audit payloads erased`,
      )
      close()
      router.refresh()
    } catch (cause) {
      setError(reason(cause, "could not remove the account"))
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <span className={LABEL_CLASS}>actions</span>
      <div className="grid grid-cols-2 gap-2">
        <Button variant="outline" size="sm" onClick={() => start("roles")}>
          <ShieldCheck data-icon="inline-start" />
          edit roles
        </Button>
        <Button variant="outline" size="sm" onClick={() => start("password")}>
          <KeyRound data-icon="inline-start" />
          reset password
        </Button>
        <Button
          variant={user.is_active ? "destructive" : "outline"}
          size="sm"
          onClick={() => start("active")}
          disabled={isSelf && user.is_active}
        >
          <Power data-icon="inline-start" />
          {user.is_active ? "deactivate" : "reactivate"}
        </Button>
        <Button variant="outline" size="sm" onClick={() => start("sessions")}>
          <LogOut data-icon="inline-start" />
          end sessions
        </Button>
      </div>
      <Button
        variant="destructive"
        size="sm"
        onClick={() => start("erase")}
        disabled={isSelf}
        className="w-full"
      >
        <Trash2 data-icon="inline-start" />
        erase account
      </Button>
      {note === "" ? null : <p className="text-muted-foreground text-xs">{note}</p>}

      <UserDialog
        open={open === "roles"}
        onOpenChange={close}
        title={`roles for ${user.username}`}
        description="permissions follow the roles, no sign-in needed for the change to apply"
      >
        <RolePicker selected={roles} onChange={setRoles} disabled={busy} />
        {error === "" ? null : <p className="text-destructive text-xs">{error}</p>}
        <div className="flex justify-end gap-2 border-border/50 border-t pt-3">
          <Button variant="ghost" size="sm" onClick={close} disabled={busy}>
            cancel
          </Button>
          <Button variant="default" size="sm" onClick={saveRoles} disabled={busy}>
            {busy ? "saving" : "save roles"}
          </Button>
        </div>
      </UserDialog>

      <UserDialog
        open={open === "password"}
        onOpenChange={close}
        title={`reset password for ${user.username}`}
        description="every live session for that account ends straight away"
      >
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className={LABEL_CLASS}>new password</span>
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
        </div>
        {error === "" ? null : <p className="text-destructive text-xs">{error}</p>}
        <div className="flex justify-end gap-2 border-border/50 border-t pt-3">
          <Button variant="ghost" size="sm" onClick={close} disabled={busy}>
            cancel
          </Button>
          <Button variant="default" size="sm" onClick={savePassword} disabled={busy}>
            {busy ? "saving" : "reset password"}
          </Button>
        </div>
      </UserDialog>

      <UserDialog
        open={open === "active"}
        onOpenChange={close}
        title={user.is_active ? `deactivate ${user.username}` : `reactivate ${user.username}`}
        description={
          user.is_active
            ? "sign-in is refused and every live session ends, the account is kept"
            : "the account can sign in again with its existing password"
        }
      >
        {error === "" ? null : <p className="text-destructive text-xs">{error}</p>}
        <div className="flex justify-end gap-2 border-border/50 border-t pt-3">
          <Button variant="ghost" size="sm" onClick={close} disabled={busy}>
            cancel
          </Button>
          <Button
            variant={user.is_active ? "destructive" : "default"}
            size="sm"
            onClick={toggleActive}
            disabled={busy}
          >
            {user.is_active ? "deactivate" : "reactivate"}
          </Button>
        </div>
      </UserDialog>

      <UserDialog
        open={open === "sessions"}
        onOpenChange={close}
        title={`end sessions for ${user.username}`}
        description="that account is signed out everywhere, it can sign back in"
      >
        {error === "" ? null : <p className="text-destructive text-xs">{error}</p>}
        <div className="flex justify-end gap-2 border-border/50 border-t pt-3">
          <Button variant="ghost" size="sm" onClick={close} disabled={busy}>
            cancel
          </Button>
          <Button variant="default" size="sm" onClick={dropSessions} disabled={busy}>
            end sessions
          </Button>
        </div>
      </UserDialog>

      <UserDialog
        open={open === "erase"}
        onOpenChange={close}
        title={`erase ${user.username}`}
        description="this is a data subject erasure and it cannot be undone"
      >
        <div className="flex flex-col gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-3">
          <span className="text-[11px] text-destructive uppercase tracking-widest">
            what this removes
          </span>
          <ul className="flex list-disc flex-col gap-1.5 pl-4 text-foreground text-xs">
            <li>the account, permanently, with no way to restore it</li>
            <li>every session and refresh token belonging to that account</li>
            <li>the personal details held inside audit records naming that person</li>
          </ul>
          <span className="text-[11px] text-destructive uppercase tracking-widest">
            what is kept
          </span>
          <p className="text-muted-foreground text-xs">
            the audit log keeps a sealed record that the erasure took place, who asked for it and
            when. the record carries no name and cannot be traced back to the person. it exists so
            the erasure itself stays provable.
          </p>
        </div>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL_CLASS}>type {user.username} to confirm</span>
          <input
            className={FIELD_CLASS}
            value={typedName}
            onChange={(event) => setTypedName(event.target.value)}
            autoComplete="off"
            disabled={busy}
          />
        </label>
        {error === "" ? null : <p className="text-destructive text-xs">{error}</p>}
        <div className="flex justify-end gap-2 border-border/50 border-t pt-3">
          <Button variant="ghost" size="sm" onClick={close} disabled={busy}>
            cancel
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={erase}
            disabled={busy || typedName !== user.username}
          >
            {busy ? "erasing" : "erase account"}
          </Button>
        </div>
      </UserDialog>
    </div>
  )
}
