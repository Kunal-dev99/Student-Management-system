'use client'

import { Suspense, useState } from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/components/ui/use-toast'
import { rawPasswordResetConfirm } from '@/shared/api/client'

function ResetPasswordForm() {
  const router = useRouter()
  const { toast } = useToast()
  const params = useSearchParams()
  const token = params.get('token') ?? ''

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return }
    if (password !== confirm) { setError('Passwords do not match.'); return }
    if (!token) { setError('This reset link is invalid or has expired.'); return }

    setSubmitting(true)
    try {
      const res = await rawPasswordResetConfirm(token, password)
      if (res.ok) {
        toast({ title: 'Password updated', description: 'You can now sign in with your new password.' })
        router.push('/login')
      } else {
        setError('This reset link is invalid or has expired.')
      }
    } catch {
      setError('This reset link is invalid or has expired.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="card-elevated p-6 space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="password">New password</Label>
        <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="confirm">Confirm password</Label>
        <Input id="confirm" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
      </div>

      {error && (
        <p className="text-sm text-[hsl(var(--destructive))] bg-[hsl(var(--destructive)/0.08)] border border-[hsl(var(--destructive)/0.25)] rounded-md px-3 py-2">
          {error}
        </p>
      )}

      <Button type="submit" className="w-full" disabled={submitting}>
        {submitting ? 'Updating…' : 'Set new password'}
      </Button>

      <p className="text-helper text-center pt-1">
        <Link href="/login" className="text-primary hover:underline">Back to sign in</Link>
      </p>
    </form>
  )
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-6">
          <div className="flex items-center justify-center rounded-md bg-[#15171A] px-4 py-2 shadow-sm mb-3">
            <Image src="/brand/logo.png" alt="Fusion Practices" width={150} height={30} priority className="h-7 w-auto" />
          </div>
          <h1 className="text-page-title">Choose a new password</h1>
          <p className="text-helper">At least 8 characters</p>
        </div>
        <Suspense fallback={<div className="card-elevated p-6 text-helper">Loading…</div>}>
          <ResetPasswordForm />
        </Suspense>
      </div>
    </div>
  )
}
