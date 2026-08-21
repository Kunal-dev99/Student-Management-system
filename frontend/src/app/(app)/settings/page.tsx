'use client'

import { Settings } from 'lucide-react'
import { ComingSoon } from '@/components/common/ComingSoon'

export default function Page() {
  return (
    <ComingSoon
      title="Settings"
      description="Programme, workflow, and rule configuration."
      icon={Settings}
      task="Phase 2"
    />
  )
}
