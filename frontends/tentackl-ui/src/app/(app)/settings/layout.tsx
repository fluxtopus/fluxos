'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const TABS = [
  { href: '/settings/account', label: 'ACCOUNT' },
  { href: '/settings/preferences', label: 'PREFERENCES' },
  { href: '/settings/integrations', label: 'INTEGRATIONS' },
  { href: '/settings/triggers', label: 'TRIGGERS' },
  { href: '/settings/agents', label: 'AGENTS' },
];

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-[var(--border)] bg-[var(--card)]">
        <div className="max-w-4xl mx-auto px-4 lg:px-6 py-6">
          <h1 className="text-xl font-bold text-[var(--foreground)] tracking-tight">
            Settings
          </h1>
          <p className="text-xs font-mono text-[var(--muted-foreground)] mt-1 tracking-wider">
            CONFIGURE YOUR WORKSPACE
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="max-w-4xl mx-auto px-4 lg:px-6">
        <nav className="flex gap-1 border-b border-[var(--border)] -mb-px overflow-x-auto scrollbar-hide">
          {TABS.map((tab) => {
            const isActive = pathname === tab.href;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`px-3 lg:px-4 py-3 text-xs font-mono tracking-wider border-b-2 transition-colors whitespace-nowrap flex-shrink-0 ${
                  isActive
                    ? 'border-[var(--accent)] text-[var(--accent)]'
                    : 'border-transparent text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
                }`}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>

        <div className="py-6 lg:py-8">{children}</div>
      </div>
    </div>
  );
}
