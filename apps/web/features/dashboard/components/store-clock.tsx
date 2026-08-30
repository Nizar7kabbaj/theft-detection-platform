"use client"
import { useEffect, useState } from "react"

const PLACEHOLDER = "--:--:--"

function utcTime(now: Date): string {
  const hours = String(now.getUTCHours()).padStart(2, "0")
  const minutes = String(now.getUTCMinutes()).padStart(2, "0")
  const seconds = String(now.getUTCSeconds()).padStart(2, "0")
  return `${hours}:${minutes}:${seconds}`
}

export function StoreClock() {
  const [time, setTime] = useState<string>(PLACEHOLDER)

  useEffect(() => {
    setTime(utcTime(new Date()))
    const id = window.setInterval(() => {
      setTime(utcTime(new Date()))
    }, 1000)
    return () => {
      window.clearInterval(id)
    }
  }, [])

  return <span className="font-mono text-foreground text-lg leading-none tabular-nums">{time}</span>
}
