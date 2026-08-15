"use client"
import { useEffect } from "react"
export function useCommandKey(onOpen: () => void) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "k" || !(event.ctrlKey || event.metaKey) || event.altKey) {
        return
      }
      event.preventDefault()
      onOpen()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [onOpen])
}
