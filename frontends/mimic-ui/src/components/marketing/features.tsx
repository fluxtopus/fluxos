"use client"

import { Shield, Zap, Network, Lock, CheckCircle2, Radio } from "lucide-react"
import { Card } from "@/components/ui/card"

const features = [
  {
    icon: Lock,
    label: "E2E ENCRYPTION",
    title: "End-to-End Encryption",
    description:
      "Military-grade encryption ensures your notification data remains secure throughout the entire delivery pipeline.",
  },
  {
    icon: CheckCircle2,
    label: "GUARANTEED DELIVERY",
    title: "Guaranteed Delivery",
    description:
      "Advanced retry mechanisms and fallback strategies ensure your notifications always reach their destination.",
  },
  {
    icon: Network,
    label: "MULTI-PROVIDER",
    title: "Multi-Provider Support",
    description: "Integrate with any provider using BYOK (Bring Your Own Key). Switch providers without changing code.",
  },
  {
    icon: Radio,
    label: "REAL-TIME MONITORING",
    title: "Real-Time Analytics",
    description:
      "Track delivery status, response times, and failure rates with precision monitoring and detailed logs.",
  },
  {
    icon: Zap,
    label: "WORKFLOW DESIGNER",
    title: "Visual Workflow Designer",
    description: "Build complex notification chains with our intuitive drag-and-drop interface. No code required.",
  },
  {
    icon: Shield,
    label: "TEMPLATE MANAGEMENT",
    title: "Template Management",
    description:
      "Create, version, and manage reusable notification templates across all channels from one central location.",
  },
]

export function Features() {
  return (
    <section className="py-24 relative">
      {/* Technical grid overlay */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,oklch(0.26_0.01_260)_1px,transparent_1px),linear-gradient(to_bottom,oklch(0.26_0.01_260)_1px,transparent_1px)] bg-[size:2rem_2rem] opacity-20" />

      <div className="max-w-7xl mx-auto px-6 relative z-10">
        <div className="text-center mb-16">
          <p className="font-mono text-sm text-primary mb-4 tracking-wider">// CORE CAPABILITIES</p>
          <h2 className="text-4xl md:text-5xl font-bold mb-4 text-balance">Built for Mission-Critical Notifications</h2>
          <p className="text-muted-foreground text-lg max-w-2xl mx-auto leading-relaxed">
            Deploy notification infrastructure that scales from startup to enterprise with zero downtime.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature, index) => (
            <Card
              key={index}
              className="p-6 bg-card/50 backdrop-blur border-border hover:border-primary/50 transition-all duration-300 group"
            >
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded bg-primary/10 flex items-center justify-center flex-shrink-0 group-hover:bg-primary/20 transition-colors">
                  <feature.icon className="w-6 h-6 text-primary" />
                </div>
                <div>
                  <div className="font-mono text-xs text-primary mb-2">{feature.label}</div>
                  <h3 className="text-lg font-semibold mb-2">{feature.title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">{feature.description}</p>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </section>
  )
}
