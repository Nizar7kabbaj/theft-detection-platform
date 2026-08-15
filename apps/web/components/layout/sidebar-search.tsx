"use client"
import { Search } from "lucide-react"

const WRAP_CLASS = "px-2 pt-2"
const BUTTON_CLASS =
  "flex w-full items-center gap-2 overflow-hidden rounded-md border border-sidebar-border bg-background/50 px-2 py-1.5 text-left text-muted-foreground outline-none transition-[gap,padding,background-color,border-color,color] duration-200 ease-linear hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring group-data-[collapsed=true]/sidebar:justify-center group-data-[collapsed=true]/sidebar:gap-0 group-data-[collapsed=true]/sidebar:border-transparent group-data-[collapsed=true]/sidebar:bg-transparent group-data-[collapsed=true]/sidebar:px-0"
const LABEL_CLASS =
  "max-w-40 truncate text-sm transition-[max-width,opacity] duration-200 ease-linear group-data-[collapsed=true]/sidebar:max-w-0 group-data-[collapsed=true]/sidebar:opacity-0"
const KBD_CLASS =
  "ml-auto shrink-0 rounded border border-sidebar-border px-1 py-px font-sans text-[0.625rem] text-muted-foreground transition-opacity duration-200 ease-linear group-data-[collapsed=true]/sidebar:hidden"
export function SidebarSearch({ onOpen }: { onOpen: () => void }) {
  return (
    <div className={WRAP_CLASS}>
      <button type="button" onClick={onOpen} className={BUTTON_CLASS} aria-label="search">
        <Search className="size-4 shrink-0" />
        <span className={LABEL_CLASS}>search</span>
        <kbd className={KBD_CLASS}>Ctrl K</kbd>
      </button>
    </div>
  )
}
