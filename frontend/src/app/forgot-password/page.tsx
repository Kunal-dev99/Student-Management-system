'use client'

import { useState } from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { rawPasswordResetRequest } from '@/shared/api/client'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await rawPasswordResetRequest(email)
    } catch {
      /* never reveal account state — always show the same confirmation */
    } finally {
      setSubmitting(false)
      setSent(true)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-6">
          <div className="flex items-center justify-center rounded-md bg-[#15171A] px-4 py-2 shadow-sm mb-3">
            <Image src="/brand/logo.png" alt="Fusion Practices" width={150} height={30} priority className="h-7 w-auto" />
          </div>
          <h1 className="text-page-title">Reset your password</h1>
          <p className="text-helper">We&apos;ll email you a reset link</p>
        </div>

        {sent ? (
          <div className="card-elevated p-6 space-y-4">
            <p className="text-sm">
              If that email is registered, a reset link has been sent.
            </p>
            <Link href="/login" className="inline-block text-sm text-primary hover:underline">
              Back to sign in
            </Link>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="card-elevated p-6 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
            </div>

            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? 'Sending…' : 'Send reset link'}
            </Button>

            <p className="text-helper text-center pt-1">
              <Link href="/login" className="text-primary hover:underline">Back to sign in</Link>
            </p>
          </form>
        )}
      </div>
    </div>
  )
}
