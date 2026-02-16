import type { Metadata, Viewport } from 'next';
import { Share_Tech, Share_Tech_Mono } from 'next/font/google';
import { Providers } from './providers';
import { AuthInitializer } from '../components/Auth/AuthInitializer';
import './globals.css';

const shareTech = Share_Tech({
  weight: ['400'],
  subsets: ['latin'],
  variable: '--font-share-tech',
});

const shareTechMono = Share_Tech_Mono({
  weight: ['400'],
  subsets: ['latin'],
  variable: '--font-share-tech-mono',
});

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: 'cover',
  interactiveWidget: 'resizes-visual',
};

export const metadata: Metadata = {
  title: 'FluxOS - Multi-Agent Workflow Orchestration',
  description: 'Describe it. Watch it build. See it run.',
  manifest: '/manifest.json',
  appleWebApp: { capable: true, statusBarStyle: 'black-translucent', title: 'FluxOS' },
  icons: {
    icon: '/favicon.png',
    apple: '/apple-touch-icon.png',
  },
};

/**
 * Root layout - provides global providers only
 * Individual route groups have their own layouts for navigation
 */
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${shareTech.variable} ${shareTechMono.variable} min-h-screen bg-[var(--background)] grid-pattern`}>
        <Providers>
          <AuthInitializer />
          {children}
        </Providers>
      </body>
    </html>
  );
}
