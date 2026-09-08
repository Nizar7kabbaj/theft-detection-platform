import { cache } from "react"
import {
  type PolicyResponse,
  type PolicyRevision,
  policyHistorySchema,
  policyResponseSchema,
} from "@/features/policy/schemas/policy"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export const fetchPolicy = cache(function fetchPolicy(): Promise<PolicyResponse> {
  return serverRead("/api/v1/policy/detection", { schema: policyResponseSchema })
})

export const fetchPolicyHistory = cache(function fetchPolicyHistory(): Promise<PolicyRevision[]> {
  return serverRead("/api/v1/policy/detection/history", { schema: policyHistorySchema })
})
