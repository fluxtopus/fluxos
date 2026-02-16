import { CheckIcon } from '@heroicons/react/24/solid'

interface PricingTier {
  name: string
  price: string
  description: string
  features: string[]
  cta: string
  popular?: boolean
}

const tiers: PricingTier[] = [
  {
    name: 'Starter',
    price: '$29',
    description: 'For solo operators getting started',
    features: [
      '5 active workflows',
      'AI agents plan & execute tasks',
      'Email & push notifications',
      'Secure team login',
      'Inbox for approvals & updates',
      'Email support',
    ],
    cta: 'Start Free Trial',
  },
  {
    name: 'Growth',
    price: '$49',
    description: 'For small teams scaling up',
    features: [
      '25 active workflows',
      'Everything in Starter',
      'Smart preference learning',
      'Self-healing workflows',
      'Multi-channel notifications',
      'Priority support',
    ],
    cta: 'Start Free Trial',
  },
  {
    name: 'Business',
    price: '$99',
    description: 'For businesses that never stop',
    features: [
      'Unlimited workflows',
      'Everything in Growth',
      'Dedicated private workspace',
      'Advanced agent capabilities',
      'Custom integrations',
      'Priority support & onboarding',
      'Custom domain',
      'SLA guarantee',
    ],
    cta: 'Start Free Trial',
    popular: true,
  },
]

export default function Pricing() {
  return (
    <section id="pricing" className="py-20 px-4 bg-muted/20">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            Simple, Transparent Pricing
          </h2>
          <p className="text-xl text-muted-foreground">
            Choose the services you need. Scale as you grow.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
          {tiers.map((tier, index) => (
            <div
              key={index}
              className={`relative p-8 border rounded-lg bg-card transition-all hover:scale-105 ${
                tier.popular
                  ? 'border-primary shadow-lg shadow-primary/20'
                  : 'border-border hover:border-primary/50'
              }`}
            >
              {tier.popular && (
                <div className="absolute -top-4 left-1/2 -translate-x-1/2 px-4 py-1 bg-primary text-primary-foreground text-sm font-semibold rounded-full">
                  Most Popular
                </div>
              )}

              <div className="mb-6">
                <h3 className="text-2xl font-bold mb-2">{tier.name}</h3>
                <div className="flex items-baseline gap-1 mb-2">
                  <span className="text-5xl font-bold text-primary">{tier.price}</span>
                  <span className="text-muted-foreground">/month</span>
                </div>
                <p className="text-muted-foreground">{tier.description}</p>
              </div>

              <ul className="space-y-3 mb-8">
                {tier.features.map((feature, featureIndex) => (
                  <li key={featureIndex} className="flex items-start gap-3">
                    <CheckIcon className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
                    <span className="text-sm">{feature}</span>
                  </li>
                ))}
              </ul>

              <button
                className={`w-full py-3 px-6 rounded-lg font-semibold transition-all ${
                  tier.popular
                    ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                    : 'border border-border hover:bg-primary hover:text-primary-foreground hover:border-primary'
                }`}
              >
                {tier.cta}
              </button>
            </div>
          ))}
        </div>

        <p className="text-center text-sm text-muted-foreground mt-8">
          All plans include private data isolation and 24/7 agent availability.
          <br />
          Questions? <a href="mailto:support@fluxtopus.com" className="text-primary hover:underline">Contact us</a>
        </p>
      </div>
    </section>
  )
}
