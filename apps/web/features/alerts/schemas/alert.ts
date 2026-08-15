import * as z from "zod/mini"
import type { components } from "@/types/api"

type AlertResponse = components["schemas"]["AlertResponse"]
type AlertPageContract = components["schemas"]["AlertPage"]

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

const relativePath = z.string().check(
  z.maxLength(2048),
  z.refine((value) => value.startsWith("/") && !value.startsWith("//"), {
    message: "expected a same-origin path",
  }),
)

export const alertResponseSchema = z.object({
  _id: z.string().check(z.minLength(1), z.maxLength(128)),
  alert_id: z.string().check(z.minLength(1), z.maxLength(128)),
  session_id: z.int(),
  occurred_at: z.iso.datetime({ offset: true }),
  created_at: z.iso.datetime({ offset: true }),
  camera_id: z.string().check(z.minLength(1), z.maxLength(128)),
  severity,
  object_name: z.string().check(z.maxLength(256)),
  confidence: z.nullish(z.number().check(z.minimum(0), z.maximum(1))),
  snapshot_url: z.nullish(relativePath),
  alert_type: z.nullish(alertType),
  acknowledged: z.boolean(),
  acknowledged_at: z.nullish(z.iso.datetime({ offset: true })),
})

export type Alert = z.output<typeof alertResponseSchema>

export const alertPageSchema = z.object({
  items: z.array(alertResponseSchema),
  next_cursor: z.nullish(z.string().check(z.maxLength(512))),
})

export type AlertPage = z.output<typeof alertPageSchema>

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

type PageFieldsOnlyInContract = Exclude<keyof AlertPageContract, keyof AlertPage>
type PageFieldsOnlyInSchema = Exclude<keyof AlertPage, keyof AlertPageContract>
type NoPageFieldsOnlyInContract = AssertNever<PageFieldsOnlyInContract>
type NoPageFieldsOnlyInSchema = AssertNever<PageFieldsOnlyInSchema>
export type PageContractDrift = [NoPageFieldsOnlyInContract, NoPageFieldsOnlyInSchema]
