'use client'

/**
 * Progressive reveal primitives for composer blocks.
 *
 * The point of the whole feature is that the answer arrives — not that it snaps into
 * existence. Blocks fade in one at a time, numbers tick up from zero, and SVG paths draw
 * themselves left to right. Recharts animates its own charts on mount; the code here
 * covers everything else.
 *
 * Deliberately CSS-first — no animation library. The runtime cost is one keyframe and a
 * requestAnimationFrame loop per counter. Adding motion here should never be the reason a
 * page feels slow.
 */

import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

/** Block-level stagger: each child appears ~150ms after the previous one. */
export function Reveal({
  index = 0,
  className,
  children,
  duration = 500,
  stagger = 150,
}: {
  index?: number
  className?: string
  children: React.ReactNode
  duration?: number
  stagger?: number
}) {
  return (
    <div
      className={cn('composer-reveal', className)}
      style={{
        animationDelay: `${index * stagger}ms`,
        animationDuration: `${duration}ms`,
      }}
    >
      {children}
    </div>
  )
}

/**
 * A number that ticks up from 0 to `value` on mount.
 *
 * The duration adapts to the magnitude — very small counts finish faster than very large
 * ones — so a 3 does not spend a full second at "1". Values that are not numbers pass
 * through unchanged, so this can wrap arbitrary KPI cells safely.
 */
export function CountUp({
  value,
  duration = 700,
  delay = 0,
  format = (n) => n.toLocaleString(),
}: {
  value: number | string
  duration?: number
  delay?: number
  format?: (n: number) => string
}) {
  const target = typeof value === 'number' ? value : parseFloat(String(value))
  const [display, setDisplay] = useState<number>(0)

  useEffect(() => {
    if (Number.isNaN(target) || !Number.isFinite(target)) return

    // Small counts do not need the full duration; large ones deserve it.
    const scaled = Math.min(duration, Math.max(300, Math.abs(target) * 40))

    let frame = 0
    let startedAt = 0
    let cancelled = false

    const tick = (now: number) => {
      if (cancelled) return
      if (!startedAt) startedAt = now
      const elapsed = now - startedAt - delay
      if (elapsed < 0) {
        frame = requestAnimationFrame(tick)
        return
      }
      const progress = Math.min(1, elapsed / scaled)
      // easeOutCubic — settles rather than smacks into the final value.
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplay(target * eased)
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => {
      cancelled = true
      cancelAnimationFrame(frame)
    }
  }, [target, duration, delay])

  if (Number.isNaN(target) || !Number.isFinite(target)) {
    return <>{value}</>
  }
  const rounded = Number.isInteger(target) ? Math.round(display) : Math.round(display * 10) / 10
  return <>{format(rounded)}</>
}
