"use client"
import { Dialog } from "@base-ui/react/dialog"
import { Search } from "lucide-react"
import { useRouter } from "next/navigation"
import { useCallback, useMemo, useRef, useState } from "react"
import type { NavLink, NavSection } from "@/lib/navigation/links"
import { cn } from "@/lib/utils"

const BACKDROP_CLASS = "fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
const POPUP_CLASS =
  "-translate-x-1/2 fixed top-[20vh] left-1/2 z-50 w-[min(36rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-xl outline-none"
const FIELD_CLASS = "flex items-center gap-2.5 border-border border-b px-4"
const INPUT_CLASS =
  "h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
const LIST_CLASS = "max-h-72 overflow-y-auto p-1.5"
const HEADING_CLASS = "px-2.5 pt-2 pb-1 text-muted-foreground text-xs uppercase tracking-wider"
const ITEM_BASE_CLASS =
  "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm outline-none"
const ITEM_ACTIVE_CLASS = "bg-accent text-accent-foreground"
const ITEM_IDLE_CLASS = "text-foreground/80"
type Match = { link: NavLink; heading: string }
function matches(sections: readonly NavSection[], query: string): Match[] {
  const term = query.trim().toLowerCase()
  const found: Match[] = []
  for (const section of sections) {
    for (const link of section.links) {
      if (term.length === 0 || link.label.includes(term) || section.heading.includes(term)) {
        found.push({ link, heading: section.heading })
      }
    }
  }
  return found
}
export function CommandPalette({
  sections,
  open,
  onOpenChange,
}: {
  sections: readonly NavSection[]
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const router = useRouter()
  const input = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState("")
  const [index, setIndex] = useState(0)
  const results = useMemo(() => matches(sections, query), [sections, query])
  const go = useCallback(
    (link: NavLink) => {
      onOpenChange(false)
      setQuery("")
      router.push(link.href)
    },
    [onOpenChange, router],
  )
  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (results.length === 0) {
      return
    }
    if (event.key === "ArrowDown") {
      event.preventDefault()
      setIndex((current) => (current + 1) % results.length)
      return
    }
    if (event.key === "ArrowUp") {
      event.preventDefault()
      setIndex((current) => (current - 1 + results.length) % results.length)
      return
    }
    if (event.key === "Enter") {
      event.preventDefault()
      const picked = results[index]
      if (picked) {
        go(picked.link)
      }
    }
  }
  let heading = ""
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className={BACKDROP_CLASS} />
        <Dialog.Popup className={POPUP_CLASS} aria-label="command palette" initialFocus={input}>
          <div className={FIELD_CLASS}>
            <Search aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
            <input
              ref={input}
              className={INPUT_CLASS}
              onChange={(event) => {
                setQuery(event.target.value)
                setIndex(0)
              }}
              onKeyDown={onKeyDown}
              placeholder="type to search"
              value={query}
            />
          </div>
          <div className={LIST_CLASS}>
            {results.length === 0 ? (
              <p className="px-2.5 py-6 text-center text-muted-foreground text-sm">no matches</p>
            ) : (
              results.map((result, position) => {
                const first = result.heading !== heading
                heading = result.heading
                return (
                  <div key={result.link.href}>
                    {first ? <p className={HEADING_CLASS}>{result.heading}</p> : null}
                    <button
                      type="button"
                      className={cn(
                        ITEM_BASE_CLASS,
                        position === index ? ITEM_ACTIVE_CLASS : ITEM_IDLE_CLASS,
                      )}
                      onClick={() => go(result.link)}
                      onMouseEnter={() => setIndex(position)}
                    >
                      {result.link.label}
                    </button>
                  </div>
                )
              })
            )}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
