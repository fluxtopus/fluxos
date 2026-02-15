"use client"

import type React from "react"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card } from "@/components/ui/card"
import { Mail, MessageSquare, Send } from "lucide-react"

export function DemoSection() {
  const [email, setEmail] = useState("")
  const [phone, setPhone] = useState("")
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  const handleDemo = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 2000))

    setSent(true)
    setLoading(false)

    setTimeout(() => {
      setSent(false)
      setEmail("")
      setPhone("")
    }, 5000)
  }

  return (
    <section id="demo" className="py-24 relative">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_80%_at_50%_50%,oklch(0.75_0.15_45_/_0.1),transparent)]" />

      <div className="max-w-4xl mx-auto px-6 relative z-10">
        <div className="text-center mb-12">
          <p className="font-mono text-sm text-primary mb-4 tracking-wider">// LIVE DEMONSTRATION</p>
          <h2 className="text-4xl md:text-5xl font-bold mb-4">Test the System</h2>
          <p className="text-muted-foreground text-lg leading-relaxed">
            Experience MIMIC in action. Send yourself a notification and see our delivery pipeline at work.
          </p>
        </div>

        <Card className="p-8 bg-card/50 backdrop-blur border-primary/30">
          <form onSubmit={handleDemo} className="space-y-6">
            <div>
              <label htmlFor="email" className="font-mono text-sm text-primary mb-2 block">
                EMAIL ADDRESS
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
                <Input
                  id="email"
                  type="email"
                  placeholder="user@domain.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="pl-11 font-mono bg-background border-border"
                  required
                />
              </div>
            </div>

            <div>
              <label htmlFor="phone" className="font-mono text-sm text-primary mb-2 block">
                PHONE NUMBER <span className="text-muted-foreground">(OPTIONAL)</span>
              </label>
              <div className="relative">
                <MessageSquare className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
                <Input
                  id="phone"
                  type="tel"
                  placeholder="+1 (555) 000-0000"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="pl-11 font-mono bg-background border-border"
                />
              </div>
            </div>

            <Button
              type="submit"
              className="w-full font-mono text-base py-6 bg-primary text-primary-foreground hover:bg-primary/90 pulse-glow"
              disabled={loading || sent}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-current rounded-full flicker" />
                  TRANSMITTING...
                </span>
              ) : sent ? (
                <span className="flex items-center gap-2">
                  <Send className="w-5 h-5" />
                  NOTIFICATION SENT
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <Send className="w-5 h-5" />
                  SEND DEMO NOTIFICATION
                </span>
              )}
            </Button>
          </form>

          {sent && (
            <div className="mt-6 p-4 border border-primary/50 rounded bg-primary/10">
              <p className="font-mono text-sm text-primary">✓ Notification dispatched. Check your inbox and phone.</p>
            </div>
          )}

          <div className="mt-8 pt-8 border-t border-border">
            <p className="font-mono text-xs text-muted-foreground text-center">
              ENCRYPTED TRANSMISSION // REAL-TIME DELIVERY // ACTIVITY LOGGED
            </p>
          </div>
        </Card>
      </div>
    </section>
  )
}
