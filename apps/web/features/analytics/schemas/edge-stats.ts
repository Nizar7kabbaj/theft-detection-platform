import { z } from "zod"
import type { components } from "@/types/api"

type EdgeStatsResponse = components["schemas"]["EdgeStatsResponse"]

export const edgeStatsResponseSchema = z.object({
  average_fps: z.number().nullable(),
  latency_ms: z.number().nullable(),
  gpu_temperature_c: z.number().int().nullable(),
  gpu_name: z.string().max(256).nullable(),
  reporting_cameras: z.number().int(),
  total_cameras: z.number().int(),
})
export type EdgeStats = z.output<typeof edgeStatsResponseSchema>

type Concrete<T> = { [K in keyof T]-?: T[K] }
type FieldsOnlyInContract = Exclude<keyof EdgeStatsResponse, keyof EdgeStats>
type FieldsOnlyInSchema = Exclude<keyof EdgeStats, keyof EdgeStatsResponse>
type FieldsWithChangedType = {
  [K in keyof Concrete<EdgeStatsResponse>]: K extends keyof Concrete<EdgeStats>
    ? Concrete<EdgeStatsResponse>[K] extends Concrete<EdgeStats>[K]
      ? never
      : K
    : never
}[keyof Concrete<EdgeStatsResponse>]
type AssertNever<T extends never> = T
type NoFieldsOnlyInContract = AssertNever<FieldsOnlyInContract>
type NoFieldsOnlyInSchema = AssertNever<FieldsOnlyInSchema>
type NoFieldsWithChangedType = AssertNever<FieldsWithChangedType>
export type ContractDrift = [NoFieldsOnlyInContract, NoFieldsOnlyInSchema, NoFieldsWithChangedType]
