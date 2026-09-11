'use client'

/**
 * Supervisor-side messaging panel — mirror of the student's MessagesPanel but with the
 * axes flipped: threads listed per student instead of per supervisor, sends go through
 * the /supervision/messages endpoint. Same visual language.
 */

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Send } from 'lucide-react'
import { api } from '@/shared/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { PageSection } from '@/components/common/PageSection'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/components/ui/use-toast'
import { cn } from '@/lib/utils'

interface SupervisorThread {
  studentId: string
  studentName: string
  studentRef: string
  role: string
  lastMessage: {
    body: string | null
    authorRole: string | null
    createdAt: string | null
  } | null
  unreadCount: number
  totalMessages: number
}

interface SupervisorMessage {
  id: string
  authorRole: 'student' | 'supervisor'
  body: string
  createdAt: string | null
  readAt: string | null
}

const useSupervisorThreads = () =>
  useQuery({
    queryKey: ['supervision', 'messages'],
    queryFn: () => api.get<SupervisorThread[]>('/supervision/messages'),
  })

const useSupervisorThreadMessages = (studentId: string | null) =>
  useQuery({
    queryKey: ['supervision', 'messages', studentId],
    queryFn: () => api.get<SupervisorMessage[]>(`/supervision/messages/${studentId}`),
    enabled: !!studentId,
  })

function useSendSupervisorMessage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { studentId: string; body: string }) =>
      api.post<SupervisorMessage>('/supervision/messages', args),
    onSuccess: (_, args) => {
      qc.invalidateQueries({ queryKey: ['supervision', 'messages'] })
      qc.invalidateQueries({ queryKey: ['supervision', 'messages', args.studentId] })
    },
  })
}

export function SupervisorMessagesPanel() {
  const { data: threads, isLoading } = useSupervisorThreads()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedId && threads && threads.length > 0) {
      setSelectedId(threads[0].studentId)
    }
  }, [threads, selectedId])

  return (
    <PageSection icon={MessageSquare} title="Student messages" accent="accent">
      {isLoading ? (
        <p className="text-helper">Loading messages…</p>
      ) : !threads || threads.length === 0 ? (
        <p className="text-helper">No students to message yet.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-[minmax(0,220px)_1fr] min-h-[320px]">
          <ThreadList
            threads={threads}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
          {selectedId && (
            <ThreadView
              key={selectedId}
              studentId={selectedId}
              studentName={threads.find((t) => t.studentId === selectedId)?.studentName}
            />
          )}
        </div>
      )}
    </PageSection>
  )
}

function ThreadList({
  threads, selectedId, onSelect,
}: {
  threads: SupervisorThread[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  return (
    <div className="border border-border rounded-md overflow-hidden max-h-[400px] overflow-y-auto">
      {threads.map((t) => {
        const active = t.studentId === selectedId
        return (
          <button
            key={t.studentId}
            type="button"
            onClick={() => onSelect(t.studentId)}
            className={cn(
              'w-full text-left px-3 py-2.5 border-b border-border/60 last:border-b-0 transition-colors',
              active ? 'bg-primary/[0.06]' : 'hover:bg-muted/60',
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium truncate">{t.studentName}</p>
              {t.unreadCount > 0 && (
                <Badge variant="destructive" className="h-5 text-[10px]">
                  {t.unreadCount}
                </Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              <span className="num">{t.studentRef}</span>
              <span className="mx-1">·</span>
              <span className="capitalize">{t.role}</span>
            </p>
            {t.lastMessage?.body && (
              <p className="text-xs text-muted-foreground mt-1 truncate">
                {t.lastMessage.authorRole === 'supervisor' ? 'You: ' : ''}
                {t.lastMessage.body}
              </p>
            )}
          </button>
        )
      })}
    </div>
  )
}

function ThreadView({
  studentId, studentName,
}: {
  studentId: string
  studentName?: string
}) {
  const { data: messages, isLoading } = useSupervisorThreadMessages(studentId)
  const send = useSendSupervisorMessage()
  const [draft, setDraft] = useState('')
  const { toast } = useToast()

  const handleSend = async () => {
    const trimmed = draft.trim()
    if (!trimmed) return
    try {
      await send.mutateAsync({ studentId, body: trimmed })
      setDraft('')
    } catch {
      toast({ title: 'Could not send', description: 'Please try again.', variant: 'destructive' })
    }
  }

  return (
    <div className="flex flex-col border border-border rounded-md min-h-[320px]">
      <div className="px-3 py-2 border-b border-border/60 text-sm font-medium">
        {studentName}
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2 max-h-[360px]">
        {isLoading ? (
          <p className="text-helper text-xs">Loading…</p>
        ) : !messages || messages.length === 0 ? (
          <p className="text-helper text-xs">
            No messages yet. Break the ice.
          </p>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={cn(
                'max-w-[80%] rounded-md px-3 py-2 text-sm',
                m.authorRole === 'supervisor'
                  ? 'ml-auto bg-primary/10 border border-primary/20'
                  : 'mr-auto bg-muted/50 border border-border/60',
              )}
            >
              <p className="whitespace-pre-wrap">{m.body}</p>
              {m.createdAt && (
                <p className="text-[10px] text-muted-foreground mt-1 num">
                  {new Date(m.createdAt).toLocaleString()}
                </p>
              )}
            </div>
          ))
        )}
      </div>
      <div className="border-t border-border/60 p-2 flex items-end gap-2">
        <Textarea
          rows={2}
          placeholder={`Reply to ${studentName ?? 'this student'}…`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="text-sm resize-none"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              void handleSend()
            }
          }}
        />
        <Button
          size="sm"
          onClick={handleSend}
          disabled={send.isPending || !draft.trim()}
        >
          <Send className="h-3.5 w-3.5 mr-1" />
          Send
        </Button>
      </div>
    </div>
  )
}
