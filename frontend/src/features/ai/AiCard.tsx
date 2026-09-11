'use client'

/**
 * Standard shell for any AI-produced element in the app.
 *
 * Slots: title, provenance chip, the AI's own content, and an optional action row that
 * routes through the app's ordinary control path (the AI proposes; the user acts). This
 * is the visual reminder that AI is a layer — every action here is one the user would
 * have taken anyway, done through the same paths as if the model didn't exist.
 */

import { type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { AiSparkle } from './AiSparkle'

export function AiCard({
  title, source, model, children, action, className,
}: {
  title: string
  source: 'model' | 'fallback'
  model?: string | null
  children: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <section className={cn('card-elevated p-4 space-y-3', className)}>
      <header className="flex items-center gap-2">
        <h3 className="text-sm font-medium">{title}</h3>
        <AiSparkle source={source} model={model} />
      </header>
      <div>{children}</div>
      {action && <div className="pt-1">{action}</div>}
    </section>
  )
}
