import * as z from "zod/mini"
import type { components } from "@/types/api"

type AlertBucketContract = components["schemas"]["AlertBucket"]
type DecisionBucketContract = components["schemas"]["DecisionBucket"]
type TimeseriesContract = components["schemas"]["StatsTimeseriesResponse"]

export const bucketUnitSchema = z.enum(["hour", "day"])
export type BucketUnit = z.output<typeof bucketUnitSchema>

const count = z.int().check(z.minimum(0))

export const alertBucketSchema = z.object({
  bucket: z.iso.datetime({ offset: true }),
  critical: count,
  warning: count,
  notice: count,
  info: count,
  unspecified: count,
  total: count,
})
export type AlertBucket = z.output<typeof alertBucketSchema>

export const decisionBucketSchema = z.object({
  bucket: z.iso.datetime({ offset: true }),
  confirmed: count,
  dismissed: count,
  unsure: count,
  total: count,
})
export type DecisionBucket = z.output<typeof decisionBucketSchema>

export const statsTimeseriesSchema = z.object({
  start: z.iso.datetime({ offset: true }),
  end: z.iso.datetime({ offset: true }),
  unit: bucketUnitSchema,
  alerts: z.array(alertBucketSchema),
  decisions: z.array(decisionBucketSchema),
})
export type StatsTimeseries = z.output<typeof statsTimeseriesSchema>

type Concrete<T> = { [K in keyof T]-?: T[K] }
type AssertNever<T extends never> = T

type AlertFieldsOnlyInContract = Exclude<keyof AlertBucketContract, keyof AlertBucket>
type AlertFieldsOnlyInSchema = Exclude<keyof AlertBucket, keyof AlertBucketContract>
type AlertFieldsWithChangedType = {
  [K in keyof Concrete<AlertBucketContract>]: K extends keyof Concrete<AlertBucket>
    ? Concrete<AlertBucketContract>[K] extends Concrete<AlertBucket>[K]
      ? never
      : K
    : never
}[keyof Concrete<AlertBucketContract>]
export type AlertBucketDrift = [
  AssertNever<AlertFieldsOnlyInContract>,
  AssertNever<AlertFieldsOnlyInSchema>,
  AssertNever<AlertFieldsWithChangedType>,
]

type DecisionFieldsOnlyInContract = Exclude<keyof DecisionBucketContract, keyof DecisionBucket>
type DecisionFieldsOnlyInSchema = Exclude<keyof DecisionBucket, keyof DecisionBucketContract>
type DecisionFieldsWithChangedType = {
  [K in keyof Concrete<DecisionBucketContract>]: K extends keyof Concrete<DecisionBucket>
    ? Concrete<DecisionBucketContract>[K] extends Concrete<DecisionBucket>[K]
      ? never
      : K
    : never
}[keyof Concrete<DecisionBucketContract>]
export type DecisionBucketDrift = [
  AssertNever<DecisionFieldsOnlyInContract>,
  AssertNever<DecisionFieldsOnlyInSchema>,
  AssertNever<DecisionFieldsWithChangedType>,
]

type SeriesFieldsOnlyInContract = Exclude<keyof TimeseriesContract, keyof StatsTimeseries>
type SeriesFieldsOnlyInSchema = Exclude<keyof StatsTimeseries, keyof TimeseriesContract>
export type TimeseriesDrift = [
  AssertNever<SeriesFieldsOnlyInContract>,
  AssertNever<SeriesFieldsOnlyInSchema>,
]
