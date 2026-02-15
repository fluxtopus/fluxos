'use client'

import { useState, useEffect } from 'react'
import AppLayout from '@/components/AppLayout'
import {
  PageHeader,
  TacticalCard,
  TacticalSelect,
  TacticalTable,
  TacticalTableHeader,
  TacticalTableBody,
  TacticalTableRow,
  TacticalTableHead,
  TacticalTableCell,
  StatusIndicator
} from '@/components/tactical'

interface DeliveryLog {
  id: string
  delivery_id: string
  workflow_id: string | null
  provider: string
  recipient: string
  status: string
  sent_at: string | null
  completed_at: string | null
  error_message: string | null
  created_at: string
}

export default function Logs() {
  const [logs, setLogs] = useState<DeliveryLog[]>([])
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({
    provider: '',
    status: ''
  })

  useEffect(() => {
    fetchLogs()
  }, [filters])

  const fetchLogs = async () => {
    setLoading(true)
    const apiKey = localStorage.getItem('api_key')
    if (!apiKey) {
      setLoading(false)
      return
    }

    const params = new URLSearchParams()
    if (filters.provider) params.append('provider', filters.provider)
    if (filters.status) params.append('status', filters.status)

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/logs?${params.toString()}`,
        {
          headers: {
            'Authorization': `Bearer ${apiKey}`
          }
        }
      )

      if (response.ok) {
        const data = await response.json()
        setLogs(data)
      }
    } catch (err) {
      console.error('Failed to fetch logs:', err)
    } finally {
      setLoading(false)
    }
  }

  const getStatusInfo = (status: string) => {
    switch (status) {
      case 'sent':
      case 'delivered':
        return { color: 'online', label: status.toUpperCase() }
      case 'failed':
        return { color: 'error', label: 'FAILED' }
      case 'pending':
        return { color: 'warning', label: 'PENDING' }
      default:
        return { color: 'offline', label: status.toUpperCase() }
    }
  }

  return (
    <AppLayout>
      <PageHeader
        title="DELIVERY LOGS"
        subtitle="REAL-TIME ACTIVITY MONITORING | FILTERABLE TRANSMISSION RECORDS"
        status="online"
      />

      {/* Filters */}
      <TacticalCard className="p-6 mb-6" glow>
        <div className="flex items-center gap-3 mb-4">
          <StatusIndicator status="online" pulse />
          <h3 className="text-lg font-sans font-semibold uppercase">FILTER CONTROLS</h3>
        </div>
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1">
            <label htmlFor="provider-filter" className="block text-sm font-mono font-medium text-primary mb-2 uppercase">
              Provider Channel
            </label>
            <TacticalSelect
              id="provider-filter"
              value={filters.provider}
              onChange={(e) => setFilters({ ...filters, provider: e.target.value })}
            >
              <option value="">ALL PROVIDERS</option>
              <option value="email">EMAIL</option>
              <option value="sms">SMS</option>
              <option value="slack">SLACK</option>
              <option value="discord">DISCORD</option>
              <option value="telegram">TELEGRAM</option>
              <option value="webhook">WEBHOOK</option>
            </TacticalSelect>
          </div>

          <div className="flex-1">
            <label htmlFor="status-filter" className="block text-sm font-mono font-medium text-primary mb-2 uppercase">
              Delivery Status
            </label>
            <TacticalSelect
              id="status-filter"
              value={filters.status}
              onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            >
              <option value="">ALL STATUSES</option>
              <option value="pending">PENDING</option>
              <option value="sent">SENT</option>
              <option value="delivered">DELIVERED</option>
              <option value="failed">FAILED</option>
            </TacticalSelect>
          </div>
        </div>
      </TacticalCard>

      {/* Logs Table */}
      <TacticalCard className="p-6">
        <div className="flex items-center gap-3 mb-6">
          <StatusIndicator status="online" pulse />
          <h3 className="text-xl font-sans font-semibold uppercase">TRANSMISSION RECORDS</h3>
        </div>

        {loading ? (
          <div className="text-center py-12">
            <div className="font-mono text-sm text-muted-foreground">LOADING LOGS...</div>
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <div className="font-mono text-lg mb-2">NO LOGS DETECTED</div>
            <div className="text-sm">Start sending notifications to see activity logs here</div>
          </div>
        ) : (
          <TacticalTable>
            <TacticalTableHeader>
              <TacticalTableRow>
                <TacticalTableHead>Delivery ID</TacticalTableHead>
                <TacticalTableHead>Provider</TacticalTableHead>
                <TacticalTableHead>Recipient</TacticalTableHead>
                <TacticalTableHead>Status</TacticalTableHead>
                <TacticalTableHead>Sent At</TacticalTableHead>
                <TacticalTableHead>Error</TacticalTableHead>
              </TacticalTableRow>
            </TacticalTableHeader>
            <TacticalTableBody>
              {logs.map((log) => {
                const statusInfo = getStatusInfo(log.status)
                return (
                  <TacticalTableRow key={log.id}>
                    <TacticalTableCell className="font-mono text-primary">
                      {log.delivery_id.substring(0, 8)}...
                    </TacticalTableCell>
                    <TacticalTableCell className="font-mono uppercase">
                      {log.provider}
                    </TacticalTableCell>
                    <TacticalTableCell className="font-mono">
                      {log.recipient}
                    </TacticalTableCell>
                    <TacticalTableCell>
                      <StatusIndicator
                        status={statusInfo.color as any}
                        label={statusInfo.label}
                        pulse={log.status === 'pending'}
                      />
                    </TacticalTableCell>
                    <TacticalTableCell className="font-mono text-sm text-muted-foreground">
                      {log.sent_at ? new Date(log.sent_at).toLocaleString() : '-'}
                    </TacticalTableCell>
                    <TacticalTableCell className="text-sm text-destructive font-mono">
                      {log.error_message || '-'}
                    </TacticalTableCell>
                  </TacticalTableRow>
                )
              })}
            </TacticalTableBody>
          </TacticalTable>
        )}
      </TacticalCard>
    </AppLayout>
  )
}
