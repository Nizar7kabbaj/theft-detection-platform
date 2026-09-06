import * as z from "zod/mini"
import type { components } from "@/types/api"

type SystemStatsContract = components["schemas"]["SystemStatsResponse"]
type ServiceMemoryContract = components["schemas"]["ServiceMemory"]

export const serviceMemorySchema = z.object({
  camera: z.nullish(z.number()),
  gate: z.nullish(z.number()),
  inference: z.nullish(z.number()),
  notification: z.nullish(z.number()),
})
export type ServiceMemory = z.output<typeof serviceMemorySchema>

export const systemStatsResponseSchema = z.object({
  cpu_percent: z.nullish(z.number()),
  memory_percent: z.nullish(z.number()),
  network_bytes_per_second: z.nullish(z.number()),
  gpu_percent: z.nullish(z.number()),
  gpu_temperature_c: z.nullish(z.number()),
  cpu_temperature_c: z.nullish(z.number()),
  service_memory_bytes: serviceMemorySchema,
})
export type SystemStats = z.output<typeof systemStatsResponseSchema>

type Concrete<T> = { [K in keyof T]-?: T[K] }
type FieldsOnlyInContract = Exclude<keyof SystemStatsContract, keyof SystemStats>
type FieldsOnlyInSchema = Exclude<keyof SystemStats, keyof SystemStatsContract>
type FieldsWithChangedType = {
  [K in keyof Concrete<SystemStatsContract>]: K extends keyof Concrete<SystemStats>
    ? Concrete<SystemStatsContract>[K] extends Concrete<SystemStats>[K]
      ? never
      : K
    : never
}[keyof Concrete<SystemStatsContract>]

type AssertNever<T extends never> = T
type NoFieldsOnlyInContract = AssertNever<FieldsOnlyInContract>
type NoFieldsOnlyInSchema = AssertNever<FieldsOnlyInSchema>
type NoFieldsWithChangedType = AssertNever<FieldsWithChangedType>
export type ContractDrift = [NoFieldsOnlyInContract, NoFieldsOnlyInSchema, NoFieldsWithChangedType]

type MemoryFieldsOnlyInContract = Exclude<keyof ServiceMemoryContract, keyof ServiceMemory>
type MemoryFieldsOnlyInSchema = Exclude<keyof ServiceMemory, keyof ServiceMemoryContract>
type MemoryFieldsWithChangedType = {
  [K in keyof Concrete<ServiceMemoryContract>]: K extends keyof Concrete<ServiceMemory>
    ? Concrete<ServiceMemoryContract>[K] extends Concrete<ServiceMemory>[K]
      ? never
      : K
    : never
}[keyof Concrete<ServiceMemoryContract>]

type NoMemoryFieldsOnlyInContract = AssertNever<MemoryFieldsOnlyInContract>
type NoMemoryFieldsOnlyInSchema = AssertNever<MemoryFieldsOnlyInSchema>
type NoMemoryFieldsWithChangedType = AssertNever<MemoryFieldsWithChangedType>
export type MemoryContractDrift = [
  NoMemoryFieldsOnlyInContract,
  NoMemoryFieldsOnlyInSchema,
  NoMemoryFieldsWithChangedType,
]
