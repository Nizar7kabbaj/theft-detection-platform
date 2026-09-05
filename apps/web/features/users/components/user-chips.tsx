import { ROLE_LABELS, type Role } from "@/features/users/schemas/user"
import { cn } from "@/lib/utils"

const ROLE_TONE = new Map<Role, string>([
  ["admin", "border-destructive/40 text-destructive"],
  ["operator", "border-primary/40 text-primary"],
  ["viewer", "border-border text-muted-foreground"],
  ["ml_engineer", "border-border text-foreground"],
  ["compliance", "border-border text-foreground"],
  ["detector", "border-border text-muted-foreground"],
])

export function RoleChip({ role }: { role: string }) {
  const known = ROLE_LABELS.has(role as Role)
  const tone = ROLE_TONE.get(role as Role) ?? "border-border text-muted-foreground"
  const label = known ? ROLE_LABELS.get(role as Role) : role
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] tracking-wide",
        tone,
      )}
    >
      {label}
    </span>
  )
}

export function RoleChips({ roles }: { roles: readonly string[] }) {
  if (roles.length === 0) {
    return <span className="text-muted-foreground text-xs">no roles</span>
  }
  return (
    <span className="flex flex-wrap gap-1">
      {roles.map((role) => (
        <RoleChip key={role} role={role} />
      ))}
    </span>
  )
}

export function StatusChip({ isActive }: { isActive: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider",
        isActive
          ? "border-primary/40 text-primary"
          : "border-border text-muted-foreground opacity-70",
      )}
    >
      {isActive ? "active" : "disabled"}
    </span>
  )
}
