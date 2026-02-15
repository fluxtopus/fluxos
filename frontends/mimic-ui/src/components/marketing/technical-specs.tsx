"use client"

export function TechnicalSpecs() {
  const channels = ["EMAIL", "SMS", "SLACK", "DISCORD", "TELEGRAM", "WEBHOOK"]
  const providers = ["SENDGRID", "TWILIO", "AWS SES", "MAILGUN", "POSTMARK", "RESEND"]

  return (
    <section id="specs" className="py-24 bg-card/30 relative">
      <div className="max-w-7xl mx-auto px-6">
        <div className="text-center mb-16">
          <p className="font-mono text-sm text-primary mb-4 tracking-wider">// TECHNICAL SPECIFICATIONS</p>
          <h2 className="text-4xl md:text-5xl font-bold mb-4">Platform Architecture</h2>
        </div>

        <div className="grid md:grid-cols-2 gap-8">
          {/* Supported Channels */}
          <div className="border border-border rounded p-8 bg-background/50">
            <div className="flex items-center gap-2 mb-6">
              <div className="w-2 h-2 bg-primary rounded-full pulse-glow" />
              <h3 className="font-mono text-lg text-primary">SUPPORTED CHANNELS</h3>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {channels.map((channel, i) => (
                <div
                  key={i}
                  className="font-mono text-sm p-3 bg-muted/50 border border-border rounded flex items-center gap-2"
                >
                  <div className="w-1 h-4 bg-primary" />
                  {channel}
                </div>
              ))}
            </div>
          </div>

          {/* Provider Integration */}
          <div className="border border-border rounded p-8 bg-background/50">
            <div className="flex items-center gap-2 mb-6">
              <div className="w-2 h-2 bg-primary rounded-full pulse-glow" />
              <h3 className="font-mono text-lg text-primary">PROVIDER INTEGRATION</h3>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {providers.map((provider, i) => (
                <div
                  key={i}
                  className="font-mono text-sm p-3 bg-muted/50 border border-border rounded flex items-center gap-2"
                >
                  <div className="w-1 h-4 bg-primary" />
                  {provider}
                </div>
              ))}
            </div>
          </div>

          {/* API Endpoints */}
          <div className="border border-border rounded p-8 bg-background/50">
            <div className="flex items-center gap-2 mb-6">
              <div className="w-2 h-2 bg-primary rounded-full pulse-glow" />
              <h3 className="font-mono text-lg text-primary">API ENDPOINTS</h3>
            </div>
            <div className="space-y-2 font-mono text-sm">
              <div className="flex items-center gap-2">
                <span className="text-accent">POST</span>
                <span className="text-muted-foreground">/api/v1/notify</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-accent">GET</span>
                <span className="text-muted-foreground">/api/v1/status/:id</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-accent">POST</span>
                <span className="text-muted-foreground">/api/v1/workflow</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-accent">GET</span>
                <span className="text-muted-foreground">/api/v1/analytics</span>
              </div>
            </div>
          </div>

          {/* System Metrics */}
          <div className="border border-border rounded p-8 bg-background/50">
            <div className="flex items-center gap-2 mb-6">
              <div className="w-2 h-2 bg-primary rounded-full pulse-glow" />
              <h3 className="font-mono text-lg text-primary">SYSTEM METRICS</h3>
            </div>
            <div className="space-y-4 font-mono text-sm">
              <div>
                <div className="text-muted-foreground mb-1">UPTIME</div>
                <div className="text-2xl font-bold text-accent">99.99%</div>
              </div>
              <div>
                <div className="text-muted-foreground mb-1">AVG LATENCY</div>
                <div className="text-2xl font-bold text-accent">&lt;100ms</div>
              </div>
              <div>
                <div className="text-muted-foreground mb-1">THROUGHPUT</div>
                <div className="text-2xl font-bold text-accent">10K/sec</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
