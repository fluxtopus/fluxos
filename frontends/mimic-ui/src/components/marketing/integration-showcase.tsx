"use client"

import { Card } from "@/components/ui/card"
import { Mail, MessageSquare, Smartphone, Send, Webhook, MessageCircle } from "lucide-react"

const integrations = [
  {
    icon: Mail,
    name: "Email",
    providers: ["SendGrid", "Mailgun", "AWS SES", "Postmark"],
    color: "text-blue-500",
  },
  {
    icon: Smartphone,
    name: "SMS",
    providers: ["Twilio", "Vonage", "AWS SNS", "MessageBird"],
    color: "text-green-500",
  },
  {
    icon: MessageSquare,
    name: "Slack",
    providers: ["Slack API", "Incoming Webhooks"],
    color: "text-purple-500",
  },
  {
    icon: MessageCircle,
    name: "Discord",
    providers: ["Discord Webhooks", "Bot API"],
    color: "text-indigo-500",
  },
  {
    icon: Send,
    name: "Telegram",
    providers: ["Telegram Bot API"],
    color: "text-cyan-500",
  },
  {
    icon: Webhook,
    name: "Webhooks",
    providers: ["Custom HTTP Endpoints"],
    color: "text-orange-500",
  },
]

export function IntegrationShowcase() {
  return (
    <section className="py-24 bg-card/30 relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,oklch(0.3_0.05_260)_0%,transparent_70%)] opacity-50" />

      <div className="max-w-7xl mx-auto px-6 relative z-10">
        <div className="text-center mb-16">
          <p className="font-mono text-sm text-primary mb-4 tracking-wider">// MULTI-CHANNEL DELIVERY</p>
          <h2 className="text-4xl md:text-5xl font-bold mb-4 text-balance">Connect Any Notification Provider</h2>
          <p className="text-muted-foreground text-lg max-w-2xl mx-auto leading-relaxed">
            Bring your own API keys and integrate with leading providers across all channels. Switch providers without
            changing a single line of code.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {integrations.map((integration, index) => (
            <Card
              key={index}
              className="p-6 bg-background/80 backdrop-blur border-border hover:border-primary/50 transition-all duration-300"
            >
              <div className="flex items-start gap-4">
                <div
                  className={`w-12 h-12 rounded-lg bg-card flex items-center justify-center flex-shrink-0 border border-border`}
                >
                  <integration.icon className={`w-6 h-6 ${integration.color}`} />
                </div>
                <div className="flex-1">
                  <h3 className="text-lg font-semibold mb-3">{integration.name}</h3>
                  <div className="space-y-1">
                    {integration.providers.map((provider, i) => (
                      <div key={i} className="text-sm text-muted-foreground font-mono flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-primary/50" />
                        {provider}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>

        <div className="mt-12 text-center">
          <p className="font-mono text-sm text-primary">+ Custom provider integration support</p>
        </div>
      </div>
    </section>
  )
}
