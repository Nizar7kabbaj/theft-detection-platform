function resolveZone(): string {
  const configured = process.env.NEXT_PUBLIC_STORE_TIME_ZONE
  if (configured === undefined || configured === "") {
    throw new Error("NEXT_PUBLIC_STORE_TIME_ZONE is not set")
  }
  try {
    new Intl.DateTimeFormat("en-CA", { timeZone: configured })
  } catch {
    throw new Error(`NEXT_PUBLIC_STORE_TIME_ZONE is not a known zone: ${configured}`)
  }
  return configured
}

export const STORE_TIME_ZONE = resolveZone()
export const STORE_TIME_LABEL = "store time"
