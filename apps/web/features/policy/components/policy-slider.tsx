"use client"

import type { CSSProperties } from "react"
import { formatUnit } from "@/features/policy/lib/format"
import type { PolicyField } from "@/features/policy/schemas/policy"
import { cn } from "@/lib/utils"

const TRACK =
  "[&::-webkit-slider-runnable-track]:h-1.5 [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-[image:var(--track)] [&::-webkit-slider-runnable-track]:shadow-[inset_0_0_0_1px_var(--border)] [&::-moz-range-track]:h-1.5 [&::-moz-range-track]:rounded-full [&::-moz-range-track]:bg-[image:var(--track)] [&::-moz-range-track]:shadow-[inset_0_0_0_1px_var(--border)]"

const THUMB =
  "[&::-webkit-slider-thumb]:-mt-[7px] [&::-webkit-slider-thumb]:size-5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-background [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow-[0_1px_3px_rgb(0_0_0/0.4)] [&::-moz-range-thumb]:size-5 [&::-moz-range-thumb]:appearance-none [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-background [&::-moz-range-thumb]:bg-primary"

export function PolicySlider({
  field,
  value,
  saved,
  canWrite,
  onChange,
}: {
  field: PolicyField
  value: number
  saved: number
  canWrite: boolean
  onChange: (value: number) => void
}) {
  const dirty = value !== saved
  const Icon = field.icon
  const percent = ((value - field.min) / (field.max - field.min)) * 100
  const track = {
    "--track": `linear-gradient(to right, var(--primary) ${percent}%, var(--muted) ${percent}%)`,
  } as CSSProperties

  return (
    <div className="flex gap-3 border-border/50 border-t px-1 py-3.5 first:border-t-0">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-sm border border-border bg-muted/40 text-muted-foreground">
        <Icon className="size-4" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-foreground text-sm">{field.label}</span>
          <span
            className={cn(
              "shrink-0 rounded-sm px-1.5 py-0.5 font-mono text-sm tabular-nums transition-colors duration-150",
              dirty ? "bg-primary/15 text-primary" : "text-foreground",
            )}
          >
            {formatUnit(value, field.unit)}
          </span>
        </div>
        <p className="text-pretty text-muted-foreground text-xs">{field.hint}</p>
        {canWrite ? (
          <div className="flex items-center gap-2.5">
            <span className="w-9 shrink-0 text-right font-mono text-[10px] text-muted-foreground tabular-nums">
              {formatUnit(field.min, field.unit)}
            </span>
            <input
              type="range"
              min={field.min}
              max={field.max}
              step={field.step}
              value={value}
              style={track}
              aria-label={field.label}
              onChange={(event) => onChange(Number(event.target.value))}
              className={cn(
                "-my-2.5 h-10 flex-1 cursor-pointer appearance-none bg-transparent outline-none",
                TRACK,
                THUMB,
                "focus-visible:[&::-webkit-slider-thumb]:ring-3 focus-visible:[&::-webkit-slider-thumb]:ring-ring/50",
              )}
            />
            <span className="w-9 shrink-0 font-mono text-[10px] text-muted-foreground tabular-nums">
              {formatUnit(field.max, field.unit)}
            </span>
          </div>
        ) : null}
      </div>
    </div>
  )
}
