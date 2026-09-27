const ZONE_ENV = "STORE_TIME_ZONE"

let serverZone: string | undefined
let clientZone: string | undefined
const formatters = new Map<string, Intl.DateTimeFormat>()

export const STORE_TIME_LABEL = "store time"

function assertTimeZone(value: string | undefined): string {
  if (value === undefined || value === "") {
    throw new Error(`${ZONE_ENV} is not set`)
  }
  try {
    new Intl.DateTimeFormat("en-CA", { timeZone: value })
  } catch {
    throw new Error(`${ZONE_ENV} is not a known zone: ${value}`)
  }
  return value
}

export function setStoreTimeZone(zone: string): void {
  if (typeof window === "undefined" || clientZone === zone) {
    return
  }
  clientZone = assertTimeZone(zone)
}

export function storeTimeZone(): string {
  if (typeof window === "undefined") {
    serverZone ??= assertTimeZone(process.env.STORE_TIME_ZONE)
    return serverZone
  }
  if (clientZone === undefined) {
    throw new Error("store time zone read before it was set")
  }
  return clientZone
}

export function storeFormatter(
  locale: string,
  options: Intl.DateTimeFormatOptions,
): Intl.DateTimeFormat {
  const zone = storeTimeZone()
  const key = `${locale}|${zone}|${JSON.stringify(options)}`
  let formatter = formatters.get(key)
  if (formatter === undefined) {
    formatter = new Intl.DateTimeFormat(locale, { ...options, timeZone: zone })
    formatters.set(key, formatter)
  }
  return formatter
}
