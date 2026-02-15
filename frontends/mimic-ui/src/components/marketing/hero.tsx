"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import Link from "next/link"
import { Radio } from "lucide-react"

function MessageRelayBackground() {
  const [dots, setDots] = useState<Array<{ id: number; x: number; y: number; delay: number }>>([])

  useEffect(() => {
    const generatedDots = Array.from({ length: 50 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      delay: Math.random() * 5,
    }))
    setDots(generatedDots)
  }, [])

  return (
    <div className="absolute inset-0 overflow-hidden opacity-30">
      <svg width="100%" height="100%" className="absolute inset-0">
        <defs>
          <radialGradient id="dotGradient">
            <stop offset="0%" stopColor="oklch(0.75 0.15 45)" stopOpacity="1" />
            <stop offset="100%" stopColor="oklch(0.75 0.15 45)" stopOpacity="0" />
          </radialGradient>
        </defs>
        {dots.map((dot) => (
          <g key={dot.id}>
            <circle
              cx={`${dot.x}%`}
              cy={`${dot.y}%`}
              r="2"
              fill="url(#dotGradient)"
              className="animate-pulse"
              style={{ animationDelay: `${dot.delay}s` }}
            />
            <circle
              cx={`${dot.x}%`}
              cy={`${dot.y}%`}
              r="0"
              fill="none"
              stroke="oklch(0.75 0.15 45)"
              strokeWidth="1"
              opacity="0.4"
              className="message-wave"
              style={{ animationDelay: `${dot.delay}s` }}
            />
          </g>
        ))}
      </svg>
    </div>
  )
}

