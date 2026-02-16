'use server'

interface PlanStep {
  id: string
  name: string
  display_name: string
  description: string
  agent_type: string
  is_scheduled: boolean
  depends_on: string[]
  status: string
}

interface PlanResult {
  id: string
  goal: string
  status: string
  steps: PlanStep[]
  has_more_steps: boolean
}

function getServiceHeaders(): Record<string, string> {
  const token = process.env.TENTACLE_SERVICE_TOKEN
  if (!token) {
    throw new Error('Server configuration error: missing service token')
  }
  return {
    'X-API-Key': token,
    'Content-Type': 'application/json',
  }
}

export async function generatePlan(businessDescription: string): Promise<PlanResult> {
  const API = process.env.TENTACLE_API_URL

  if (!API) {
    throw new Error('Server configuration error')
  }

  const headers = getServiceHeaders()

  const res = await fetch(`${API}/api/tasks/preview`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      goal: `I run this business: ${businessDescription}\n\nIdentify the most impactful repetitive tasks in this business and create concrete automation steps for them. Each step should be a specific action like fetching data, sending reports, scheduling jobs, or processing information — not meta-steps about planning or creating agents.`,
    }),
  })

  if (!res.ok) {
    throw new Error('Failed to generate plan')
  }

  return (await res.json()) as PlanResult
}

export async function joinWaitlist(
  email: string,
  name: string,
  businessDescription: string,
  taskId: string,
) {
  const API = process.env.TENTACLE_API_URL

  if (!API) {
    throw new Error('Server configuration error')
  }

  const headers = getServiceHeaders()

  const res = await fetch(`${API}/api/workspace/objects`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      type: 'contact',
      data: {
        email,
        name,
        business_description: businessDescription,
        task_id: taskId,
        source: 'automate-your-business',
        signed_up_at: new Date().toISOString(),
      },
      tags: ['waitlist', 'founding-member'],
    }),
  })

  if (!res.ok) {
    throw new Error('Failed to join waitlist')
  }
}
