"use client"

import { Card } from "@/components/ui/card"
import { Bell, ShoppingCart, Shield, TrendingUp, Users, Zap } from "lucide-react"

const useCases = [
  {
    icon: Bell,
    title: "Transactional Alerts",
    description: "Order confirmations, shipping updates, payment receipts, and account notifications.",
    metrics: "99.99% delivery rate",
  },
  {
    icon: Users,
    title: "User Engagement",
    description: "Onboarding sequences, feature announcements, re-engagement campaigns, and newsletters.",
    metrics: "3x higher engagement",
  },
  {
    icon: Shield,
    title: "Security & Compliance",
    description: "2FA codes, login alerts, password resets, and security breach notifications.",
    metrics: "<50ms average latency",
  },
  {
    icon: TrendingUp,
    title: "Marketing Automation",
    description: "Drip campaigns, promotional offers, event reminders, and personalized recommendations.",
    metrics: "5x ROI improvement",
  },
  {
    icon: ShoppingCart,
    title: "E-commerce",
    description: "Cart abandonment, inventory alerts, flash sales, and customer support updates.",
    metrics: "24/7 uptime",
  },
  {
    icon: Zap,
    title: "Real-time Monitoring",
    description: "System alerts, error notifications, performance metrics, and incident management.",
    metrics: "Instant delivery",
  },
]

export function UseCases() {
  return (
    <section className="py-24 relative">
      <div className="max-w-7xl mx-auto px-6 relative z-10">
        <div className="text-center mb-16">
          <p className="font-mono text-sm text-primary mb-4 tracking-wider">// DEPLOYMENT SCENARIOS</p>
          <h2 className="text-4xl md:text-5xl font-bold mb-4 text-balance">Built for Every Use Case</h2>
          <p className="text-muted-foreground text-lg max-w-2xl mx-auto leading-relaxed">
            From startups to enterprise, MIMIC scales to handle any notification requirement with precision and
            reliability.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {useCases.map((useCase, index) => (
            <Card
              key={index}
              className="p-6 bg-card/50 backdrop-blur border-border hover:border-primary/30 transition-all duration-300 group"
            >
              <div className="mb-4">
                <div className="w-12 h-12 rounded bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                  <useCase.icon className="w-6 h-6 text-primary" />
                </div>
                <h3 className="text-xl font-semibold mb-2">{useCase.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed mb-3">{useCase.description}</p>
                <div className="font-mono text-xs text-primary border-t border-border pt-3">{useCase.metrics}</div>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </section>
  )
}
