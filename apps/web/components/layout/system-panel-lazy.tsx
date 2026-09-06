"use client"
import dynamic from "next/dynamic"

const PANEL_CLASS = "h-64 w-full animate-pulse bg-muted motion-reduce:animate-none"

const Panel = dynamic(() => import("@/components/layout/system-panel").then((m) => m.SystemPanel), {
  ssr: false,
  loading: () => <div className={PANEL_CLASS} />,
})

export function preloadSystemPanel(): void {
  void import("@/components/layout/system-panel")
}

export function SystemPanelLazy() {
  return <Panel />
}
