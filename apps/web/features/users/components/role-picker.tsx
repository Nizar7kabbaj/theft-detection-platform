"use client"

import { ROLE_LABELS, ROLE_VALUES, type Role } from "@/features/users/schemas/user"
import { cn } from "@/lib/utils"

export function RolePicker({
  selected,
  onChange,
  disabled,
}: {
  selected: readonly string[]
  onChange: (roles: string[]) => void
  disabled?: boolean
}) {
  function toggle(role: Role) {
    if (selected.includes(role)) {
      onChange(selected.filter((entry) => entry !== role))
      return
    }
    onChange([...selected, role])
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {ROLE_VALUES.map((role) => {
        const on = selected.includes(role)
        return (
          <button
            key={role}
            type="button"
            disabled={disabled === true}
            onClick={() => toggle(role)}
            aria-pressed={on}
            className={cn(
              "rounded border px-2 py-1 font-mono text-[11px] transition-colors disabled:opacity-50",
              on
                ? "border-primary/50 bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:border-border hover:text-foreground",
            )}
          >
            {ROLE_LABELS.get(role)}
          </button>
        )
      })}
    </div>
  )
}
