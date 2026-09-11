'use client'

/**
 * Student ↔ supervisor messaging panel embedded in the portal.
 *
 * Left column lists supervisor threads (one row per current supervisor). Selecting a
 * thread opens messages on the right and marks supervisor-authored messages as read
 * when the API returns them. Bottom of the right pane is a compose box.
 */

import { useEffect, useState } from 'react'
import { MessageSquare, Send } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { PageSection } from '@/components/common/PageSection'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/components/ui/use-toast'
import { cn } from '@/lib/utils'
import {
  useMessageThreads,
  useSendMessage,
  useThreadMessages,
  type MessageThread,
} from './api'

export function MessagesPanel() {
  const { data: threads, isLoading } = useMessageThreads()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // Auto-select the first thread when the list first loads.
  useEffect(() => {
    if (!selectedId && threads && threads.length > 0) {
      setSelectedId(threads[0].supervisorPersonId)
    }
  }, [threads, selectedId])

  return (
    <PageSection icon={MessageSquare} title="My messages" accent="accent">
      {isLoading ? (
        <p className="text-helper">Loading messages…</p>
      ) : !threads || threads.length === 0 ? (
        <p className="text-helper">No supervisors to message yet.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-[minmax(0,220px)_1fr] min-h-[280px]">
          <ThreadList
            threads={threads}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
          {selectedId && (
            <ThreadView
              key={selectedId}
              supervisorPersonId={selectedId}
              supervisorName={threads.find((t) => t.supervisorPersonId === selectedId)?.supervisorName}
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
  threads: MessageThread[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  return (
    <div className="border border-border rounded-md overflow-hidden">
      {threads.map((t) => {
        const active = t.supervisorPersonId === selectedId
        return (
          <button
            key={t.supervisorPersonId}
            type="button"
            onClick={() => onSelect(t.supervisorPersonId)}
            className={cn(
              'w-full text-left px-3 py-2.5 border-b border-border/60 last:border-b-0 transition-colors',
              active ? 'bg-primary/[0.06]' : 'hover:bg-muted/60',
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium truncate">{t.supervisorName}</p>
              {t.unreadCount > 0 && (
                <Badge variant="destructive" className="h-5 text-[10px]">
                  {t.unreadCount}
                </Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground capitalize">{t.role}</p>
            {t.lastMessage?.body && (
              <p className="text-xs text-muted-foreground mt-1 truncate">
                {t.lastMessage.authorRole === 'student' ? 'You: ' : ''}
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
  supervisorPersonId, supervisorName,
}: {
  supervisorPersonId: string
  supervisorName?: string
}) {
  const { data: messages, isLoading } = useThreadMessages(supervisorPersonId)
  const send = useSendMessage()
  const [draft, setDraft] = useState('')
  const { toast } = useToast()

  const handleSend = async () => {
    const trimmed = draft.trim()
    if (!trimmed) return
    try {
      await send.mutateAsync({ supervisorPersonId, body: trimmed })
      setDraft('')
    } catch {
      toast({ title: 'Could not send', description: 'Please try again.', variant: 'destructive' })
    }
  }

  return (
    <div className="flex flex-col border border-border rounded-md min-h-[280px]">
      <div className="px-3 py-2 border-b border-border/60 text-sm font-medium">
        {supervisorName}
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2 max-h-[320px]">
        {isLoading ? (
          <p className="text-helper text-xs">Loading…</p>
        ) : !messages || messages.length === 0 ? (
          <p className="text-helper text-xs">
            No messages yet. Say hello.
          </p>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={cn(
                'max-w-[80%] rounded-md px-3 py-2 text-sm',
                m.authorRole === 'student'
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
          placeholder={`Message ${supervisorName ?? 'your supervisor'}…`}
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
