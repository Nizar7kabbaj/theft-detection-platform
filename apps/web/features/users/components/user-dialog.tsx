"use client"

import { Dialog } from "@base-ui/react/dialog"
import type { ReactNode } from "react"

const BACKDROP_CLASS = "fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
const POPUP_CLASS =
  "-translate-x-1/2 fixed top-[15vh] left-1/2 z-50 flex w-[min(32rem,calc(100vw-2rem))] flex-col gap-4 rounded-xl border border-border bg-popover p-5 text-popover-foreground shadow-xl outline-none"

export function UserDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className={BACKDROP_CLASS} />
        <Dialog.Popup className={POPUP_CLASS} aria-label={title}>
          <div className="flex flex-col gap-1">
            <span className="text-foreground text-base">{title}</span>
            <span className="text-muted-foreground text-xs">{description}</span>
          </div>
          {children}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
