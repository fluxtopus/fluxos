'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'

interface ProviderKey {
  id: string
  provider_type: string
  is_active: boolean
  created_at: string
  updated_at: string
}

interface ProviderKeyFormProps {
  providerKey: ProviderKey | null
  onSuccess: () => void
  onCancel: () => void
}

export default function ProviderKeyForm({ providerKey, onSuccess, onCancel }: ProviderKeyFormProps) {
  const router = useRouter()
  const [formData, setFormData] = useState({
    provider_type: providerKey?.provider_type || 'email',
    api_key: '',
    secret: '',
    webhook_url: '',
    bot_token: '',
    from_email: '',
    from_number: ''
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (providerKey) {
      setFormData(prev => ({
        ...prev,
        provider_type: providerKey.provider_type
      }))
    }
  }, [providerKey])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    const apiKey = localStorage.getItem('api_key')
    if (!apiKey) {
      setError('API key not found')
      setLoading(false)
      return
    }

    // Build request payload based on provider type
    const payload: any = {
      provider_type: formData.provider_type
    }

    if (formData.provider_type === 'email') {
      payload.api_key = formData.api_key
      payload.from_email = formData.from_email
    } else if (formData.provider_type === 'sms') {
      payload.api_key = formData.api_key
      payload.secret = formData.secret
      payload.from_number = formData.from_number
    } else if (formData.provider_type === 'slack' || formData.provider_type === 'discord' || formData.provider_type === 'webhook') {
      payload.webhook_url = formData.webhook_url
    } else if (formData.provider_type === 'telegram') {
      payload.bot_token = formData.bot_token
    }

    try {
      const url = providerKey
        ? `${process.env.NEXT_PUBLIC_API_URL}/api/v1/provider-keys/${formData.provider_type}`
        : `${process.env.NEXT_PUBLIC_API_URL}/api/v1/provider-keys`

      const response = await fetch(url, {
        method: providerKey ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify(payload)
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to save provider key')
      }

      onSuccess()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="border border-gray-200 rounded-lg p-6 bg-gray-50">
      <h3 className="text-lg font-medium text-gray-900 mb-4">
        {providerKey ? 'Edit' : 'Add'} Provider Key
      </h3>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="provider_type" className="block text-sm font-medium text-gray-700">
            Provider Type
          </label>
          <select
            id="provider_type"
            value={formData.provider_type}
            onChange={(e) => setFormData({ ...formData, provider_type: e.target.value })}
            disabled={!!providerKey}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 disabled:bg-gray-100"
            required
          >
            <option value="email">Email (SendGrid)</option>
            <option value="sms">SMS (Twilio)</option>
            <option value="slack">Slack</option>
            <option value="discord">Discord</option>
            <option value="telegram">Telegram</option>
            <option value="webhook">Webhook</option>
          </select>
        </div>

        {formData.provider_type === 'email' && (
          <>
            <div>
              <label htmlFor="api_key" className="block text-sm font-medium text-gray-700">
                SendGrid API Key
              </label>
              <input
                type="password"
                id="api_key"
                value={formData.api_key}
                onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                required
              />
            </div>
            <div>
              <label htmlFor="from_email" className="block text-sm font-medium text-gray-700">
                From Email
              </label>
              <input
                type="email"
                id="from_email"
                value={formData.from_email}
                onChange={(e) => setFormData({ ...formData, from_email: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                required
              />
            </div>
          </>
        )}

        {formData.provider_type === 'sms' && (
          <>
            <div>
              <label htmlFor="api_key" className="block text-sm font-medium text-gray-700">
                Twilio Account SID
              </label>
              <input
                type="text"
                id="api_key"
                value={formData.api_key}
                onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                required
              />
            </div>
            <div>
              <label htmlFor="secret" className="block text-sm font-medium text-gray-700">
                Twilio Auth Token
              </label>
              <input
                type="password"
                id="secret"
                value={formData.secret}
                onChange={(e) => setFormData({ ...formData, secret: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                required
              />
            </div>
            <div>
              <label htmlFor="from_number" className="block text-sm font-medium text-gray-700">
                From Phone Number
              </label>
              <input
                type="text"
                id="from_number"
                value={formData.from_number}
                onChange={(e) => setFormData({ ...formData, from_number: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                placeholder="+1234567890"
              />
            </div>
          </>
        )}

        {(formData.provider_type === 'slack' || formData.provider_type === 'discord' || formData.provider_type === 'webhook') && (
          <div>
            <label htmlFor="webhook_url" className="block text-sm font-medium text-gray-700">
              Webhook URL
            </label>
            <input
              type="url"
              id="webhook_url"
              value={formData.webhook_url}
              onChange={(e) => setFormData({ ...formData, webhook_url: e.target.value })}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
              required
            />
          </div>
        )}

        {formData.provider_type === 'telegram' && (
          <div>
            <label htmlFor="bot_token" className="block text-sm font-medium text-gray-700">
              Bot Token
            </label>
            <input
              type="password"
              id="bot_token"
              value={formData.bot_token}
              onChange={(e) => setFormData({ ...formData, bot_token: e.target.value })}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
              required
            />
          </div>
        )}

        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-md">
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        <div className="flex justify-end space-x-3">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 bg-primary-600 text-white rounded-md text-sm font-medium hover:bg-primary-700 disabled:opacity-50"
          >
            {loading ? 'Saving...' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  )
}

