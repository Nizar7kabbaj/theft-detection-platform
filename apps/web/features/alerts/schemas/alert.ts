import { z } from "zod"
import type { components } from "@/types/api"

type AlertResponse = components["schemas"]["AlertResponse"]

const severity = z.enum([
  "SEVERITY_UNSPECIFIED",
  "SEVERITY_INFO",
  "SEVERITY_NOTICE",
  "SEVERITY_WARNING",
  "SEVERITY_CRITICAL",
])

const alertType = z.enum([
  "ALERT_TYPE_UNSPECIFIED",
  "ALERT_TYPE_OBJECT_PROXIMITY",
  "ALERT_TYPE_BENDING",
  "ALERT_TYPE_LOITERING",
])

const relativePath = z
  .string()
  .max(2048)
  .refine((value) => value.startsWith("/") && !value.startsWith("//"), {
    message: "expected a same-origin path",
  })

export const alertResponseSchema = z.object({
  _id: z.string().min(1).max(128),
  alert_id: z.string().min(1).max(128),
  session_id: z.number().int(),
  occurred_at: z.iso.datetime({ offset: true }),
  camera_id: z.string().min(1).max(128),
  severity,
  object_name: z.string().max(256),
  confidence: z.number().min(0).max(1).nullish(),
  snapshot_url: relativePath.nullish(),
  alert_type: alertType.nullish(),
})

export type Alert = z.output<typeof alertResponseSchema>

type Concrete<T> = { [K in keyof T]-?: T[K] }

type FieldsOnlyInContract = Exclude<keyof AlertResponse, keyof Alert>
type FieldsOnlyInSchema = Exclude<keyof Alert, keyof AlertResponse>
type FieldsWithChangedType = {
  [K in keyof Concrete<AlertResponse>]: K extends keyof Concrete<Alert>
    ? Concrete<AlertResponse>[K] extends Concrete<Alert>[K]
      ? never
      : K
    : never
}[keyof Concrete<AlertResponse>]

type AssertNever<T extends never> = T
type NoFieldsOnlyInContract = AssertNever<FieldsOnlyInContract>
type NoFieldsOnlyInSchema = AssertNever<FieldsOnlyInSchema>
type NoFieldsWithChangedType = AssertNever<FieldsWithChangedType>
export type ContractDrift = [NoFieldsOnlyInContract, NoFieldsOnlyInSchema, NoFieldsWithChangedType]
