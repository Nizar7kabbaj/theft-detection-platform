import * as z from "zod/mini"
import type { components } from "@/types/api"

type DurationSpreadContract = components["schemas"]["DurationSpread"]
type TypeTallyContract = components["schemas"]["TypeTally"]
type CameraTallyContract = components["schemas"]["CameraTally"]
type BreakdownContract = components["schemas"]["StatsBreakdownResponse"]

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

type Concrete<T> = { [K in keyof T]-?: T[K] }
type AssertNever<T extends never> = T
type OnlyIn<Left, Right> = Exclude<keyof Left, keyof Right>
type ChangedType<Contract, Schema> = {
  [K in keyof Concrete<Contract>]: K extends keyof Concrete<Schema>
    ? Concrete<Contract>[K] extends Concrete<Schema>[K]
      ? never
      : K
    : never
}[keyof Concrete<Contract>]

export type DurationSpreadDrift = [
  AssertNever<OnlyIn<DurationSpreadContract, DurationSpread>>,
  AssertNever<OnlyIn<DurationSpread, DurationSpreadContract>>,
  AssertNever<ChangedType<DurationSpreadContract, DurationSpread>>,
]

export type TypeTallyDrift = [
  AssertNever<OnlyIn<TypeTallyContract, TypeTally>>,
  AssertNever<OnlyIn<TypeTally, TypeTallyContract>>,
  AssertNever<ChangedType<TypeTallyContract, TypeTally>>,
]

export type CameraTallyDrift = [
  AssertNever<OnlyIn<CameraTallyContract, CameraTally>>,
  AssertNever<OnlyIn<CameraTally, CameraTallyContract>>,
  AssertNever<ChangedType<CameraTallyContract, CameraTally>>,
]

export type BreakdownDrift = [
  AssertNever<OnlyIn<BreakdownContract, StatsBreakdown>>,
  AssertNever<OnlyIn<StatsBreakdown, BreakdownContract>>,
]
