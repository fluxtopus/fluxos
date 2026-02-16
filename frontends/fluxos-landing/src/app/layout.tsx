import type { Metadata } from 'next'
import { Orbitron, Share_Tech_Mono } from 'next/font/google'
import { Providers } from './providers'
import './globals.css'

const orbitron = Orbitron({
  weight: ['400', '500', '600', '700', '800', '900'],
  subsets: ['latin'],
  variable: '--font-orbitron',
})

const shareTechMono = Share_Tech_Mono({
  weight: ['400'],
  subsets: ['latin'],
  variable: '--font-share-tech-mono',
})

export const metadata: Metadata = {
  metadataBase: new URL('https://fluxtopus.com'),
  title: 'fluxos',
  description: 'AI agents that run your business operations. Describe what you need, your agents handle the rest.',
  icons: {
    icon: '/favicon.png',
    shortcut: '/favicon.png',
    apple: '/favicon.png',
  },
  openGraph: {
    title: 'fluxos',
    description: 'AI agents that run your business operations. Describe what you need, your agents handle the rest.',
    url: 'https://fluxtopus.com',
    siteName: 'fluxos',
    images: [
      {
        url: '/social.png',
        width: 1200,
        height: 630,
        alt: 'fluxos - AI Agents for Your Business',
      },
    ],
    locale: 'en_US',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'fluxos',
    description: 'AI agents that run your business operations. Describe what you need, your agents handle the rest.',
    images: ['/social.png'],
    creator: '@jvivas_official',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${orbitron.variable} ${shareTechMono.variable} antialiased`}>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  )
}
