'use client'

import { useState } from 'react'
import { GitBranch, Workflow } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import {
  useActivateDefinition, useCreateDefinition, useDefinitions, useDispatchEvent,
  useInstances, useStartInstance,
} from '@/features/workflows/api'

const TEMPLATE = JSON.stringify({
  key: 'review', name: 'Progress review', initialState: 'open',
  states: ['open', 'submitted', 'decided'],
  transitions: [
    { from: 'open', on: 'submit', to: 'submitted', action: { createTask: { title: 'Review submission', assigneeRole: 'Supervisor' } } },
    { from: 'submitted', on: 'decide', to: 'decided' },
  ],
  activate: true,
}, null, 2)

export default function WorkflowsPage() {
  const { toast } = useToast()
  const defs = useDefinitions()
  const instances = useInstances()
  const createDef = useCreateDefinition()
  const activate = useActivateDefinition()
  const start = useStartInstance()
  const dispatch = useDispatchEvent()
  const [json, setJson] = useState(TEMPLATE)
  const [events, setEvents] = useState<Record<string, string>>({})

  const err = (e: unknown) => toast({ title: 'Failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <>
      <PageHeader title="Workflows" description="Configurable, versioned state machines — defined in data." />
      <div className="px-6 pb-6 space-y-4">
        <PageSection icon={Workflow} title="Definitions" accent="primary">
          {defs.isLoading ? <Skeleton className="h-16 w-full" /> : (
            <div className="space-y-2 mb-4">
              {defs.data?.map((d) => (
                <div key={d.id} className="flex items-center justify-between border-b border-border/60 last:border-0 pb-2 last:pb-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium">{d.name}</span>
                    <span className="text-helper font-mono">{d.key} v{d.version}</span>
                    {d.active ? <Badge variant="success">active</Badge> : <Badge variant="outline">inactive</Badge>}
                    <span className="text-helper">{d.states.join(' → ')}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    {!d.active && <Button size="sm" variant="ghost" onClick={async () => { try { await activate.mutateAsync(d.id); toast({ title: 'Activated' }) } catch (e) { err(e) } }}>Activate</Button>}
                    {d.active && <Button size="sm" variant="secondary" onClick={async () => { try { await start.mutateAsync(d.key); toast({ title: 'Instance started' }) } catch (e) { err(e) } }}>Start instance</Button>}
                  </div>
                </div>
              ))}
              {defs.data && defs.data.length === 0 && <p className="text-helper">No definitions yet.</p>}
            </div>
          )}
          <div className="pt-2 border-t border-border">
            <p className="text-label mb-1">New definition (JSON)</p>
            <Textarea rows={10} value={json} onChange={(e) => setJson(e.target.value)} className="font-mono text-xs" />
            <Button size="sm" className="mt-2" disabled={createDef.isPending}
              onClick={async () => {
                try { const body = JSON.parse(json); const d = await createDef.mutateAsync(body); toast({ title: `Created ${d.key} v${d.version}` }) }
                catch (e) { err(e instanceof SyntaxError ? new Error('Invalid JSON') : e) }
              }}>Create definition</Button>
          </div>
        </PageSection>

        <PageSection icon={GitBranch} title="Instances" accent="accent">
          {instances.isLoading ? <Skeleton className="h-16 w-full" /> : (
            <div className="space-y-2">
              {instances.data?.map((i) => (
                <div key={i.id} className="flex items-center justify-between border-b border-border/60 last:border-0 pb-2 last:pb-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-mono">{i.id.slice(0, 8)}</span>
                    <Badge variant="info">{i.currentState}</Badge>
                    <span className="text-helper">{i.aggregateType}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Input placeholder="event" className="h-8 w-32" value={events[i.id] ?? ''} onChange={(e) => setEvents((s) => ({ ...s, [i.id]: e.target.value }))} />
                    <Button size="sm" variant="ghost" disabled={!events[i.id] || dispatch.isPending}
                      onClick={async () => { try { await dispatch.mutateAsync({ id: i.id, event: events[i.id] }); toast({ title: 'Event dispatched' }); setEvents((s) => ({ ...s, [i.id]: '' })) } catch (e) { err(e) } }}>Send</Button>
                  </div>
                </div>
              ))}
              {instances.data && instances.data.length === 0 && <p className="text-helper">No running instances. Start one from a definition above.</p>}
            </div>
          )}
        </PageSection>
      </div>
    </>
  )
}
