"use client"

import { RefreshCw } from "lucide-react"

export function NewAlertPill({ count, onRefresh }: { count: number; onRefresh: () => void }) {
  if (count === 0) {
    return null
  }

  return (
    <div className="flex justify-center">
      <button
        aria-live="polite"
        className="flex items-center gap-2 rounded-full border border-chart-2/40 bg-chart-2/10 px-3 py-1.5 text-chart-2 transition-colors hover:bg-chart-2/20 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        onClick={onRefresh}
        type="button"
      >
        <RefreshCw aria-hidden="true" className="size-3" />
        <span className="font-mono text-[11px] uppercase tracking-wider">
          {count === 1 ? "1 event changed" : `${count} events changed`}
        </span>
      </button>
    </div>
  )
}
