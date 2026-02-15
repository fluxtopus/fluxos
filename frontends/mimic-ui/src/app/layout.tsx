import './globals.css'
import type { Metadata } from 'next'
import { Rajdhani, Space_Mono } from 'next/font/google'

const rajdhani = Rajdhani({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-sans',
})

const spaceMono = Space_Mono({
  subsets: ['latin'],
  weight: ['400', '700'],
  variable: '--font-mono',
})

export const metadata: Metadata = {
  title: 'MIMIC - Notification Workflow Management Platform',
  description:
    'Mission control for your notification infrastructure. Orchestrate and deliver notifications across email, SMS, Slack, Discord, Telegram, and webhooks with military-grade precision.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${rajdhani.variable} ${spaceMono.variable} font-sans antialiased`}>
        {children}
      </body>
    </html>
  )
}

