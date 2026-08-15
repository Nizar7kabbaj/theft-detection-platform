"use client"

import { Search } from "lucide-react"
import { cn } from "@/lib/utils"

const WRAP_CLASS = "px-2 pt-2"

const BUTTON_CLASS =
  "flex w-full items-center gap-2 rounded-md border border-sidebar-border bg-background/50 px-2 py-1.5 text-left outline-none transition-colors hover:bg-sidebar-accent/60 focus-visible:ring-2 focus-visible:ring-sidebar-ring"

const KBD_CLASS =
  "ml-auto shrink-0 rounded border border-sidebar-border px-1 py-px font-sans text-[0.625rem] text-muted-foreground"

export function SidebarSearch({ collapsed }: { collapsed: boolean }) {
  return (
    <div className={cn(WRAP_CLASS, collapsed && "px-1")}>
      <button
        type="button"
        disabled
        className={cn(BUTTON_CLASS, collapsed && "justify-center px-0")}
        aria-label="search, not available yet"
        title="search"
      >
        <Search className="size-4 shrink-0 text-muted-foreground" />
        <span className={cn("text-[0.8125rem]/5 text-muted-foreground", collapsed && "sr-only")}>
          search
        </span>
        <kbd className={cn(KBD_CLASS, collapsed && "hidden")}>⌘K</kbd>
      </button>
    </div>
  )
}
