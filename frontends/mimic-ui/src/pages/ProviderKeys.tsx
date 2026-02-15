'use client'

import { useState, useEffect } from 'react'
import ProviderKeyForm from '@/components/ProviderKeyForm'
import AppLayout from '@/components/AppLayout'
import { PageHeader, TacticalCard, TacticalButton, StatusIndicator } from '@/components/tactical'
import { Plus, TestTube, Edit, Trash2 } from 'lucide-react'

interface ProviderKey {
  id: string
  provider_type: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export default function ProviderKeys() {
  const [providerKeys, setProviderKeys] = useState<ProviderKey[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingKey, setEditingKey] = useState<ProviderKey | null>(null)

  useEffect(() => {
    fetchProviderKeys()
  }, [])

  const fetchProviderKeys = async () => {
    setLoading(true)
    const apiKey = localStorage.getItem('api_key')
    if (!apiKey) {
      setLoading(false)
      return
    }

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/provider-keys`, {
        headers: {
          'Authorization': `Bearer ${apiKey}`
        }
      })

      if (response.ok) {
        const data = await response.json()
        setProviderKeys(data)
      }
    } catch (err) {
      console.error('Failed to fetch provider keys:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleTest = async (providerType: string) => {
    const apiKey = localStorage.getItem('api_key')
    if (!apiKey) return

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/provider-keys/${providerType}/test`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${apiKey}`
          }
        }
      )

      const data = await response.json()
      if (data.success) {
        alert('Connection test successful!')
      } else {
        alert(`Connection test failed: ${data.message}`)
      }
    } catch (err) {
      alert('Failed to test connection')
    }
  }

  const handleDelete = async (providerType: string) => {
    if (!confirm(`Are you sure you want to delete the ${providerType} provider key?`)) {
      return
    }

    const apiKey = localStorage.getItem('api_key')
    if (!apiKey) return

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/provider-keys/${providerType}`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${apiKey}`
          }
        }
      )

      if (response.ok) {
        fetchProviderKeys()
      }
    } catch (err) {
      alert('Failed to delete provider key')
    }
  }

  const providerTypes = ['email', 'sms', 'slack', 'discord', 'telegram', 'webhook']

  return (
    <AppLayout>
      <PageHeader
        title="PROVIDER KEYS"
        subtitle="BYOK CONFIGURATION | BRING YOUR OWN KEY INTEGRATION"
        status="online"
      />

      <div className="flex justify-end mb-6">
        <TacticalButton
          onClick={() => {
            setEditingKey(null)
            setShowForm(true)
          }}
          variant="primary"
          glow
          className="gap-2"
        >
          <Plus className="w-4 h-4" />
          ADD PROVIDER
        </TacticalButton>
      </div>

      {showForm && (
        <TacticalCard className="p-6 mb-6" glow>
          <div className="flex items-center gap-3 mb-6">
            <StatusIndicator status="warning" pulse />
            <h3 className="text-xl font-sans font-semibold uppercase">
              {editingKey ? 'EDIT PROVIDER' : 'NEW PROVIDER'}
            </h3>
          </div>
          <ProviderKeyForm
            providerKey={editingKey}
            onSuccess={() => {
              setShowForm(false)
              setEditingKey(null)
              fetchProviderKeys()
            }}
            onCancel={() => {
              setShowForm(false)
              setEditingKey(null)
            }}
          />
        </TacticalCard>
      )}

      {loading ? (
        <div className="text-center py-12">
          <div className="font-mono text-sm text-muted-foreground">LOADING PROVIDERS...</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {providerTypes.map((providerType) => {
            const key = providerKeys.find(k => k.provider_type === providerType)
            const isConfigured = !!key

            return (
              <TacticalCard key={providerType} className="p-6" glow>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-sans font-semibold uppercase">{providerType}</h3>
                  {key && (
                    <StatusIndicator
                      status={key.is_active ? "online" : "offline"}
                      pulse={key.is_active}
                      label={key.is_active ? 'ACTIVE' : 'INACTIVE'}
                    />
                  )}
                </div>

                {isConfigured ? (
                  <div className="space-y-4">
                    <div className="space-y-2 text-sm font-mono">
                      <div className="flex justify-between text-muted-foreground">
                        <span>ADDED:</span>
                        <span>{new Date(key!.created_at).toLocaleDateString()}</span>
                      </div>
                      <div className="flex justify-between text-muted-foreground">
                        <span>STATUS:</span>
                        <span className="text-primary">{key!.is_active ? 'OPERATIONAL' : 'STANDBY'}</span>
                      </div>
                    </div>

                    <div className="flex gap-2">
                      <TacticalButton
                        onClick={() => handleTest(providerType)}
                        variant="primary"
                        size="sm"
                        className="flex-1 gap-1"
                      >
                        <TestTube className="w-3 h-3" />
                        TEST
                      </TacticalButton>
                      <TacticalButton
                        onClick={() => {
                          setEditingKey(key!)
                          setShowForm(true)
                        }}
                        variant="secondary"
                        size="sm"
                        className="flex-1 gap-1"
                      >
                        <Edit className="w-3 h-3" />
                        EDIT
                      </TacticalButton>
                      <TacticalButton
                        onClick={() => handleDelete(providerType)}
                        variant="danger"
                        size="sm"
                        className="flex-1 gap-1"
                      >
                        <Trash2 className="w-3 h-3" />
                        DELETE
                      </TacticalButton>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="text-center py-4 text-muted-foreground">
                      <div className="font-mono text-sm mb-2">NOT CONFIGURED</div>
                      <div className="text-xs">No API keys configured for this provider</div>
                    </div>
                    <TacticalButton
                      onClick={() => {
                        setEditingKey(null)
                        setShowForm(true)
                      }}
                      variant="outline"
                      className="w-full"
                    >
                      CONFIGURE
                    </TacticalButton>
                  </div>
                )}
              </TacticalCard>
            )
          })}
        </div>
      )}
    </AppLayout>
  )
}
