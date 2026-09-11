'use client'

import { MessageSquare } from 'lucide-react'
import { MessagesPanel } from '@/features/portal/MessagesPanel'
import { SupervisorMessagesPanel } from '@/features/supervision/SupervisorMessagesPanel'
import { useAuth } from '@/shared/auth/AuthContext'

/**
 * One page, two panels — picked by role. Students see their supervisor threads;
 * supervisors see one thread per current student.
 */
export default function MessagesRoute() {
  const { principal } = useAuth()
  const roles = principal?.roles ?? []
  const isSupervisor = roles.includes('Supervisor')
  const isStudent = roles.includes('Student')

  return (
    <div className="p-6 space-y-4">
      <header>
        <h1 className="text-page-title flex items-center gap-2">
          <MessageSquare className="h-6 w-6 text-primary" />
          Messages
        </h1>
        <p className="text-helper mt-1">
          {isSupervisor
            ? 'Direct messages with your current students.'
            : 'Direct messages with your supervisors.'}
        </p>
      </header>
      {/* Supervisors also holding the Student role (rare — an academic doing their own
          PhD) get the supervisor panel first; a "See student view" toggle could come
          later if the demand's real. */}
      {isSupervisor ? <SupervisorMessagesPanel /> : isStudent ? <MessagesPanel /> : (
        <p className="text-helper">No messaging surface for your role.</p>
      )}
    </div>
  )
}
