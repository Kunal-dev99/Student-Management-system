'use client'

/**
 * Form-based workflow definition builder.
 *
 * The API takes JSON, but non-technical users shouldn't have to type it. This dialog
 * captures the same shape (key, name, states, transitions, tasks) through structured
 * inputs and serialises it on submit. Power users can flip open the "Show JSON" panel
 * to inspect / paste the equivalent — nothing is hidden.
 */

import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Plus, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'


interface Transition {
  from: string
  on: string
  to: string
  createTask: boolean
  taskTitle: string
  taskAssigneeRole: string
}

const ROLE_OPTIONS = [
  'Supervisor', 'PGR Administrator', 'Institution Administrator', 'Chair',
  'Registry', 'Finance',
]

function slug(s: string): string {
  return s.toLowerCase().trim().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
}

export interface WorkflowBuilderProps {
  open: boolean
  onOpenChange: (v: boolean) => void
  onCreate: (body: Record<string, unknown>) => Promise<void> | void
  submitting?: boolean
}

export function WorkflowBuilder({ open, onOpenChange, onCreate, submitting }: WorkflowBuilderProps) {
  const [key, setKey] = useState('')
  const [name, setName] = useState('')
  const [states, setStates] = useState<string[]>(['open', 'submitted', 'decided'])
  const [initialState, setInitialState] = useState<string>('open')
  const [activate, setActivate] = useState(true)
  const [transitions, setTransitions] = useState<Transition[]>([
    { from: 'open', on: 'submit', to: 'submitted',
      createTask: true, taskTitle: 'Review submission', taskAssigneeRole: 'Supervisor' },
    { from: 'submitted', on: 'decide', to: 'decided',
      createTask: false, taskTitle: '', taskAssigneeRole: 'Supervisor' },
  ])
  const [showJson, setShowJson] = useState(false)

  const definitionBody = useMemo(() => {
    const filteredTransitions = transitions
      .filter((t) => t.from && t.on && t.to)
      .map((t) => {
        const base: Record<string, unknown> = { from: t.from, on: slug(t.on), to: t.to }
        if (t.createTask && t.taskTitle.trim()) {
          base.action = { createTask: {
            title: t.taskTitle.trim(),
            assigneeRole: t.taskAssigneeRole,
          } }
        }
        return base
      })
    return {
      key: slug(key || name),
      name,
      initialState,
      states: states.filter(Boolean),
      transitions: filteredTransitions,
      activate,
    }
  }, [key, name, states, initialState, transitions, activate])

  const nameError = !name.trim() ? 'Name is required' : null
  const stateError = states.length < 2 ? 'At least two states are needed' : null
  const initialError = !states.includes(initialState) ? 'Initial state must be one of the states' : null
  const transitionError = transitions.length === 0
    ? 'At least one transition is needed'
    : transitions.some((t) => !states.includes(t.from) || !states.includes(t.to))
      ? 'Every transition must connect two defined states'
      : null
  const errors = [nameError, stateError, initialError, transitionError].filter(Boolean) as string[]

  const canSubmit = errors.length === 0 && !submitting

  const addState = () => setStates((s) => [...s, ''])
  const setState = (i: number, v: string) => setStates((s) => s.map((x, idx) => idx === i ? slug(v) : x))
  const removeState = (i: number) => setStates((s) => s.filter((_, idx) => idx !== i))

  const addTransition = () => setTransitions((t) => [...t, {
    from: states[0] ?? '', on: '', to: states[1] ?? '',
    createTask: false, taskTitle: '', taskAssigneeRole: 'Supervisor',
  }])
  const setTransition = (i: number, patch: Partial<Transition>) =>
    setTransitions((t) => t.map((x, idx) => idx === i ? { ...x, ...patch } : x))
  const removeTransition = (i: number) => setTransitions((t) => t.filter((_, idx) => idx !== i))

  const submit = async () => {
    if (!canSubmit) return
    await onCreate(definitionBody)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New workflow definition</DialogTitle>
        </DialogHeader>

        <div className="space-y-5">
          {/* Basics */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="wf-name">Name</Label>
              <Input id="wf-name" value={name} onChange={(e) => setName(e.target.value)}
                     placeholder="e.g. Progress review" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wf-key">Key <span className="text-helper">(auto)</span></Label>
              <Input id="wf-key" value={key || slug(name)}
                     onChange={(e) => setKey(slug(e.target.value))}
                     placeholder="progress_review" />
            </div>
          </div>

          {/* States */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>States</Label>
              <Button type="button" size="sm" variant="ghost" onClick={addState}>
                <Plus className="h-3.5 w-3.5 mr-1" /> Add state
              </Button>
            </div>
            <div className="space-y-1.5">
              {states.map((s, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input value={s} onChange={(e) => setState(i, e.target.value)}
                         placeholder="state_name" className="font-mono text-sm" />
                  <Button type="button" size="sm" variant="ghost" onClick={() => removeState(i)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          </div>

          {/* Initial state */}
          <div className="space-y-1.5">
            <Label>Initial state</Label>
            <Select value={initialState} onValueChange={setInitialState}>
              <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
              <SelectContent>
                {states.filter(Boolean).map((s) => (
                  <SelectItem key={s} value={s}>{s}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Transitions */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Transitions</Label>
              <Button type="button" size="sm" variant="ghost" onClick={addTransition}>
                <Plus className="h-3.5 w-3.5 mr-1" /> Add transition
              </Button>
            </div>
            <div className="space-y-2">
              {transitions.map((t, i) => (
                <div key={i} className="rounded-md border border-border/60 bg-surface-2 p-3 space-y-2">
                  <div className="flex flex-wrap items-end gap-2">
                    <div className="space-y-1">
                      <Label className="text-xs">From</Label>
                      <Select value={t.from} onValueChange={(v) => setTransition(i, { from: v })}>
                        <SelectTrigger className="h-8 w-40"><SelectValue placeholder="from" /></SelectTrigger>
                        <SelectContent>
                          {states.filter(Boolean).map((s) => (
                            <SelectItem key={s} value={s}>{s}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">On event</Label>
                      <Input value={t.on} onChange={(e) => setTransition(i, { on: e.target.value })}
                             placeholder="submit" className="h-8 w-40 font-mono text-sm" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">To</Label>
                      <Select value={t.to} onValueChange={(v) => setTransition(i, { to: v })}>
                        <SelectTrigger className="h-8 w-40"><SelectValue placeholder="to" /></SelectTrigger>
                        <SelectContent>
                          {states.filter(Boolean).map((s) => (
                            <SelectItem key={s} value={s}>{s}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <Button type="button" size="sm" variant="ghost" onClick={() => removeTransition(i)}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  <div className="flex items-center gap-2 pt-1">
                    <Checkbox id={`ct-${i}`} checked={t.createTask}
                              onCheckedChange={(v) => setTransition(i, { createTask: v === true })} />
                    <Label htmlFor={`ct-${i}`} className="text-xs font-normal">
                      Also create a task on this transition
                    </Label>
                  </div>
                  {t.createTask && (
                    <div className="flex flex-wrap items-end gap-2 pl-6">
                      <div className="space-y-1">
                        <Label className="text-xs">Task title</Label>
                        <Input value={t.taskTitle}
                               onChange={(e) => setTransition(i, { taskTitle: e.target.value })}
                               placeholder="Review submission" className="h-8 w-56 text-sm" />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">Assign to role</Label>
                        <Select value={t.taskAssigneeRole}
                                onValueChange={(v) => setTransition(i, { taskAssigneeRole: v })}>
                          <SelectTrigger className="h-8 w-48"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {ROLE_OPTIONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  )}
                </div>
              ))}
              {transitions.length === 0 && (
                <p className="text-helper">No transitions yet — add one to make the workflow useful.</p>
              )}
            </div>
          </div>

          {/* Activate */}
          <div className="flex items-center gap-2">
            <Checkbox id="wf-activate" checked={activate}
                      onCheckedChange={(v) => setActivate(v === true)} />
            <Label htmlFor="wf-activate" className="font-normal">
              Activate on create (otherwise the definition is a draft)
            </Label>
          </div>

          {/* Errors */}
          {errors.length > 0 && (
            <div className="rounded-md border border-[hsl(var(--warning)/0.4)] bg-[hsl(var(--warning)/0.05)] px-3 py-2">
              <ul className="text-xs text-[hsl(var(--warning))] space-y-0.5">
                {errors.map((e) => <li key={e}>• {e}</li>)}
              </ul>
            </div>
          )}

          {/* JSON preview */}
          <div className="rounded-md border border-border/60 bg-surface-2/40">
            <button type="button" onClick={() => setShowJson((v) => !v)}
                    className="flex w-full items-center gap-1 px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground">
              {showJson ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              {showJson ? 'Hide JSON' : 'Show JSON (advanced)'}
              <Badge variant="secondary" className="ml-2 text-[10px]">
                {states.filter(Boolean).length} states · {transitions.length} transitions
              </Badge>
            </button>
            {showJson && (
              <pre className="border-t border-border/40 px-3 py-2 text-xs font-mono whitespace-pre-wrap">
                {JSON.stringify(definitionBody, null, 2)}
              </pre>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {submitting ? 'Creating…' : 'Create definition'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
