"use client"
import { Tooltip } from "@base-ui/react/tooltip"
import { cn } from "@/lib/utils"

const RAIL_CLASS =
  "group/rail fixed top-1/2 z-30 flex h-12 w-7 -translate-y-1/2 cursor-pointer items-center justify-center outline-none transition-[left] duration-200 ease-linear focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
const STACK_CLASS = "relative flex h-5 w-2 flex-col items-center justify-center"
const BAR_CLASS =
  "absolute h-2.5 w-0.5 rounded-full bg-border transition-all duration-200 ease-linear group-hover/rail:bg-foreground"
const BAR_TOP_CLASS =
  "bottom-1/2 origin-bottom group-hover/rail:rotate-30 group-data-[collapsed=true]/rail:-rotate-30"
const BAR_BOTTOM_CLASS =
  "top-1/2 origin-top group-hover/rail:-rotate-30 group-data-[collapsed=true]/rail:rotate-30"
const POPUP_CLASS =
  "z-50 rounded-md bg-foreground px-2 py-1 font-medium text-background text-xs shadow-md"
export function SidebarToggle({
  collapsed,
  onToggle,
}: {
  collapsed: boolean
  onToggle: () => void
}) {
  return (
    <Tooltip.Provider delay={300}>
      <Tooltip.Root>
        <Tooltip.Trigger
          type="button"
          onClick={onToggle}
          data-collapsed={collapsed}
          aria-expanded={!collapsed}
          aria-controls="app-sidebar"
          aria-label={collapsed ? "expand sidebar" : "collapse sidebar"}
          className={cn(
            RAIL_CLASS,
            collapsed ? "left-(--sidebar-width-icon)" : "left-(--sidebar-width)",
          )}
        >
          <span aria-hidden="true" className={STACK_CLASS}>
            <span className={cn(BAR_CLASS, BAR_TOP_CLASS)} />
            <span className={cn(BAR_CLASS, BAR_BOTTOM_CLASS)} />
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Positioner side="right" sideOffset={6}>
            <Tooltip.Popup className={POPUP_CLASS}>
              {collapsed ? "expand" : "collapse"}
            </Tooltip.Popup>
          </Tooltip.Positioner>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
