export function PageHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h1 className="font-medium text-[1.0625rem]/6 text-foreground">{title}</h1>
      <p className="text-muted-foreground text-[0.8125rem]/5">{description}</p>
    </div>
  )
}
