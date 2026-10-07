"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  createTelegramLink,
  getTelegramStatus,
  unlinkTelegram,
} from "@/features/auth/api/telegram-client"
import type { TelegramLink, TelegramStatus } from "@/features/auth/schemas/telegram"
import { UserDialog } from "@/features/users/components/user-dialog"

const LINK_CLASS =
  "inline-flex h-8 items-center justify-center rounded-lg border border-border px-3 text-sm outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"

function webLink(appUrl: string): string | null {
  try {
    const parsed = new URL(appUrl)
    const domain = parsed.pathname.replace(/^\//, "")
    const start = parsed.searchParams.get("start")
    if (domain === "" || start === null) {
      return null
    }
    const address = `tg://resolve?domain=${domain}&start=${start}`
    return `https://web.telegram.org/k/#?tgaddr=${encodeURIComponent(address)}`
  } catch {
    return null
  }
}

function statusText(status: TelegramStatus | null): string {
  if (status === null) {
    return "checking…"
  }
  if (!status.linked || status.linked_at === null) {
    return "not linked"
  }
  return `linked since ${new Date(status.linked_at).toLocaleString()}`
}

export function TelegramDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [status, setStatus] = useState<TelegramStatus | null>(null)
  const [link, setLink] = useState<TelegramLink | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) {
      setLink(null)
      setError("")
      return
    }
    const controller = new AbortController()
    getTelegramStatus(controller.signal)
      .then(setStatus)
      .catch(() => {
        if (!controller.signal.aborted) {
          setError("could not read the link status")
        }
      })
    return () => controller.abort()
  }, [open])

  async function onCreate() {
    setBusy(true)
    setError("")
    try {
      setLink(await createTelegramLink())
    } catch {
      setError("could not create a link, try again")
    } finally {
      setBusy(false)
    }
  }

  async function onUnlink() {
    setBusy(true)
    setError("")
    try {
      await unlinkTelegram()
      setStatus({ linked: false, linked_at: null })
      setLink(null)
    } catch {
      setError("could not unlink, try again")
    } finally {
      setBusy(false)
    }
  }

  const linked = status?.linked === true
  const web = link === null ? null : webLink(link.url)

  return (
    <UserDialog
      open={open}
      onOpenChange={onOpenChange}
      title="telegram"
      description="link this account so decisions made from telegram carry your name"
    >
      <div className="flex flex-col gap-3 text-sm">
        <span className="text-muted-foreground">{statusText(status)}</span>
        {link === null ? (
          <div className="flex gap-2">
            <Button size="sm" onClick={onCreate} disabled={busy}>
              {linked ? "link another telegram account" : "create link"}
            </Button>
            {linked ? (
              <Button size="sm" variant="outline" onClick={onUnlink} disabled={busy}>
                unlink
              </Button>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              <a className={LINK_CLASS} href={link.url} target="_blank" rel="noopener noreferrer">
                open in telegram app
              </a>
              {web === null ? null : (
                <a className={LINK_CLASS} href={web} target="_blank" rel="noopener noreferrer">
                  open in telegram web
                </a>
              )}
            </div>
            <span className="text-muted-foreground text-xs">
              works once, expires at {new Date(link.expires_at).toLocaleTimeString()}. press start
              in the bot chat.
            </span>
          </div>
        )}
        {error === "" ? null : <span className="text-destructive text-xs">{error}</span>}
      </div>
    </UserDialog>
  )
}
