import type { Metadata } from 'next'
import WaitlistFlow from '@/components/waitlist/WaitlistFlow'

export const metadata: Metadata = {
  title: 'Automate Your Business | fluxos',
  description: 'Tell us what your business does. AI agents will show you exactly how to automate it.',
  openGraph: {
    title: 'Automate Your Business | fluxos',
    description: 'Tell us what your business does. AI agents will show you exactly how to automate it.',
    url: 'https://fluxtopus.com/automate-your-business',
    siteName: 'fluxos',
    images: [
      {
        url: '/social.png',
        width: 1200,
        height: 630,
        alt: 'fluxos - Automate Your Business',
      },
    ],
    locale: 'en_US',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Automate Your Business | fluxos',
    description: 'Tell us what your business does. AI agents will show you exactly how to automate it.',
    images: ['/social.png'],
    creator: '@jvivas_official',
  },
}

export default function AutomateYourBusinessPage() {
  return <WaitlistFlow />
}
