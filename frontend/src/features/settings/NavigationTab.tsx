'use client'

/**
 * Settings → Navigation — the runtime park mechanism for the sidebar (tenant-wide).
 *
 * An admin switches any sidebar feature on or off. Off hides it from the nav and blocks its route,
 * but changes nothing in code — flip it back on any time. Dashboard and Settings are core and stay
 * on, so there's always a way back. Toggling refreshes /me so the sidebar updates immediately.
 */
import { Compass, Lock } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { useNavFeatures, useSetNavFeature, type NavFeature } from '@/features/settings/navFeaturesApi'

function FeatureRow({ item, onToggle, busy }: {
  item: NavFeature
  onToggle: (item: NavFeature, enabled: boolean) => void
  busy: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 border-b border-border/50 last:border-0">
      <div className="min-w-0">
        <span className="font-medium">{item.label}</span>
        <span className="text-helper font-mono ml-2">{item.route}</span>
      </div>
      {item.core ? (
        <Badge variant="secondary" className="inline-flex items-center gap-1 shrink-0">
          <Lock className="h-3 w-3" /> Always on
        </Badge>
      ) : (
        <Button
          size="sm"
          variant={item.enabled ? 'outline' : 'secondary'}
          disabled={busy}
          className="w-24 shrink-0"
          onClick={() => onToggle(item, !item.enabled)}
        >
          {item.enabled ? 'Enabled' : 'Disabled'}
        </Button>
      )}
    </div>
  )
}

export function NavigationTab() {
  const { toast } = useToast()
  const { refresh } = useAuth()
  const { data, isLoading, isError, error } = useNavFeatures()
  const setNav = useSetNavFeature()

  const onToggle = async (item: NavFeature, enabled: boolean) => {
    try {
      await setNav.mutateAsync({ route: item.route, enabled })
      await refresh() // update the live sidebar immediately
      toast({ title: enabled ? `${item.label} enabled` : `${item.label} hidden from the sidebar` })
    } catch (e) {
      toast({ title: 'Could not update', description: (e as ApiError).message, variant: 'destructive' })
    }
  }

  return (
    <PageSection
      icon={Compass}
      title="Navigation"
      accent="primary"
      description="Switch sidebar features on or off for the whole institution. A hidden feature is removed from the menu and its page is blocked, but nothing is deleted — turn it back on any time. Access is still enforced per endpoint on the server."
    >
      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : isError ? (
        <p className="text-sm text-[hsl(var(--destructive))]">{(error as ApiError)?.message}</p>
      ) : (
        <div className="space-y-5">
          {data?.groups.map((g) => (
            <div key={g.group}>
              <h4 className="text-label mb-1">{g.group}</h4>
              <div className="card-elevated px-3">
                {g.items.map((item) => (
                  <FeatureRow key={item.route} item={item} onToggle={onToggle} busy={setNav.isPending} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </PageSection>
  )
}
