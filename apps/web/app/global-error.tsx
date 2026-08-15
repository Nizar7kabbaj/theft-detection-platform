"use client"
import { useEffect } from "react"
import { inter } from "@/lib/theme/font"
import "./globals.css"
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    const body = JSON.stringify({ digest: error.digest, path: window.location.pathname })
    if (typeof navigator.sendBeacon === "function") {
      navigator.sendBeacon("/client-error", new Blob([body], { type: "application/json" }))
      return
    }
    void fetch("/client-error", {
      method: "POST",
      body,
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      keepalive: true,
    }).catch(() => undefined)
  }, [error])
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans antialiased">
        <main className="mx-auto flex min-h-svh max-w-3xl flex-col items-start justify-center gap-4 p-8">
          <p className="text-muted-foreground text-sm">the application did not load</p>
          {error.digest === undefined ? null : (
            <p className="text-muted-foreground text-xs tabular-nums">reference {error.digest}</p>
          )}
          <button
            type="button"
            onClick={reset}
            className="rounded border px-3 py-1.5 text-sm hover:bg-muted"
          >
            reload
          </button>
        </main>
      </body>
    </html>
  )
}
