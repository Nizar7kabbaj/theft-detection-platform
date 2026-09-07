"use client"
import { Dialog } from "@base-ui/react/dialog"

const BACKDROP_CLASS = "fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
const POPUP_CLASS =
  "-translate-x-1/2 fixed top-[10vh] left-1/2 z-50 flex w-[min(56rem,calc(100vw-2rem))] flex-col gap-4 rounded-xl border border-border bg-popover p-5 text-popover-foreground shadow-xl outline-none transition-all duration-500 ease-out data-[ending-style]:scale-90 data-[ending-style]:opacity-0 data-[starting-style]:scale-90 data-[starting-style]:opacity-0"

export function ClipDialog({
  open,
  onOpenChange,
  source,
  cameraId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  source: string
  cameraId: string
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className={BACKDROP_CLASS} />
        <Dialog.Popup className={POPUP_CLASS} aria-label="recorded clip">
          <div className="flex flex-col gap-1">
            <span className="text-foreground text-base">recorded clip</span>
            <span className="text-muted-foreground text-xs">
              the seconds leading up to the alert on camera {cameraId}
            </span>
          </div>
          <video
            className="w-full rounded-md bg-black"
            controls
            preload="metadata"
            src={open ? source : undefined}
          >
            <track kind="captions" />
          </video>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
