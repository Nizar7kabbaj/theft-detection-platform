import type { BucketUnit } from "@/features/analytics/schemas/timeseries"

export const UNIT_VALUES = ["hour", "day"] as const satisfies readonly BucketUnit[]
export const DEFAULT_UNIT: BucketUnit = "day"

type UncoveredUnit = Exclude<BucketUnit, (typeof UNIT_VALUES)[number]>
type AssertNever<T extends never> = T
export type UnitDrift = AssertNever<UncoveredUnit>

export function parseBucketUnit(params: Record<string, string | string[] | undefined>): BucketUnit {
  const raw = params.unit
  const value = typeof raw === "string" ? raw : Array.isArray(raw) ? raw[0] : undefined
  const match = UNIT_VALUES.find((candidate) => candidate === value)
  return match ?? DEFAULT_UNIT
}
