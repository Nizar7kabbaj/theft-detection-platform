import { z } from "zod"
import type { components } from "@/types/api"

type StatsResponse = components["schemas"]["StatsResponse"]

const topObjectSchema = z.object({
  object: z.string().max(256).nullable(),
  count: z.number().int(),
})

export const statsResponseSchema = z.object({
  total_alerts: z.number().int(),
  total_detections: z.number().int(),
  total_cameras: z.number().int(),
  alerts_today: z.number().int(),
  high_severity: z.number().int(),
  medium_severity: z.number().int(),
  top_objects: z.array(topObjectSchema),
})

export type Stats = z.output<typeof statsResponseSchema>

type Concrete<T> = { [K in keyof T]-?: T[K] }
type FieldsOnlyInContract = Exclude<keyof StatsResponse, keyof Stats>
type FieldsOnlyInSchema = Exclude<keyof Stats, keyof StatsResponse>
type FieldsWithChangedType = {
  [K in keyof Concrete<StatsResponse>]: K extends keyof Concrete<Stats>
    ? Concrete<StatsResponse>[K] extends Concrete<Stats>[K]
      ? never
      : K
    : never
}[keyof Concrete<StatsResponse>]

type AssertNever<T extends never> = T
type NoFieldsOnlyInContract = AssertNever<FieldsOnlyInContract>
type NoFieldsOnlyInSchema = AssertNever<FieldsOnlyInSchema>
type NoFieldsWithChangedType = AssertNever<FieldsWithChangedType>
export type ContractDrift = [NoFieldsOnlyInContract, NoFieldsOnlyInSchema, NoFieldsWithChangedType]
