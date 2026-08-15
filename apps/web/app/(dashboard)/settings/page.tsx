import type { Metadata } from "next"

export const metadata: Metadata = { title: "settings" }

export default function SettingsPage() {
  return (
    <section className="flex flex-col gap-2">
      <h1 className="font-medium text-foreground text-lg">settings</h1>
      <p className="text-muted-foreground text-sm">not implemented yet</p>
    </section>
  )
}
