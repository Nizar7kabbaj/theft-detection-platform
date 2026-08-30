import * as z from "zod/mini"

const count = z.int().check(z.minimum(0))

export const durationSpreadSchema = z.object({
  under_60: count,
  under_300: count,
  under_900: count,
  over_900: count,
})
export type DurationSpread = z.output<typeof durationSpreadSchema>

export const typeTallySchema = z.object({
  alert_type: z.string().check(z.maxLength(64)),
  count,
})
export type TypeTally = z.output<typeof typeTallySchema>

export const cameraTallySchema = z.object({
  camera_id: z.string().check(z.minLength(1), z.maxLength(128)),
  count,
})
export type CameraTally = z.output<typeof cameraTallySchema>

export const statsBreakdownSchema = z.object({
  start: z.iso.datetime({ offset: true }),
  end: z.iso.datetime({ offset: true }),
  raised: count,
  decided: count,
  median_decision_seconds: z.nullish(count),
  duration: durationSpreadSchema,
  alert_types: z.array(typeTallySchema),
  cameras: z.array(cameraTallySchema),
})
export type StatsBreakdown = z.output<typeof statsBreakdownSchema>
