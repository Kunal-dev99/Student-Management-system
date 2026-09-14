'use client'

import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, GitBranch, Plus, Workflow } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { PageSection } from '@/components/common/PageSection'
import { FilterChips } from '@/components/common/FilterChips'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import {
  useActivateDefinition, useCreateDefinition, useDefinitions, useDispatchEvent,
  useInstances, useStartInstance,
} from '@/features/workflows/api'
import { WorkflowBuilder } from '@/features/workflows/WorkflowBuilder'
import { WorkflowDiagram } from '@/features/workflows/WorkflowDiagram'


export default function WorkflowsPage() {
  const { toast } = useToast()
  const defs = useDefinitions()
  const instances = useInstances()
  const createDef = useCreateDefinition()
  const activate = useActivateDefinition()
  const start = useStartInstance()
  const dispatch = useDispatchEvent()
  const [builderOpen, setBuilderOpen] = useState(false)
  const [events, setEvents] = useState<Record<string, string>>({})
  const [stateFilter, setStateFilter] = useState('all')
  const [openDiagramDefId, setOpenDiagramDefId] = useState<string | null>(null)
  const [openDiagramInstanceId, setOpenDiagramInstanceId] = useState<string | null>(null)
  const defById = useMemo(
    () => new Map((defs.data ?? []).map((d) => [d.id, d])),
    [defs.data],
  )

  const stateOptions = useMemo(() => {
    const states = Array.from(new Set((instances.data ?? []).map((i) => i.currentState))).sort()
    return [{ value: 'all', label: 'All' }, ...states.map((s) => ({ value: s, label: s }))]
  }, [instances.data])
  const filteredInstances = (instances.data ?? []).filter(
    (i) => stateFilter === 'all' || i.currentState === stateFilter,
  )

  const err = (e: unknown) => toast({ title: 'Failed', description: (e as Error).message, variant: 'destructive' })

  return (
    <>
      <PageHeader title="Workflows" />
      <div className="px-6 pb-6 space-y-4">
        <WorkflowBuilder
          open={builderOpen}
          onOpenChange={setBuilderOpen}
          submitting={createDef.isPending}
          onCreate={async (body) => {
            try {
              const d = await createDef.mutateAsync(body as Parameters<typeof createDef.mutateAsync>[0])
              toast({ title: `Created ${d.key} v${d.version}` })
              setBuilderOpen(false)
            } catch (e) { err(e) }
          }}
        />

        <PageSection
          icon={Workflow}
          title={`Definitions${defs.data ? ` (${defs.data.length})` : ''}`}
          accent="primary"
          actions={
            <Button size="sm" onClick={() => setBuilderOpen(true)}>
              <Plus className="h-3.5 w-3.5 mr-1" /> New definition
            </Button>
          }
        >
          {defs.isLoading ? <Skeleton className="h-16 w-full" /> : (
            <div className="space-y-2 mb-4">
              {defs.data?.map((d) => {
                const diagramOpen = openDiagramDefId === d.id
                return (
                  <div key={d.id} className="border-b border-border/60 last:border-0 pb-2 last:pb-0">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 flex-wrap">
                        <button type="button" className="inline-flex items-center gap-1 text-sm font-medium hover:text-primary"
                          onClick={() => setOpenDiagramDefId(diagramOpen ? null : d.id)}>
                          {diagramOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                          {d.name}
                        </button>
                        <span className="text-helper font-mono">{d.key} v{d.version}</span>
                        {d.active ? <Badge variant="success">active</Badge> : <Badge variant="outline">inactive</Badge>}
                        <span className="text-helper">{d.states.join(' → ')}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        {!d.active && <Button size="sm" variant="ghost" onClick={async () => { try { await activate.mutateAsync(d.id); toast({ title: 'Activated' }) } catch (e) { err(e) } }}>Activate</Button>}
                        {d.active && <Button size="sm" variant="secondary" onClick={async () => { try { await start.mutateAsync(d.key); toast({ title: 'Instance started' }) } catch (e) { err(e) } }}>Start instance</Button>}
                      </div>
                    </div>
                    {diagramOpen && (
                      <WorkflowDiagram
                        className="mt-2"
                        states={d.states}
                        transitions={d.transitions}
                        initialState={d.initialState}
                      />
                    )}
                  </div>
                )
              })}
              {defs.data && defs.data.length === 0 && <p className="text-helper">No definitions yet.</p>}
            </div>
          )}
        </PageSection>

        <PageSection
          icon={GitBranch}
          title={`Instances${instances.data ? ` (${instances.data.length})` : ''}`}
          accent="accent"
          description="Live workflow instances. Dispatch an event to advance one."
        >
          {instances.isLoading ? <Skeleton className="h-16 w-full" /> : (
            <div className="space-y-3">
              {instances.data && instances.data.length > 0 && (
                <FilterChips label="State:" options={stateOptions} value={stateFilter} onChange={setStateFilter} />
              )}
              <div className="space-y-2">
              {filteredInstances.map((i) => {
                const def = defById.get(i.definitionId)
                const diagramOpen = openDiagramInstanceId === i.id
                return (
                  <div key={i.id} className="border-b border-border/60 last:border-0 pb-2 last:pb-0">
                    <div className="flex items-center justify-between">
                      <button type="button" className="flex items-center gap-2 hover:text-primary disabled:hover:text-inherit"
                        disabled={!def}
                        onClick={() => def && setOpenDiagramInstanceId(diagramOpen ? null : i.id)}>
                        {def && (diagramOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />)}
                        <span className="text-sm font-mono">{i.id.slice(0, 8)}</span>
                        <Badge variant="info">{i.currentState}</Badge>
                        <span className="text-helper">{i.aggregateType}</span>
                      </button>
                      <div className="flex items-center gap-1">
                        <Input placeholder="event" className="h-8 w-32" value={events[i.id] ?? ''} onChange={(e) => setEvents((s) => ({ ...s, [i.id]: e.target.value }))} />
                        <Button size="sm" variant="ghost" disabled={!events[i.id] || dispatch.isPending}
                          onClick={async () => { try { await dispatch.mutateAsync({ id: i.id, event: events[i.id] }); toast({ title: 'Event dispatched' }); setEvents((s) => ({ ...s, [i.id]: '' })) } catch (e) { err(e) } }}>Send</Button>
                      </div>
                    </div>
                    {diagramOpen && def && (
                      <WorkflowDiagram
                        className="mt-2"
                        states={def.states}
                        transitions={def.transitions}
                        initialState={def.initialState}
                        currentState={i.currentState}
                      />
                    )}
                  </div>
                )
              })}
              {instances.data && instances.data.length === 0 && <p className="text-helper">No running instances. Start one from a definition above.</p>}
              {instances.data && instances.data.length > 0 && filteredInstances.length === 0 && (
                <p className="text-helper">No instances match this state filter.</p>
              )}
              </div>
            </div>
          )}
        </PageSection>
      </div>
    </>
  )
}
