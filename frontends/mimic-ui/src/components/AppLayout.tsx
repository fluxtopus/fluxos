'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { StatusIndicator } from './tactical'
import { Radio } from 'lucide-react'

interface AppLayoutProps {
  children: React.ReactNode
}

export default function AppLayout({ children }: AppLayoutProps) {
  const [user, setUser] = useState<any>(null)
  const pathname = usePathname()

  useEffect(() => {
    // Fetch user info
    const apiKey = localStorage.getItem('api_key')
    if (apiKey) {
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/me`, {
        headers: {
          'Authorization': `Bearer ${apiKey}`
        }
      })
        .then(res => res.json())
        .then(data => setUser(data))
        .catch(() => {})
    }
  }, [])

  const navLinks = [
    { href: '/dashboard', label: 'DASHBOARD' },
    { href: '/send', label: 'SEND' },
    { href: '/workflows', label: 'WORKFLOWS' },
    { href: '/providers', label: 'PROVIDERS' },
    { href: '/logs', label: 'LOGS' },
  ]

  return (
    <div className="min-h-screen relative">
      {/* Grid overlay background */}
      <div className="fixed inset-0 bg-[linear-gradient(to_right,oklch(0.26_0.01_260)_1px,transparent_1px),linear-gradient(to_bottom,oklch(0.26_0.01_260)_1px,transparent_1px)] bg-[size:2rem_2rem] opacity-10 pointer-events-none" />

      {/* Navigation Bar */}
      <nav className="relative border-b border-border bg-card/30 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-20">
            {/* Logo/Branding */}
            <div className="flex items-center gap-8">
              <Link href="/dashboard" className="flex items-center gap-3">
                <Radio className="w-8 h-8 text-primary" strokeWidth={1.5} />
                <div>
                  <h1 className="text-2xl font-bold font-sans uppercase tracking-wider text-primary">
                    MIMIC
                  </h1>
                  <div className="text-xs text-muted-foreground font-mono uppercase tracking-widest">
                    v1.0.0 | OPERATIONAL
                  </div>
                </div>
              </Link>

              {/* Nav Links */}
              <div className="hidden md:flex ml-8 space-x-1">
                {navLinks.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`
                      relative px-4 py-2 text-sm font-mono font-medium uppercase tracking-wide
                      transition-all duration-300
                      ${pathname === link.href
                        ? 'text-primary'
                        : 'text-muted-foreground hover:text-primary'
                      }
                    `}
                  >
                    {link.label}
                    {pathname === link.href && (
                      <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-primary to-transparent shadow-[0_0_10px_oklch(0.75_0.15_45/0.8)]" />
                    )}
                  </Link>
                ))}
              </div>
            </div>

            {/* User Info */}
            <div className="flex items-center gap-4">
              {user && (
                <div className="flex items-center gap-3">
                  <StatusIndicator status="online" pulse />
                  <span className="text-muted-foreground font-mono text-sm uppercase tracking-wide">
                    {user.email}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="relative max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  )
}
