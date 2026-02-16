'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import dynamic from 'next/dynamic'
import { generatePlan, joinWaitlist } from '@/app/automate-your-business/actions'

const OceanBackground = dynamic(() => import('@/components/OceanBackground'), {
  ssr: false,
})

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

type FlowState = 'input' | 'generating' | 'plan' | 'captured'

const STAGES = [
  {
    label: 'SCANNING OPERATIONS',
    description: 'Identifying repetitive tasks and bottlenecks...',
    logs: [
      '[ok] Scanning business processes',
      '[ok] Found automatable workflows',
      '[ok] Bottleneck analysis complete',
    ],
  },
  {
    label: 'MATCHING AGENTS',
    description: 'Finding the best AI agents for each task...',
    logs: [
      '[ok] Agent registry loaded',
      '[ok] Matching capabilities to tasks',
      '[ok] Agent assignments confirmed',
    ],
  },
  {
    label: 'MAPPING DEPENDENCIES',
    description: 'Determining the optimal execution order...',
    logs: [
      '[ok] Building dependency graph',
      '[ok] Resolving execution order',
    ],
  },
  {
    label: 'OPTIMIZING SCHEDULE',
    description: 'Calculating timing and resource allocation...',
    logs: [
      '[ok] Resource allocation planned',
      '[ok] Schedule optimization complete',
    ],
  },
  {
    label: 'GENERATING PLAN',
    description: 'Building your custom automation blueprint...',
    logs: [
      '[ok] Compiling automation blueprint',
      '[ok] Validating step integrity',
      '[ok] Plan ready for review',
    ],
  },
]

const STAGE_DURATION = 18000 // ms per stage (~90s total for 5 stages)
const LOG_STAGGER = 3000 // ms between log lines

