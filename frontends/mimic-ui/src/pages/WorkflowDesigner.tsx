'use client'

import { useState } from 'react'
import WorkflowCanvas from '../components/WorkflowCanvas'
import { Node, Edge } from 'reactflow'
import AppLayout from '@/components/AppLayout'
import {
  PageHeader,
  TacticalCard,
  TacticalButton,
  TacticalInput,
  StatusIndicator
} from '@/components/tactical'
import { Save } from 'lucide-react'

export default function WorkflowDesigner() {
  const [workflowName, setWorkflowName] = useState('')
  const [saving, setSaving] = useState(false)
  const [nodes, setNodes] = useState<Node[]>([])
  const [edges, setEdges] = useState<Edge[]>([])

  const handleSave = async (canvasNodes: Node[], canvasEdges: Edge[]) => {
    if (!workflowName) {
      alert('Please enter a workflow name')
      return
    }

    setSaving(true)
    const apiKey = localStorage.getItem('api_key')
    if (!apiKey) {
      alert('API key not found')
      setSaving(false)
      return
    }

    try {
      // Convert React Flow nodes/edges to workflow definition JSON
      const definitionJson = {
        nodes: canvasNodes.map(node => ({
          id: node.id,
          type: node.type,
          data: node.data,
          position: node.position
        })),
        edges: canvasEdges.map(edge => ({
          source: edge.source,
          target: edge.target
        }))
      }

      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/workflows`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify({
          name: workflowName,
          definition_json: definitionJson
        })
      })

      if (response.ok) {
        alert('Workflow saved successfully!')
      } else {
        const data = await response.json()
        alert(`Failed to save workflow: ${data.detail}`)
      }
    } catch (err: any) {
      alert(`Error: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppLayout>
      <PageHeader
        title="WORKFLOW DESIGNER"
        subtitle="VISUAL ORCHESTRATION INTERFACE | DRAG-AND-DROP ENABLED"
        status="online"
      />

      {/* Toolbar */}
      <TacticalCard className="p-6 mb-6" glow>
        <div className="flex flex-col md:flex-row items-start md:items-center gap-4">
          <div className="flex-1">
            <label htmlFor="workflow-name" className="block text-sm font-mono font-medium text-primary mb-2 uppercase">
              Workflow Identifier
            </label>
            <TacticalInput
              id="workflow-name"
              type="text"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              placeholder="Enter workflow name..."
            />
          </div>
          <div className="flex items-end">
            <TacticalButton
              onClick={() => handleSave(nodes, edges)}
              disabled={saving || !workflowName}
              variant="primary"
              glow
              className="gap-2"
            >
              {saving ? (
                <>
                  <div className="w-2 h-2 bg-current rounded-full flicker" />
                  SAVING...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  SAVE WORKFLOW
                </>
              )}
            </TacticalButton>
          </div>
        </div>
      </TacticalCard>

      {/* Canvas */}
      <TacticalCard className="p-0 overflow-hidden" style={{ height: '600px' }}>
        <div className="relative h-full">
          {/* Corner decorations */}
          <div className="absolute top-0 left-0 w-16 h-16 border-t-2 border-l-2 border-primary/30 z-10 pointer-events-none" />
          <div className="absolute top-0 right-0 w-16 h-16 border-t-2 border-r-2 border-primary/30 z-10 pointer-events-none" />
          <div className="absolute bottom-0 left-0 w-16 h-16 border-b-2 border-l-2 border-primary/30 z-10 pointer-events-none" />
          <div className="absolute bottom-0 right-0 w-16 h-16 border-b-2 border-r-2 border-primary/30 z-10 pointer-events-none" />

          <WorkflowCanvas
            onSave={handleSave}
            initialNodes={nodes}
            initialEdges={edges}
          />
        </div>
      </TacticalCard>

      {/* Instructions */}
      <div className="mt-6 p-4 rounded-lg border border-border bg-card/20">
        <div className="flex items-start gap-3">
          <StatusIndicator status="online" pulse />
          <div className="flex-1">
            <p className="font-mono text-xs text-muted-foreground uppercase mb-2">SYSTEM INSTRUCTIONS</p>
            <p className="text-sm text-muted-foreground">
              Drag nodes from the panel to create your notification workflow. Connect nodes to define the execution flow.
              Save your workflow when complete.
            </p>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
