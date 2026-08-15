"use client"
import { Menu } from "@base-ui/react/menu"
import { Monitor, MoonStar, Sun } from "lucide-react"
import type { ComponentType } from "react"
import { THEMES, type Theme } from "@/lib/theme/theme-cookie"
import { useTheme } from "@/lib/theme/use-theme"
import { cn } from "@/lib/utils"

const THEME_ICONS: Record<Theme, ComponentType<{ className?: string }>> = {
  light: Sun,
  dark: MoonStar,
  system: Monitor,
}

const ITEM_CLASS =
  "flex flex-1 items-center justify-center rounded-sm py-1.5 outline-none data-[highlighted]:bg-accent"

export function ThemeMenuItems() {
  const { theme, setTheme } = useTheme()
  return (
    <div className="flex items-center gap-2 px-2 py-1.5">
      <span className="text-muted-foreground text-xs">theme</span>
      <div className="ml-auto flex items-center gap-1 rounded-md bg-muted/60 p-0.5">
        {THEMES.map((value) => {
          const Icon = THEME_ICONS[value]
          const active = theme === value
          return (
            <Menu.Item
              key={value}
              closeOnClick={false}
              onClick={() => setTheme(value)}
              aria-label={value}
              className={cn(
                ITEM_CLASS,
                "w-8",
                active ? "bg-background text-foreground" : "text-muted-foreground",
              )}
            >
              <Icon className="size-3.5" />
            </Menu.Item>
          )
        })}
      </div>
    </div>
  )
}