export default function WaitlistFlow() {
  const [state, setState] = useState<FlowState>('input')
  const [businessDescription, setBusinessDescription] = useState('')
  const [plan, setPlan] = useState<{ id: string; steps: PlanStep[]; has_more_steps: boolean } | null>(null)
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const planRef = useRef<HTMLDivElement>(null)
  const stagesEndRef = useRef<HTMLDivElement>(null)

  // Progress stage state
  const [activeStage, setActiveStage] = useState(0)
  const [visibleLogs, setVisibleLogs] = useState<number[]>([]) // count of visible logs per stage
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [progressPercent, setProgressPercent] = useState(0)
  const [planReady, setPlanReady] = useState(false)

  // Advance stages during generating
  useEffect(() => {
    if (state !== 'generating') return

    setActiveStage(0)
    setVisibleLogs([])
    setElapsedSeconds(0)
    setProgressPercent(0)
    setPlanReady(false)

    // Elapsed timer
    const timerInterval = setInterval(() => {
      setElapsedSeconds((s) => s + 1)
    }, 1000)

    // Progress bar: smoothly fill to ~90% over total duration
    const totalDuration = STAGES.length * STAGE_DURATION
    const progressInterval = setInterval(() => {
      setProgressPercent((p) => {
        if (p >= 90) return 90
        return p + 90 / (totalDuration / 200)
      })
    }, 200)

    // Stage advancement
    const stageTimers = STAGES.map((_, i) =>
      setTimeout(() => setActiveStage(i), i * STAGE_DURATION)
    )

    // Log lines for each stage
    const logTimers: ReturnType<typeof setTimeout>[] = []
    STAGES.forEach((stage, stageIdx) => {
      stage.logs.forEach((_, logIdx) => {
        const delay = stageIdx * STAGE_DURATION + 1500 + logIdx * LOG_STAGGER
        logTimers.push(
          setTimeout(() => {
            setVisibleLogs((prev) => {
              const next = [...prev]
              next[stageIdx] = (next[stageIdx] || 0) + 1
              return next
            })
          }, delay)
        )
      })
    })

    return () => {
      clearInterval(timerInterval)
      clearInterval(progressInterval)
      stageTimers.forEach(clearTimeout)
      logTimers.forEach(clearTimeout)
    }
  }, [state])

  // Auto-scroll stages container to keep active stage visible
  useEffect(() => {
    if (state === 'generating' && stagesEndRef.current) {
      stagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [state, activeStage, visibleLogs])

  // When plan arrives, animate to 100% then transition
  useEffect(() => {
    if (!planReady) return
    setProgressPercent(100)
    const timer = setTimeout(() => setState('plan'), 600)
    return () => clearTimeout(timer)
  }, [planReady])

  // Scroll to plan when it appears
  useEffect(() => {
    if (state === 'plan' && planRef.current) {
      planRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [state])

  const handleGenerate = useCallback(async () => {
    if (!businessDescription.trim()) return
    setError('')
    setState('generating')

    try {
      const result = await generatePlan(businessDescription.trim())
      setPlan({ id: result.id, steps: result.steps || [], has_more_steps: result.has_more_steps })
      setPlanReady(true)
    } catch {
      setError('Something went wrong generating your plan. Please try again.')
      setState('input')
    }
  }, [businessDescription])

  async function handleJoinWaitlist(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim() || !plan) return
    setError('')
    setSubmitting(true)

    try {
      await joinWaitlist(email.trim(), name.trim(), businessDescription, plan.id)
      setState('captured')
    } catch {
      setError('Failed to join waitlist. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }

  return (
    <main className="min-h-screen bg-[#0b0d10] text-[#728c96] relative overflow-hidden font-mono text-sm selection:bg-[#3b6e75] selection:text-white">
      <OceanBackground />

      <div className="relative z-10 min-h-screen p-6 md:p-12 flex flex-col">
        {/* Top Bar */}
        <div className="flex justify-between items-start mb-12">
          <a href="/" className="text-[#3b6e75] hover:text-[#a8b8bf] transition-colors bg-[#0b0d10] px-3 py-1 border border-[#1b2b34]">
            &lt; FluxOS
          </a>
          <div className="text-right hidden sm:block bg-[#0b0d10] px-3 py-1 border border-[#1b2b34]">
            <p className="text-[#2d4f56]">AGENTS: <span className="text-[#a8b8bf]">READY</span></p>
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 flex items-start justify-center">
          <div className="max-w-2xl w-full space-y-8 bg-[#0b0d10] p-6 md:p-8 border border-[#1b2b34]">
            {/* Header */}
            <div className="space-y-3">
              <h1 className="text-[#a8b8bf] text-xl md:text-2xl font-mono leading-tight">
                Stop building automations.<br />
                Start running your business.
              </h1>
              <p className="text-[#5a6f7a] text-sm">
                Tell us what your business does. We&apos;ll show you exactly which AI agents can run it.
              </p>
            </div>

            {/* State 1: Input */}
            {(state === 'input' || state === 'generating') && (
              <div className="space-y-4">
                <div className="border border-[#1b2b34] bg-[#0d1117] p-4">
                  <label className="block text-[#3b6e75] text-xs mb-2 uppercase tracking-wider">
                    What does your business do?
                  </label>
                  <textarea
                    value={businessDescription}
                    onChange={(e) => setBusinessDescription(e.target.value)}
                    placeholder="e.g. I run a digital marketing agency with 15 clients. We handle social media, SEO, and content creation."
                    maxLength={500}
                    className="w-full bg-transparent text-[#a8b8bf] placeholder-[#2d4f56] border-none outline-none resize-none font-mono text-sm leading-relaxed min-h-[100px]"
                    disabled={state === 'generating'}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && e.metaKey && state === 'input') {
                        handleGenerate()
                      }
                    }}
                  />
                </div>

                {state === 'input' && (
                  <button
                    onClick={handleGenerate}
                    disabled={!businessDescription.trim()}
                    className="w-full border border-[#3b6e75] text-[#a8b8bf] py-3 px-6 font-mono text-sm uppercase tracking-wider hover:bg-[#3b6e75]/20 hover:border-[#a8b8bf]/40 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    Generate My Plan
                  </button>
                )}
              </div>
            )}

            {/* State 2: Generating — Animated Progress Stages */}
            {state === 'generating' && (
              <div className="border border-[#1b2b34] bg-[#0d1117] p-4 space-y-4">
                {/* Progress bar + elapsed timer */}
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-1.5 bg-[#1b2b34] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#3b6e75] rounded-full transition-all duration-500 ease-out"
                      style={{ width: `${progressPercent}%` }}
                    />
                  </div>
                  <span className="text-[#485a62] text-xs tabular-nums shrink-0">
                    {formatTime(elapsedSeconds)}
                  </span>
                </div>

                {/* Stages — rolling window */}
                <div className="max-h-[140px] overflow-y-auto scrollbar-hide">
                  <div className="space-y-3">
                    {STAGES.map((stage, i) => {
                      const isCompleted = activeStage > i
                      const isActive = activeStage === i
                      const isPending = activeStage < i

                      return (
                        <div
                          key={i}
                          className={`transition-opacity duration-500 ${
                            isPending ? 'opacity-20' : 'opacity-100'
                          }`}
                        >
                          {/* Stage header */}
                          <div className="flex items-center gap-2">
                            <span className={`text-xs w-4 text-center ${
                              isCompleted ? 'text-[#3b6e75]' : isActive ? 'text-[#a8b8bf]' : 'text-[#2d4f56]'
                            }`}>
                              {isCompleted ? '✓' : isActive ? '●' : '○'}
                            </span>
                            <span className={`text-xs font-bold tracking-wider ${
                              isCompleted ? 'text-[#3b6e75]' : isActive ? 'text-[#a8b8bf]' : 'text-[#2d4f56]'
                            }`}>
                              {stage.label}
                            </span>
                          </div>

                          {/* Description + logs (only for active/completed) */}
                          {(isActive || isCompleted) && (
                            <div className="ml-6 mt-1 space-y-0.5">
                              <p className={`text-xs ${isActive ? 'text-[#5a6f7a]' : 'text-[#3b5a62]'}`}>
                                {stage.description}
                              </p>
                              {stage.logs.map((log, logIdx) => {
                                const logCount = visibleLogs[i] || 0
                                if (logIdx >= logCount) return null
                                return (
                                  <p
                                    key={logIdx}
                                    className="text-[#2d4f56] text-xs animate-fadeIn"
                                  >
                                    {log}
                                  </p>
                                )
                              })}
                              {isActive && (
                                <span className="text-[#3b6e75] animate-pulse text-xs">_</span>
                              )}
                            </div>
                          )}
                        </div>
                      )
                    })}
                    <div ref={stagesEndRef} />
                  </div>
                </div>
              </div>
            )}

            {/* State 3: Plan */}
            {(state === 'plan' || state === 'captured') && plan && (
              <div ref={planRef} className="space-y-6">
                {/* Plan steps */}
                <div className="border border-[#1b2b34] bg-[#0d1117] divide-y divide-[#1b2b34]">
                  {plan.steps.map((step, i) => (
                    <div key={step.id} className="p-4 space-y-1">
                      <div className="flex items-baseline gap-3">
                        <span className="text-[#485a62] text-xs shrink-0">
                          STEP {i + 1}
                        </span>
                        <span className="text-base shrink-0" aria-hidden="true">
                          {step.is_scheduled ? '⏰' : '🤖'}
                        </span>
                      </div>
                      <p className="text-[#a8b8bf] text-sm">{step.display_name || step.name}</p>
                      <p className="text-[#5a6f7a] text-xs">{step.description}</p>
                    </div>
                  ))}

                  <div className="p-4 text-center text-[#3b6e75] text-xs">
                    + more automations tailored to your business
                  </div>
                </div>

                {/* Email capture (State 3 only) */}
                {state === 'plan' && (
                  <form onSubmit={handleJoinWaitlist} className="space-y-4">
                    <p className="text-[#3b6e75] text-sm uppercase tracking-wider">
                      Save your plan & get early access
                    </p>
                    <div className="space-y-3">
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="your@email.com"
                        required
                        className="w-full bg-[#0d1117] border border-[#1b2b34] text-[#a8b8bf] placeholder-[#2d4f56] p-3 font-mono text-sm outline-none focus:border-[#3b6e75] transition-colors"
                      />
                      <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Name (optional)"
                        className="w-full bg-[#0d1117] border border-[#1b2b34] text-[#a8b8bf] placeholder-[#2d4f56] p-3 font-mono text-sm outline-none focus:border-[#3b6e75] transition-colors"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={!email.trim() || submitting}
                      className="w-full border border-[#3b6e75] text-[#a8b8bf] py-3 px-6 font-mono text-sm uppercase tracking-wider hover:bg-[#3b6e75]/20 hover:border-[#a8b8bf]/40 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      {submitting ? 'Submitting...' : 'Join the Waitlist'}
                    </button>
                  </form>
                )}

                {/* State 4: Captured */}
                {state === 'captured' && (
                  <div className="border border-[#3b6e75]/50 bg-[#0d1117] p-4">
                    <p className="text-[#a8b8bf] text-sm font-mono">
                      You&apos;re in. We&apos;ll get back to you.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Error */}
            {error && (
              <p className="text-red-400/80 text-xs font-mono">{error}</p>
            )}

            {/* Scarcity footer */}
            {state !== 'captured' && (
              <p className="text-[#2d4f56] text-xs font-mono">
                Only 50 spots available.
              </p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-between items-end text-[#485a62] mt-12">
          <p className="text-[#2d4f56] text-xs bg-[#0b0d10] px-3 py-1 border border-[#1b2b34]">This page was planned and built by fluxos agents.</p>
          <a
            href="https://fluxtopus.com"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-[#3b6e75] transition-colors bg-[#0b0d10] px-3 py-1 border border-[#1b2b34]"
          >
            [SITE]
          </a>
        </div>
      </div>
    </main>
  )
}
