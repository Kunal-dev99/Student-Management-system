'use client'

/**
 * "Institution policy" tab — the numbers that change real platform behaviour:
 * supervisor capacity guard, overdue-meeting flags, part-time rescaling, funding
 * gap tolerance, the institution-wide email switch, and the assistant LLM gate.
 *
 * The registry on the backend is the source of truth: groups, labels, types,
 * ranges and defaults all arrive from GET /settings/institution. Validation
 * failures (400) carry a human message which we surface verbatim.
 */

import { useEffect, useState } from 'react'
import {
  Banknote, GraduationCap, Mail, SlidersHorizontal, Sparkles, Users, type LucideIcon,
} from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import {
  useInstitutionSettings, useResetInstitutionSetting, useSetInstitutionSetting,
  type InstitutionSetting, type SettingValue,
} from '@/features/settings/api'

const GROUP_ICONS: Record<string, LucideIcon> = {
  'Supervision policy': Users,
  'Student lifecycle': GraduationCap,
  'Funding integrity': Banknote,
  Email: Mail,
  Assistant: Sparkles,
}

const fmt = (s: InstitutionSetting, v: SettingValue) =>
  s.type === 'bool' ? (v ? 'On' : 'Off') : String(v)

function SettingRow({ setting }: { setting: InstitutionSetting }) {
  const { toast } = useToast()
  const save = useSetInstitutionSetting()
  const reset = useResetInstitutionSetting()

  // Draft state: bools live as booleans, everything else as text so partial input is possible.
  const [draft, setDraft] = useState<string | boolean>(
    setting.type === 'bool' ? (setting.value as boolean) : String(setting.value),
  )
  useEffect(() => {
    setDraft(setting.type === 'bool' ? (setting.value as boolean) : String(setting.value))
  }, [setting.value, setting.type])

  const numeric = setting.type === 'int' || setting.type === 'float'
  const numberInvalid =
    numeric && (String(draft).trim() === '' || Number.isNaN(Number(draft)))
  const dirty =
    setting.type === 'bool' ? draft !== setting.value : String(draft) !== String(setting.value)

  const submit = async () => {
    const value: SettingValue =
      setting.type === 'bool' ? (draft as boolean)
        : numeric ? Number(draft)
          : String(draft)
    try {
      await save.mutateAsync({ key: setting.key, value })
      toast({ title: `${setting.label} saved` })
    } catch (e) {
      // 400 carries the registry's human message ("… must be at most 50") — verbatim.
      toast({ title: 'Not saved', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  const resetToDefault = async () => {
    try {
      await reset.mutateAsync(setting.key)
      toast({ title: `${setting.label} reset to default (${fmt(setting, setting.default)})` })
    } catch (e) {
      toast({ title: 'Reset failed', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <div className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 sm:max-w-[55%]">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">{setting.label}</p>
          {setting.overridden && <Badge variant="warning">Overridden</Badge>}
        </div>
        <p className="text-helper mt-0.5">{setting.description}</p>
      </div>
      <div className="flex flex-col items-start sm:items-end gap-1.5 shrink-0">
        <div className="flex items-center gap-2">
          {setting.type === 'bool' ? (
            <div className="flex items-center gap-2 h-9">
              <Checkbox
                id={`set-${setting.key}`}
                checked={draft === true}
                onCheckedChange={(v) => setDraft(v === true)}
              />
              <Label htmlFor={`set-${setting.key}`} className="cursor-pointer font-normal">
                {draft ? 'On' : 'Off'}
              </Label>
            </div>
          ) : (
            <Input
              id={`set-${setting.key}`}
              type={numeric ? 'number' : 'text'}
              min={setting.min ?? undefined}
              max={setting.max ?? undefined}
              step={setting.type === 'float' ? 0.1 : 1}
              value={String(draft)}
              onChange={(e) => setDraft(e.target.value)}
              className={numeric ? 'w-32' : 'w-56'}
            />
          )}
          <Button
            size="sm"
            disabled={!dirty || numberInvalid || save.isPending}
            onClick={submit}
          >
            {save.isPending ? 'Saving…' : 'Save'}
          </Button>
          {setting.overridden && (
            <Button size="sm" variant="ghost" disabled={reset.isPending} onClick={resetToDefault}>
              Reset to default
            </Button>
          )}
        </div>
        <p className="text-helper">
          Default: {fmt(setting, setting.default)}
          {setting.min !== null && setting.max !== null && ` · range ${setting.min}–${setting.max}`}
        </p>
      </div>
    </div>
  )
}

export function InstitutionPolicyTab() {
  const { data, isLoading } = useInstitutionSettings()

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-helper">
        These settings change live platform behaviour institution-wide — capacity warnings,
        overdue flags, funding checks and outgoing email. A change takes effect on the next
        request; nothing needs restarting.
      </p>
      {data?.groups.map((g) => (
        <PageSection
          key={g.group}
          icon={GROUP_ICONS[g.group] ?? SlidersHorizontal}
          title={g.group}
          accent="primary"
        >
          <div className="divide-y divide-border/40">
            {g.settings.map((s) => <SettingRow key={s.key} setting={s} />)}
          </div>
        </PageSection>
      ))}
      {data && data.groups.length === 0 && (
        <p className="text-muted-foreground text-center py-8">No institution settings are defined.</p>
      )}
    </div>
  )
}
