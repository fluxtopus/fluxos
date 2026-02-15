'use client'

import { useState, useEffect } from 'react'
import { usePathname } from 'next/navigation'
import Link from 'next/link'
import AppLayout from '@/components/AppLayout'
import { MetricsCard, PageHeader, TacticalCard, TacticalButton, StatusIndicator } from '@/components/tactical'

export default function Dashboard() {
  const [user, setUser] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Fetch user info
    const apiKey = localStorage.getItem('api_key')
    if (apiKey) {
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/me`, {
        headers: {
          'Authorization': `Bearer ${apiKey}`
        }
      })
        .then(res => res.json())
        .then(data => {
          setUser(data)
          setLoading(false)
        })
        .catch(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="font-mono text-2xl text-primary">INITIALIZING SYSTEMS...</div>
        </div>
      </AppLayout>
    )
  }

  const stats = [
    {
      label: 'WORKFLOWS',
      value: '0',
      status: 'online' as const,
    },
    {
      label: 'NOTIFICATIONS SENT',
      value: '0',
      status: 'warning' as const,
    },
    {
      label: 'SUCCESS RATE',
      value: '100%',
      status: 'online' as const,
    },
    {
      label: 'SUBSCRIPTION TIER',
      value: user?.subscription_tier?.toUpperCase() || 'FREE',
      status: 'warning' as const,
    },
  ]

  return (
    <AppLayout>
      <PageHeader
        title="COMMAND DASHBOARD"
        subtitle={`SYSTEM.STATUS: ONLINE | TIMESTAMP: ${new Date().toLocaleString()}`}
        status="online"
      />

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        {stats.map((stat, index) => (
          <MetricsCard
            key={index}
            label={stat.label}
            value={stat.value}
            status={stat.status}
          />
        ))}
      </div>

      {/* Quick Actions & System Status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <TacticalCard className="p-6" glow>
          <div className="flex items-center gap-3 mb-6">
            <StatusIndicator status="warning" pulse />
            <h3 className="text-xl font-sans font-semibold uppercase">QUICK ACTIONS</h3>
          </div>
          <div className="space-y-3">
            <Link href="/send" className="block">
              <TacticalButton variant="primary" className="w-full" glow>
                SEND NOTIFICATION
              </TacticalButton>
            </Link>
            <Link href="/workflows" className="block">
              <TacticalButton variant="outline" className="w-full">
                CREATE WORKFLOW
              </TacticalButton>
            </Link>
          </div>
        </TacticalCard>

        {/* System Status Panel */}
        <TacticalCard className="p-6" glow>
          <div className="flex items-center gap-3 mb-6">
            <StatusIndicator status="online" pulse />
            <h3 className="text-xl font-sans font-semibold uppercase">SYSTEM STATUS</h3>
          </div>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground uppercase text-sm font-mono">API Gateway</span>
              <StatusIndicator status="online" pulse label="ONLINE" />
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground uppercase text-sm font-mono">Notification Engine</span>
              <StatusIndicator status="online" pulse label="READY" />
            </div>
            <div className="flex justify-between items-center">
              <span className="text-muted-foreground uppercase text-sm font-mono">Workflow Processor</span>
              <StatusIndicator status="online" pulse label="STANDBY" />
            </div>
          </div>
        </TacticalCard>
      </div>

      {/* Activity Feed */}
      <TacticalCard className="p-6">
        <div className="flex items-center gap-3 mb-6">
          <StatusIndicator status="online" pulse />
          <h3 className="text-xl font-sans font-semibold uppercase">RECENT ACTIVITY</h3>
        </div>
        <div className="text-center py-12 text-muted-foreground">
          <div className="font-mono text-lg mb-2">NO ACTIVITY DETECTED</div>
          <div className="text-sm">Start sending notifications to see activity here</div>
        </div>
      </TacticalCard>
    </AppLayout>
  )
}
