'use client'

import { useState, useEffect } from 'react'
import AppLayout from '@/components/AppLayout'
import { PageHeader, TacticalCard, StatusIndicator, MetricsCard } from '@/components/tactical'
import { ArrowPathIcon } from '@heroicons/react/24/outline'

export default function DeliveryDashboard() {
  const [workflows, setWorkflows] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchWorkflows()
  }, [])

  const fetchWorkflows = async () => {
    setLoading(true)
    const apiKey = localStorage.getItem('api_key')
    if (!apiKey) {
      setLoading(false)
      return
    }

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/workflows`, {
        headers: {
          'Authorization': `Bearer ${apiKey}`
        }
      })

      if (response.ok) {
        const data = await response.json()
        setWorkflows(data)
      }
    } catch (err) {
      console.error('Failed to fetch workflows:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AppLayout>
      <PageHeader
        title="DELIVERY DASHBOARD"
        subtitle="REAL-TIME WORKFLOW EXECUTION MONITORING | ANALYTICS ENABLED"
        status="online"
      />

      {/* Metrics Overview */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <MetricsCard
          label="TOTAL WORKFLOWS"
          value={workflows.length}
          status="online"
        />
        <MetricsCard
          label="ACTIVE WORKFLOWS"
          value={workflows.filter(w => w.is_active).length}
          status="online"
        />
        <MetricsCard
          label="MESSAGES PROCESSED"
          value="2.4M+"
          status="warning"
        />
        <MetricsCard
          label="AVG LATENCY"
          value="<100ms"
          status="online"
        />
      </div>

      {/* Workflows List */}
      <TacticalCard className="p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <StatusIndicator status="online" pulse />
            <h3 className="text-xl font-sans font-semibold uppercase">WORKFLOW EXECUTION</h3>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-12">
            <ArrowPathIcon className="h-8 w-8 animate-spin mx-auto text-primary mb-4" />
            <div className="font-mono text-sm text-muted-foreground">LOADING...</div>
          </div>
        ) : workflows.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <div className="font-mono text-lg mb-2">NO WORKFLOWS DETECTED</div>
            <div className="text-sm">Create a workflow to see execution data here</div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {workflows.map((workflow) => (
              <TacticalCard key={workflow.id} className="p-4" glow>
                <div className="flex items-start justify-between mb-3">
                  <StatusIndicator
                    status={workflow.is_active ? "online" : "offline"}
                    pulse={workflow.is_active}
                  />
                  <span className={`
                    px-2 py-1 rounded text-xs font-mono uppercase tracking-wider
                    ${workflow.is_active
                      ? 'bg-primary/20 text-primary border border-primary/30'
                      : 'bg-muted text-muted-foreground border border-border'
                    }
                  `}>
                    {workflow.is_active ? 'ACTIVE' : 'INACTIVE'}
                  </span>
                </div>
                <h4 className="font-sans font-semibold text-lg mb-2">{workflow.name}</h4>
                <div className="space-y-1 text-sm text-muted-foreground font-mono">
                  <div className="flex justify-between">
                    <span>ID:</span>
                    <span>{workflow.id.substring(0, 8)}...</span>
                  </div>
                  <div className="flex justify-between">
                    <span>STATUS:</span>
                    <span className="text-primary">{workflow.is_active ? 'OPERATIONAL' : 'STANDBY'}</span>
                  </div>
                </div>
              </TacticalCard>
            ))}
          </div>
        )}
      </TacticalCard>
    </AppLayout>
  )
}
