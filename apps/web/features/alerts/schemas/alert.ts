import * as z from "zod/mini"
import type { components } from "@/types/api"

type AlertResponse = components["schemas"]["AlertResponse"]
type AlertPageContract = components["schemas"]["AlertPage"]
type AlertDetailContract = components["schemas"]["AlertDetail"]

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
  "ALERT_TYPE_CONCEALMENT",
  "ALERT_TYPE_LOITERING",
])

export const decisionSchema = z.enum([
  "DECISION_UNSPECIFIED",
  "DECISION_CONFIRMED",
  "DECISION_DISMISSED",
  "DECISION_UNSURE",
])

export type Decision = z.output<typeof decisionSchema>

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

const bboxSchema = z.object({
  x1: z.number(),
  y1: z.number(),
  x2: z.number(),
  y2: z.number(),
})

export type Bbox = z.output<typeof bboxSchema>

const keypointSchema = z.object({
  x: z.number(),
  y: z.number(),
  confidence: z.number().check(z.minimum(0), z.maximum(1)),
})

export type Keypoint = z.output<typeof keypointSchema>

const personSchema = z.object({
  track_id: z.int(),
  bbox: z.nullish(bboxSchema),
  keypoints: z.optional(z.array(keypointSchema)),
})

export type Person = z.output<typeof personSchema>

const objectSchema = z.object({
  class_name: z.string().check(z.maxLength(256)),
  bbox: z.nullish(bboxSchema),
})

export type DetectedObject = z.output<typeof objectSchema>

const concealmentSchema = z.object({
  object_track_id: z.int(),
  object_class: z.string().check(z.maxLength(256)),
  last_seen_frame: z.int(),
  missing_frames: z.int(),
  person_track_id: z.int(),
  wrist_index: z.int(),
  wrist_x: z.number(),
  wrist_y: z.number(),
  grab_distance: z.number(),
})

export type Concealment = z.output<typeof concealmentSchema>

export const alertDetailSchema = z.object({
  _id: z.string().check(z.minLength(1), z.maxLength(128)),
  alert_id: z.string().check(z.minLength(1), z.maxLength(128)),
  session_id: z.int(),
  frame_index: z.int(),
  occurred_at: z.iso.datetime({ offset: true }),
  created_at: z.iso.datetime({ offset: true }),
  camera_id: z.string().check(z.minLength(1), z.maxLength(128)),
  severity,
  alert_type: z.nullish(alertType),
  acknowledged: z.boolean(),
  acknowledged_at: z.nullish(z.iso.datetime({ offset: true })),
  decision: decisionSchema,
  decided_at: z.nullish(z.iso.datetime({ offset: true })),
  decided_by: z.nullish(z.string().check(z.maxLength(128))),
  person: z.nullish(personSchema),
  object: z.nullish(objectSchema),
  frame_width: z.nullish(z.int()),
  frame_height: z.nullish(z.int()),
  concealment: z.nullish(concealmentSchema),
  classifier_score: z.nullish(z.number()),
  classifier_state: z.nullish(z.string().check(z.maxLength(128))),
  snapshot_url: z.nullish(relativePath),
})

export type AlertDetail = z.output<typeof alertDetailSchema>

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

type DetailFieldsOnlyInContract = Exclude<keyof AlertDetailContract, keyof AlertDetail>
type DetailFieldsOnlyInSchema = Exclude<keyof AlertDetail, keyof AlertDetailContract>
type DetailFieldsWithChangedType = {
  [K in keyof Concrete<AlertDetailContract>]: K extends keyof Concrete<AlertDetail>
    ? Concrete<AlertDetailContract>[K] extends Concrete<AlertDetail>[K]
      ? never
      : K
    : never
}[keyof Concrete<AlertDetailContract>]

type NoDetailFieldsOnlyInContract = AssertNever<DetailFieldsOnlyInContract>
type NoDetailFieldsOnlyInSchema = AssertNever<DetailFieldsOnlyInSchema>
type NoDetailFieldsWithChangedType = AssertNever<DetailFieldsWithChangedType>

export type DetailContractDrift = [
  NoDetailFieldsOnlyInContract,
  NoDetailFieldsOnlyInSchema,
  NoDetailFieldsWithChangedType,
]
