'use client'

import { useQuery } from '@tanstack/react-query'
import { getHealth } from '@/shared/api/client'

/** Backend connectivity probe for the dashboard banner. */
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 15_000,
  })
}
