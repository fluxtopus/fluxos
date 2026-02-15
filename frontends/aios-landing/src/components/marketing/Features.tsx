import {
  ChatBubbleBottomCenterTextIcon,
  ArrowPathIcon,
  ShieldCheckIcon,
  BoltIcon,
  BellAlertIcon,
  WrenchScrewdriverIcon,
} from '@heroicons/react/24/outline'

const features = [
  {
    icon: ChatBubbleBottomCenterTextIcon,
    title: 'Just Say What You Need',
    description: 'Describe your goal in plain English. No templates, no drag-and-drop builders, no coding. Your AI agents figure out the steps.',
  },
  {
    icon: BoltIcon,
    title: 'Approve Once, Runs Forever',
    description: 'Your agents ask permission the first time. After that, they learn your preferences and handle it automatically.',
  },
  {
    icon: WrenchScrewdriverIcon,
    title: 'Self-Healing Workflows',
    description: 'When something breaks, your agents replan and recover on their own. You get notified, not stuck.',
  },
  {
    icon: BellAlertIcon,
    title: 'Customers Stay in the Loop',
    description: 'Send the right message at the right time — emails, alerts, follow-ups — across every channel, without lifting a finger.',
  },
  {
    icon: ShieldCheckIcon,
    title: 'Your Data Stays Yours',
    description: 'Every business gets its own private workspace. Your data is isolated and secure by default.',
  },
  {
    icon: ArrowPathIcon,
    title: 'Works While You Sleep',
    description: 'Agents run 24/7 — checking weather, processing orders, sending reports — so you can focus on growing your business.',
  },
]

export default function Features() {
  return (
    <section id="features" className="py-20 px-4">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            How It Works
          </h2>
          <p className="text-xl text-muted-foreground">
            AI agents that understand your business and get things done
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
          {features.map((feature, index) => (
            <div
              key={index}
              className="group p-6 border border-border rounded-lg bg-card hover:bg-card/80 transition-all hover:scale-105 hover:border-primary/50"
            >
              <div className="inline-flex items-center justify-center w-12 h-12 mb-4 rounded-lg bg-primary/10 group-hover:bg-primary/20 transition-colors">
                <feature.icon className="w-6 h-6 text-primary" />
              </div>
              <h3 className="text-xl font-semibold mb-2">{feature.title}</h3>
              <p className="text-muted-foreground">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
