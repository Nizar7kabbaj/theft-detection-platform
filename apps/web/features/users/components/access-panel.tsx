"use client"

import { Collapsible } from "@base-ui/react/collapsible"
import { Check, ChevronDown, Minus } from "lucide-react"
import { grantedFor, type RolePermissionMap } from "@/features/users/schemas/user"
import { cn } from "@/lib/utils"

const TRIGGER_CLASS =
  "group/access flex w-full items-center gap-1.5 text-left text-muted-foreground text-[11px] uppercase tracking-widest outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
const CHEVRON_CLASS =
  "size-3.5 shrink-0 -rotate-90 transition-transform duration-200 group-data-[panel-open]/access:rotate-0"

function split(permission: string): { resource: string; action: string } {
  const parts = permission.split(":")
  return {
    resource: parts[0] ?? permission,
    action: parts[1] ?? "",
  }
}

export function AccessPanel({
  map,
  roles,
  open,
  onOpenChange,
}: {
  map: RolePermissionMap
  roles: readonly string[]
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const granted = grantedFor(map, roles)
  const held = map.permissions.filter((permission) => granted.has(permission)).length

  return (
    <Collapsible.Root open={open} onOpenChange={onOpenChange} className="flex flex-col gap-2">
      <Collapsible.Trigger className={TRIGGER_CLASS}>
        <ChevronDown aria-hidden="true" className={CHEVRON_CLASS} />
        access
        <span className="ml-auto font-mono text-[10px] tabular-nums">
          {held} of {map.permissions.length}
        </span>
      </Collapsible.Trigger>
      <Collapsible.Panel>
        <ul className="flex flex-col gap-1.5 pt-1">
          {map.permissions.map((permission) => {
            const on = granted.has(permission)
            const { resource, action } = split(permission)
            return (
              <li
                key={permission}
                className={cn(
                  "flex items-center justify-between gap-2 font-mono text-xs",
                  on ? "text-foreground" : "text-muted-foreground opacity-50",
                )}
              >
                <span className="flex items-center gap-1.5">
                  {on ? (
                    <Check className="size-3 shrink-0 text-primary" />
                  ) : (
                    <Minus className="size-3 shrink-0" />
                  )}
                  {resource} {action}
                </span>
                <span className="text-[10px] uppercase tracking-wider">
                  {on ? "granted" : "denied"}
                </span>
              </li>
            )
          })}
        </ul>
      </Collapsible.Panel>
    </Collapsible.Root>
  )
}
