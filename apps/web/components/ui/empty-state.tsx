import type { ComponentType, ReactNode } from "react"

const WRAP_CLASS =
  "flex min-h-64 flex-1 flex-col items-center justify-center gap-3 rounded-lg border border-border border-dashed bg-card/40 px-6 py-12 text-center"
const ICON_WRAP_CLASS =
  "flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground"
export function EmptyState({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: ComponentType<{ className?: string }>
  title: string
  description: string
  children?: ReactNode
}) {
  return (
    <div className={WRAP_CLASS}>
      <span aria-hidden="true" className={ICON_WRAP_CLASS}>
        <Icon className="size-5" />
      </span>
      <h2 className="font-semibold text-foreground text-lg tracking-tight">{title}</h2>
      <p className="max-w-sm text-muted-foreground text-sm">{description}</p>
      {children}
    </div>
  )
}
