'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import AppLayout from '@/components/AppLayout'
import {
  PageHeader,
  TacticalCard,
  TacticalButton,
  TacticalInput,
  TacticalSelect,
  StatusIndicator
} from '@/components/tactical'
import { Send } from 'lucide-react'

export default function SendNotification() {
  const router = useRouter()
  const [formData, setFormData] = useState({
    recipient: '',
    content: '',
    provider: 'email'
  })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setResult(null)

    const apiKey = localStorage.getItem('api_key')
    if (!apiKey) {
      setError('API key not found. Please login first.')
      setLoading(false)
      return
    }

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/send`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify(formData)
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to send notification')
      }

      setResult(data)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AppLayout>
      <PageHeader
        title="SEND NOTIFICATION"
        subtitle="TRANSMISSION PROTOCOL: E2E-ENCRYPTED | DELIVERY: GUARANTEED"
        status="online"
      />

      {/* System Status Indicators */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="flex items-center gap-3 p-4 rounded-lg border border-border bg-card/30">
          <StatusIndicator status="online" pulse />
          <div>
            <div className="font-mono text-xs text-muted-foreground">SYSTEM</div>
            <div className="font-mono text-sm">ONLINE</div>
          </div>
        </div>
        <div className="flex items-center gap-3 p-4 rounded-lg border border-border bg-card/30">
          <StatusIndicator status="online" pulse />
          <div>
            <div className="font-mono text-xs text-muted-foreground">ENCRYPTION</div>
            <div className="font-mono text-sm">ACTIVE</div>
          </div>
        </div>
        <div className="flex items-center gap-3 p-4 rounded-lg border border-border bg-card/30">
          <StatusIndicator status="online" pulse />
          <div>
            <div className="font-mono text-xs text-muted-foreground">PROVIDERS</div>
            <div className="font-mono text-sm">READY</div>
          </div>
        </div>
      </div>

      <TacticalCard className="p-8" glow>
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label htmlFor="provider" className="block text-sm font-mono font-medium text-primary mb-2 uppercase">
              Provider Channel
            </label>
            <TacticalSelect
              id="provider"
              value={formData.provider}
              onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
            >
              <option value="email">EMAIL</option>
              <option value="sms">SMS</option>
              <option value="slack">SLACK</option>
              <option value="discord">DISCORD</option>
              <option value="telegram">TELEGRAM</option>
              <option value="webhook">WEBHOOK</option>
            </TacticalSelect>
          </div>

          <div>
            <label htmlFor="recipient" className="block text-sm font-mono font-medium text-primary mb-2 uppercase">
              Recipient Target
            </label>
            <TacticalInput
              type="text"
              id="recipient"
              value={formData.recipient}
              onChange={(e) => setFormData({ ...formData, recipient: e.target.value })}
              placeholder="email@example.com, +1234567890, #channel, etc."
              required
            />
          </div>

          <div>
            <label htmlFor="content" className="block text-sm font-mono font-medium text-primary mb-2 uppercase">
              Message Payload
            </label>
            <textarea
              id="content"
              value={formData.content}
              onChange={(e) => setFormData({ ...formData, content: e.target.value })}
              rows={6}
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-all duration-200"
              placeholder="Your notification message..."
              required
            />
          </div>

          <div className="flex items-center justify-between pt-4">
            <TacticalButton
              type="button"
              onClick={() => router.back()}
              variant="outline"
            >
              Cancel
            </TacticalButton>
            <TacticalButton
              type="submit"
              disabled={loading}
              variant="primary"
              glow
              className="gap-2"
            >
              {loading ? (
                <>
                  <div className="w-2 h-2 bg-current rounded-full flicker" />
                  TRANSMITTING...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  SEND NOTIFICATION
                </>
              )}
            </TacticalButton>
          </div>
        </form>

        {error && (
          <div className="mt-6 p-4 border border-destructive/50 rounded bg-destructive/10">
            <p className="font-mono text-sm text-destructive">✗ TRANSMISSION FAILED: {error}</p>
          </div>
        )}

        {result && (
          <div className="mt-6 p-4 border border-primary/50 rounded bg-primary/10">
            <p className="font-mono text-sm text-primary mb-2">✓ NOTIFICATION DISPATCHED</p>
            <p className="font-mono text-xs text-muted-foreground">DELIVERY ID: {result.delivery_id}</p>
            <p className="font-mono text-xs text-muted-foreground">STATUS: {result.status}</p>
          </div>
        )}

        <div className="mt-8 pt-8 border-t border-border">
          <p className="font-mono text-xs text-muted-foreground text-center">
            ENCRYPTED TRANSMISSION // REAL-TIME DELIVERY // ACTIVITY LOGGED
          </p>
        </div>
      </TacticalCard>
    </AppLayout>
  )
}
