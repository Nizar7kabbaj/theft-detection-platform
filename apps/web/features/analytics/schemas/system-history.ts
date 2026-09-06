import * as z from "zod/mini"
import type { components } from "@/types/api"

type SystemHistoryContract = components["schemas"]["SystemHistoryResponse"]

export const systemHistoryResponseSchema = z.object({
  cpu: z.array(z.number()),
  gpu: z.array(z.number()),
  memory: z.array(z.number()),
  network: z.array(z.number()),
  cpu_temperature: z.array(z.number()),
  gpu_temperature: z.array(z.number()),
})
export type SystemHistory = z.output<typeof systemHistoryResponseSchema>

type Concrete<T> = { [K in keyof T]-?: T[K] }
type FieldsOnlyInContract = Exclude<keyof SystemHistoryContract, keyof SystemHistory>
type FieldsOnlyInSchema = Exclude<keyof SystemHistory, keyof SystemHistoryContract>
type FieldsWithChangedType = {
  [K in keyof Concrete<SystemHistoryContract>]: K extends keyof Concrete<SystemHistory>
    ? Concrete<SystemHistoryContract>[K] extends Concrete<SystemHistory>[K]
      ? never
      : K
    : never
}[keyof Concrete<SystemHistoryContract>]

type AssertNever<T extends never> = T
type NoFieldsOnlyInContract = AssertNever<FieldsOnlyInContract>
type NoFieldsOnlyInSchema = AssertNever<FieldsOnlyInSchema>
type NoFieldsWithChangedType = AssertNever<FieldsWithChangedType>
export type ContractDrift = [NoFieldsOnlyInContract, NoFieldsOnlyInSchema, NoFieldsWithChangedType]
