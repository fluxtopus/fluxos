import { XCircleIcon, ArrowLeftIcon } from '@heroicons/react/24/outline'
import Link from 'next/link'

export default function CheckoutCancel() {
  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="max-w-2xl w-full text-center">
        <div className="inline-flex items-center justify-center w-20 h-20 mb-8 rounded-full bg-muted">
          <XCircleIcon className="w-12 h-12 text-muted-foreground" />
        </div>

        <h1 className="text-4xl md:text-5xl font-bold mb-4">
          Checkout Canceled
        </h1>

        <p className="text-xl text-muted-foreground mb-8">
          No worries! Your payment was not processed. We&apos;ll be here when you&apos;re ready to get started.
        </p>

        <div className="p-6 border border-border rounded-lg bg-card mb-8">
          <h2 className="text-lg font-semibold mb-3">Questions before you start?</h2>
          <p className="text-muted-foreground mb-4">
            Check out our documentation or reach out to our team. We&apos;re happy to help you choose the right plan.
          </p>
          <div className="flex flex-wrap gap-3 justify-center text-sm">
            <a
              href="https://docs.fluxtopus.com"
              className="px-4 py-2 border border-border rounded hover:bg-muted transition-colors"
            >
              Documentation
            </a>
            <a
              href="mailto:support@fluxtopus.com"
              className="px-4 py-2 border border-border rounded hover:bg-muted transition-colors"
            >
              Contact Support
            </a>
            <a
              href="https://fluxtopus.com"
              className="px-4 py-2 border border-border rounded hover:bg-muted transition-colors"
            >
              Home
            </a>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href="/#pricing"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 border border-border rounded-lg hover:bg-muted transition-colors"
          >
            <ArrowLeftIcon className="w-5 h-5" />
            View Pricing
          </Link>
          <Link
            href="/"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
          >
            Back to Home
          </Link>
        </div>
      </div>
    </div>
  )
}