export function Hero() {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden bg-background">
      <MessageRelayBackground />

      <div className="absolute inset-0 flex items-center justify-center opacity-30">
        <div className="relative w-[800px] h-[800px]">
          {/* Concentric circles */}
          <div className="absolute inset-0 rounded-full border-2 border-primary/40 animate-pulse" />
          <div className="absolute inset-[10%] rounded-full border border-primary/30" />
          <div className="absolute inset-[20%] rounded-full border-2 border-primary/40" />
          <div className="absolute inset-[30%] rounded-full border border-primary/20" />
          <div className="absolute inset-[40%] rounded-full border border-primary/30" />

          {/* Cross hairs */}
          <div className="absolute top-1/2 left-0 w-full h-px bg-primary/30" />
          <div className="absolute left-1/2 top-0 w-px h-full bg-primary/30" />

          {/* Corner brackets */}
          <div className="absolute top-0 left-0 w-20 h-20 border-t-2 border-l-2 border-primary/50" />
          <div className="absolute top-0 right-0 w-20 h-20 border-t-2 border-r-2 border-primary/50" />
          <div className="absolute bottom-0 left-0 w-20 h-20 border-b-2 border-l-2 border-primary/50" />
          <div className="absolute bottom-0 right-0 w-20 h-20 border-b-2 border-r-2 border-primary/50" />

          {/* Diagonal scan lines */}
          <div className="absolute top-1/4 left-0 w-full h-px bg-gradient-to-r from-transparent via-primary/20 to-transparent rotate-45" />
          <div className="absolute top-3/4 left-0 w-full h-px bg-gradient-to-r from-transparent via-primary/20 to-transparent -rotate-45" />
        </div>
      </div>

      {/* Corner status indicators */}
      <div className="absolute top-6 left-6 font-mono text-xs text-muted-foreground space-y-1 z-20">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-primary rounded-full pulse-glow" />
          <span>SYSTEM ONLINE</span>
        </div>
        <div className="opacity-70">STATUS: OPERATIONAL</div>
        <div className="opacity-70">MODE: MULTI-CHANNEL</div>
        <div className="opacity-70">UPTIME: 99.999%</div>
      </div>

      <div className="absolute top-6 right-6 font-mono text-xs text-muted-foreground text-right space-y-1 z-20">
        <div className="opacity-70">PROTOCOL: E2E-ENCRYPTED</div>
        <div className="opacity-70">DELIVERY: GUARANTEED</div>
        <div className="opacity-70">LATENCY: {"<"}100MS</div>
        <div className="flex items-center gap-2 justify-end">
          <span>PROVIDERS: ACTIVE</span>
          <div className="w-2 h-2 bg-primary rounded-full pulse-glow" />
        </div>
      </div>

      <div className="absolute bottom-6 left-6 font-mono text-xs text-muted-foreground space-y-1 z-20">
        <div className="opacity-70">API VERSION: v2.1.0</div>
        <div className="opacity-70">BUILD: 2025.11.28</div>
      </div>

      <div className="absolute bottom-6 right-6 font-mono text-xs text-muted-foreground text-right z-20">
        <div className="opacity-70">PROCESSED TODAY: 2.4M+</div>
      </div>

      {/* Main content */}
      <div className="relative z-10 max-w-6xl mx-auto px-6 text-center">
        <div
          className={`transition-all duration-1000 ${mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-10"}`}
        >
          <div className="mb-8 flex items-center justify-center gap-4">
            <Radio className="w-12 h-12 text-primary" strokeWidth={1.5} />
            <h1 className="text-7xl md:text-9xl font-bold tracking-tight text-foreground">MIMIC</h1>
          </div>

          <p className="font-mono text-sm text-primary mb-6 tracking-wider">
            // UNIFIED NOTIFICATION ORCHESTRATION PLATFORM
          </p>

          <h2 className="text-3xl md:text-5xl font-bold mb-6 max-w-4xl mx-auto leading-tight text-balance">
            Mission Control for Your Notification Infrastructure
          </h2>

          <p className="text-lg md:text-xl text-muted-foreground mb-12 max-w-2xl mx-auto leading-relaxed">
            Orchestrate and deliver notifications across multiple channels with military-grade precision. Email, SMS,
            Slack, Discord, Telegram, webhooks—all from one unified platform.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Button
              size="lg"
              className="font-mono text-base px-8 py-6 bg-primary text-primary-foreground hover:bg-primary/90"
              asChild
            >
              <Link href="#demo">TRY DEMO</Link>
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="font-mono text-base px-8 py-6 border-primary text-primary hover:bg-primary/10 bg-transparent"
              asChild
            >
              <Link href="#specs">VIEW SPECS</Link>
            </Button>
          </div>

          <div className="mt-16 flex flex-wrap gap-3 justify-center items-center text-sm font-mono">
            <div className="flex items-center gap-2 px-4 py-2 bg-card/80 border border-border rounded backdrop-blur">
              <div className="w-2 h-2 bg-primary rounded-full" />
              <span>Node.js SDK</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 bg-card/80 border border-border rounded backdrop-blur">
              <div className="w-2 h-2 bg-primary rounded-full" />
              <span>Python SDK</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 bg-card/80 border border-border rounded backdrop-blur">
              <div className="w-2 h-2 bg-primary rounded-full" />
              <span>REST API</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 bg-card/80 border border-border rounded backdrop-blur">
              <div className="w-2 h-2 bg-primary rounded-full" />
              <span>GraphQL</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 bg-card/80 border border-border rounded backdrop-blur">
              <div className="w-2 h-2 bg-primary rounded-full" />
              <span>Webhooks</span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom metrics bar */}
      <div className="absolute bottom-0 left-0 right-0 h-16 bg-card/50 backdrop-blur border-t border-border z-20">
        <div className="max-w-7xl mx-auto px-6 h-full flex items-center justify-between">
          <div className="flex gap-8 font-mono text-xs">
            <div>
              <span className="text-muted-foreground">UPTIME: </span>
              <span className="text-foreground font-semibold">99.999%</span>
            </div>
            <div>
              <span className="text-muted-foreground">LATENCY: </span>
              <span className="text-foreground font-semibold">{"<"}100ms</span>
            </div>
            <div>
              <span className="text-muted-foreground">CHANNELS: </span>
              <span className="text-foreground font-semibold">6+</span>
            </div>
          </div>
          <div className="font-mono text-xs text-muted-foreground">
            PROCESSED TODAY: <span className="text-primary font-semibold">2,431,829</span>
          </div>
        </div>
      </div>
    </section>
  )
}
