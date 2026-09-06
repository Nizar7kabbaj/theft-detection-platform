"use client"
import { useEffect, useState } from "react"
import { STORE_TIME_ZONE } from "@/lib/time/zone"

const PLACEHOLDER = "--:--:--"

function storeTime(now: Date): string {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: STORE_TIME_ZONE,
  }).format(now)
}

export function StoreClock() {
  const [time, setTime] = useState<string>(PLACEHOLDER)
  useEffect(() => {
    setTime(storeTime(new Date()))
    const id = window.setInterval(() => {
      setTime(storeTime(new Date()))
    }, 1000)
    return () => {
      window.clearInterval(id)
    }
  }, [])
  return <span className="font-mono text-foreground text-lg leading-none tabular-nums">{time}</span>
}
