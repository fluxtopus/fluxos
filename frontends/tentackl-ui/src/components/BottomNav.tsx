'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  InboxIcon,
  RectangleStackIcon,
  ArrowPathIcon,
  CogIcon,
} from '@heroicons/react/24/outline';
import { useInboxStore } from '../store/inboxStore';

const tabs = [
  { name: 'Inbox', href: '/inbox', icon: InboxIcon },
  { name: 'Tasks', href: '/tasks', icon: RectangleStackIcon },
  { name: 'Auto', href: '/automations', icon: ArrowPathIcon },
  { name: 'Settings', href: '/settings', icon: CogIcon },
] as const;

function isTabActive(tabHref: string, pathname: string): boolean {
  if (tabHref === '/settings') {
    return pathname.startsWith('/settings');
  }
  return pathname === tabHref || pathname.startsWith(tabHref + '/');
}

export function BottomNav() {
  const pathname = usePathname();
  const { unreadCount } = useInboxStore();
  const [keyboardOpen, setKeyboardOpen] = useState(false);

  // Hide bottom nav when virtual keyboard is open
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;

    const handleResize = () => {
      setKeyboardOpen(vv.height < window.innerHeight * 0.75);
    };

    vv.addEventListener('resize', handleResize);
    return () => vv.removeEventListener('resize', handleResize);
  }, []);

  if (keyboardOpen) return null;

  return (
    <nav className="fixed bottom-0 inset-x-0 z-40 lg:hidden bg-[var(--card)]/95 backdrop-blur-md border-t border-[var(--border)] pb-[env(safe-area-inset-bottom)]">
      <div className="flex items-center justify-around h-16">
        {tabs.map((tab) => {
          const active = isTabActive(tab.href, pathname);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className="relative flex flex-col items-center justify-center flex-1 h-full min-w-[44px] min-h-[44px] transition-colors"
            >
              <div className="relative">
                <tab.icon
                  className={`w-6 h-6 transition-colors ${
                    active
                      ? 'text-[var(--accent)]'
                      : 'text-[var(--muted-foreground)]'
                  }`}
                />
                {tab.href === '/inbox' && unreadCount > 0 && (
                  <span className="absolute -top-1.5 -right-2.5 flex items-center justify-center min-w-[18px] h-[18px] px-1 text-[10px] font-bold rounded-full bg-[var(--accent)] text-[var(--accent-foreground)]">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </div>
              <span
                className={`mt-1 text-[10px] font-mono tracking-wider ${
                  active
                    ? 'text-[var(--accent)]'
                    : 'text-[var(--muted-foreground)]'
                }`}
              >
                {tab.name}
              </span>
              {active && (
                <motion.div
                  layoutId="bottomNavIndicator"
                  className="absolute top-0 left-3 right-3 h-0.5 bg-[var(--accent)] rounded-full"
                  transition={{ type: 'spring', stiffness: 500, damping: 35 }}
                />
              )}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
