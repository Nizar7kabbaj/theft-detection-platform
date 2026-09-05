import { ROLE_VALUES } from "@/features/users/schemas/user"

export const USER_FILTERS_COOKIE_NAME = "user_filters"
export const USER_FILTERS_COOKIE_MAX_AGE = 60 * 60 * 24 * 30

const MAX_COOKIE_LENGTH = 256
const MAX_SEARCH_LENGTH = 50
const MAX_ID_LENGTH = 64
const STATUS_VALUES = ["all", "active", "disabled"] as const

export type StatusFilter = (typeof STATUS_VALUES)[number]

export type UserFilters = {
  search: string
  role: string
  status: StatusFilter
  selected: string
  page: number
  access: boolean
}

export const EMPTY_FILTERS: UserFilters = {
  search: "",
  role: "",
  status: "all",
  selected: "",
  page: 0,
  access: false,
}

function knownRole(value: string | null): string {
  if (value === null) {
    return ""
  }
  return ROLE_VALUES.some((role) => role === value) ? value : ""
}

function knownStatus(value: string | null): StatusFilter {
  if (value === null) {
    return "all"
  }
  return STATUS_VALUES.find((status) => status === value) ?? "all"
}

function safeId(value: string | null): string {
  if (value === null || value.length > MAX_ID_LENGTH) {
    return ""
  }
  return /^[a-f0-9-]+$/i.test(value) ? value : ""
}
const MAX_PAGE = 10000

function safePage(value: string | null): number {
  if (value === null) {
    return 0
  }
  const parsed = Number.parseInt(value, 10)
  if (Number.isNaN(parsed) || parsed < 0 || parsed > MAX_PAGE) {
    return 0
  }
  return parsed
}

export function parseStoredFilters(value: string | undefined | null): UserFilters {
  if (value === undefined || value === null || value === "" || value.length > MAX_COOKIE_LENGTH) {
    return EMPTY_FILTERS
  }
  let decoded: string
  try {
    decoded = decodeURIComponent(value)
  } catch {
    return EMPTY_FILTERS
  }
  const search = new URLSearchParams(decoded)
  return {
    search: (search.get("search") ?? "").slice(0, MAX_SEARCH_LENGTH),
    role: knownRole(search.get("role")),
    status: knownStatus(search.get("status")),
    selected: safeId(search.get("selected")),
    page: safePage(search.get("page")),
    access: search.get("access") === "1",
  }
}

export function serializeFilters(filters: UserFilters): string {
  const search = new URLSearchParams()
  if (filters.search !== "") {
    search.set("search", filters.search.slice(0, MAX_SEARCH_LENGTH))
  }
  if (filters.role !== "") {
    search.set("role", filters.role)
  }
  if (filters.status !== "all") {
    search.set("status", filters.status)
  }
  if (filters.selected !== "") {
    search.set("selected", filters.selected)
  }
  if (filters.page > 0) {
    search.set("page", String(filters.page))
  }
  if (filters.access) {
    search.set("access", "1")
  }
  return encodeURIComponent(search.toString())
}
