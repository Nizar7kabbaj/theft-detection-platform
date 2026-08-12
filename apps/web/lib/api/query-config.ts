const SECOND = 1000
const MINUTE = 60 * SECOND
const HOUR = 60 * MINUTE

export const ALERT_LIST_STALE_MS = 5 * SECOND
export const ALERT_LIST_GC_MS = MINUTE

export const ALERT_DETAIL_STALE_MS = 30 * SECOND
export const ALERT_DETAIL_GC_MS = 5 * MINUTE

export const CAMERA_ROSTER_STALE_MS = 5 * MINUTE
export const CAMERA_ROSTER_GC_MS = 30 * MINUTE

export const ANALYTICS_STALE_MS = HOUR
export const ANALYTICS_GC_MS = 24 * HOUR

export const DEFAULT_STALE_MS = 30 * SECOND
export const DEFAULT_GC_MS = 5 * MINUTE
export const MAX_RETRY_COUNT = 2
export const RETRY_BASE_DELAY_MS = SECOND
export const RETRY_MAX_DELAY_MS = 30 * SECOND
