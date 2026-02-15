'use client'

import { useState } from 'react'

interface WorkflowNodeProps {
  node: {
    id: string
    type: 'trigger' | 'condition' | 'action'
    data: any
  }
  onUpdate: (id: string, data: any) => void
}

export default function WorkflowNode({ node, onUpdate }: WorkflowNodeProps) {
  const [isOpen, setIsOpen] = useState(false)

  const handleUpdate = (field: string, value: any) => {
    onUpdate(node.id, {
      ...node.data,
      [field]: value
    })
  }

  return (
    <div className="border border-gray-300 rounded-lg p-4 bg-white shadow">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-gray-900 capitalize">{node.type}</h3>
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="text-gray-500 hover:text-gray-700"
        >
          {isOpen ? '−' : '+'}
        </button>
      </div>
      
      {isOpen && (
        <div className="mt-4 space-y-4">
          {node.type === 'action' && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700">Provider</label>
                <select
                  value={node.data.provider || 'email'}
                  onChange={(e) => handleUpdate('provider', e.target.value)}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
                >
                  <option value="email">Email</option>
                  <option value="sms">SMS</option>
                  <option value="slack">Slack</option>
                  <option value="discord">Discord</option>
                  <option value="telegram">Telegram</option>
                  <option value="webhook">Webhook</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Template ID</label>
                <input
                  type="text"
                  value={node.data.template_id || ''}
                  onChange={(e) => handleUpdate('template_id', e.target.value)}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
                  placeholder="Optional template ID"
                />
              </div>
            </>
          )}
          
          {node.type === 'condition' && (
            <div>
              <label className="block text-sm font-medium text-gray-700">Condition</label>
              <input
                type="text"
                value={node.data.condition || ''}
                onChange={(e) => handleUpdate('condition', e.target.value)}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
                placeholder="e.g., ${inputs.user_type} == 'premium'"
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

