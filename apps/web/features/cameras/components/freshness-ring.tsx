import {
  elapsedLabel,
  freshnessFraction,
  HEALTH_DETAIL,
  HEALTH_STROKE,
  HEALTH_TEXT,
} from "@/features/cameras/lib/health"
import type { HealthState } from "@/features/cameras/schemas/camera"

const RADIUS = 34
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export function FreshnessRing({ state, seconds }: { state: HealthState; seconds: number | null }) {
  const fraction = freshnessFraction(seconds)
  const offset = CIRCUMFERENCE * (1 - fraction)
  const center = seconds === null ? "--" : elapsedLabel(seconds)
  const spoken =
    seconds === null
      ? `frame freshness, ${HEALTH_DETAIL[state]}`
      : `frame freshness, ${HEALTH_DETAIL[state]}, last frame ${elapsedLabel(seconds)} ago`

  return (
    <div className="flex items-center gap-4">
      <div className="relative size-24 shrink-0">
        <svg role="img" aria-label={spoken} viewBox="0 0 80 80" className="size-full -rotate-90">
          <circle
            cx="40"
            cy="40"
            r={RADIUS}
            fill="none"
            strokeWidth="6"
            className="stroke-border"
          />
          <circle
            cx="40"
            cy="40"
            r={RADIUS}
            fill="none"
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
            className={`${HEALTH_STROKE[state]} transition-[stroke-dashoffset] duration-700 ease-out`}
          />
        </svg>
        <span
          aria-hidden="true"
          className="absolute inset-0 flex items-center justify-center font-medium text-lg tabular-nums"
        >
          {center}
        </span>
      </div>
      <div aria-hidden="true" className="flex min-w-0 flex-col gap-1">
        <span className="text-muted-foreground text-xs uppercase tracking-wide">
          frame freshness
        </span>
        <span className={`font-medium text-sm ${HEALTH_TEXT[state]}`}>{HEALTH_DETAIL[state]}</span>
        <span className="text-muted-foreground text-xs">offline past {elapsedLabel(15)}</span>
      </div>
    </div>
  )
}
