import { CheckCircleIcon, RocketLaunchIcon } from '@heroicons/react/24/solid'
import Link from 'next/link'

export default function CheckoutSuccess() {
  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="max-w-2xl w-full text-center">
        <div className="inline-flex items-center justify-center w-20 h-20 mb-8 rounded-full bg-primary/10">
          <CheckCircleIcon className="w-12 h-12 text-primary" />
        </div>

        <h1 className="text-4xl md:text-5xl font-bold mb-4">Welcome to aios!</h1>

        <p className="text-xl text-muted-foreground mb-8">
          Your infrastructure is being provisioned. Check your email for credentials and setup instructions.
        </p>

        <div className="p-6 border border-border rounded-lg bg-card mb-8">
          <h2 className="text-lg font-semibold mb-3">What happens next?</h2>
          <ul className="space-y-3 text-left text-muted-foreground">
            <li className="flex items-start gap-3">
              <span className="text-primary font-mono">1.</span>
              <span>We&apos;re provisioning your isolated cell</span>
            </li>
            <li className="flex items-start gap-3">
              <span className="text-primary font-mono">2.</span>
              <span>You&apos;ll receive an email with your API credentials and dashboard access</span>
            </li>
            <li className="flex items-start gap-3">
              <span className="text-primary font-mono">3.</span>
              <span>Your services will be live and ready to use within 5 minutes</span>
            </li>
          </ul>
        </div>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href="https://docs.fluxtopus.com"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 border border-border rounded-lg hover:bg-muted transition-colors"
          >
            Read Documentation
          </Link>
          <Link
            href="/"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
          >
            <RocketLaunchIcon className="w-5 h-5" />
            Back to Home
          </Link>
        </div>
      </div>
    </div>
  )
}
