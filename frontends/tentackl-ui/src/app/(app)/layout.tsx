'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Menu, MenuButton, MenuItem, MenuItems } from '@headlessui/react';
import {
  Bars3Icon,
  XMarkIcon,
  RectangleStackIcon,
  InboxIcon,
  CogIcon,
  ArrowRightOnRectangleIcon,
  UserCircleIcon,
  PlusIcon,
  ArrowPathIcon,
  BoltIcon,
} from '@heroicons/react/24/outline';
import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuthStore, waitForAuthHydration } from '../../store/authStore';
import { useTaskStore } from '../../store/taskStore';
import { useInboxStore } from '../../store/inboxStore';
import { useInboxSSE } from '../../hooks/useInboxSSE';
import { AuthModal } from '../../components/Auth/AuthModal';
import { BottomNav } from '../../components/BottomNav';
// Navigation item type
interface NavItem {
  name: string;
  href: string;
  icon: typeof RectangleStackIcon;
  showBadge?: boolean;
}

// Core navigation: Inbox + Tasks + Settings
const coreNavigation: NavItem[] = [
  { name: 'INBOX', href: '/inbox', icon: InboxIcon, showBadge: true },
  { name: 'TASKS', href: '/tasks', icon: RectangleStackIcon },
  { name: 'AUTOMATIONS', href: '/automations', icon: ArrowPathIcon },
  { name: 'TRIGGERS', href: '/settings/triggers', icon: BoltIcon },
  { name: 'SETTINGS', href: '/settings', icon: CogIcon },
];

/**
 * Task-focused layout for authenticated app experience.
 * Futuristic sci-fi aesthetic with Tentackl design tokens.
 */
export default function DelegationLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const { user, isAuthenticated, logout, showAuthModal } = useAuthStore();
  const { pendingCheckpoints, loadPendingCheckpoints } = useTaskStore();
  const { unreadCount, loadUnreadCount } = useInboxStore();

  // Wait for both client mount AND Zustand hydration from localStorage
  // before making any auth decisions. Without this, the redirect fires
  // before the persisted token is restored, kicking logged-in users out.
  useEffect(() => {
    let cancelled = false;
    waitForAuthHydration().then(() => {
      if (!cancelled) setIsMounted(true);
    });
    return () => { cancelled = true; };
  }, []);

  // Redirect to login if not authenticated (only after hydration is complete)
  useEffect(() => {
    if (isMounted && !isAuthenticated) {
      const returnTo = pathname !== '/inbox' ? `?returnTo=${encodeURIComponent(pathname)}` : '';
      router.push(`/auth/login${returnTo}`);
    }
  }, [isMounted, isAuthenticated, router, pathname]);

  // Fetch pending checkpoints and unread inbox count on mount
  useEffect(() => {
    if (isAuthenticated) {
      loadPendingCheckpoints();
      loadUnreadCount();
    }
  }, [isAuthenticated, loadPendingCheckpoints, loadUnreadCount]);

  // Connect inbox SSE at layout level for real-time badge updates + thread refresh
  useInboxSSE({
    onNewMessage: (item) => {
      loadUnreadCount();
      // If user is viewing this conversation, trigger a thread refresh
      const state = useInboxStore.getState();
      if (item?.conversation_id && item.conversation_id === state.activeThreadId) {
        state.bumpThreadRefresh();
      }
    },
  }, isAuthenticated);

  const pendingCount = pendingCheckpoints.length;

  // Build navigation — core items + decisions badge when pending
  const navigation = useMemo(() => {
    const navItems: NavItem[] = [...coreNavigation];

    // Add Decisions between Tasks and Settings when there are pending items
    if (pendingCount > 0) {
      navItems.splice(1, 0, { name: 'DECISIONS', href: '/decisions', icon: InboxIcon, showBadge: true });
    }

    return navItems;
  }, [pendingCount]);

  // Show nothing while checking auth or redirecting
  if (!isMounted || !isAuthenticated) {
    return (
      <div className="h-[100dvh] flex items-center justify-center bg-[var(--background)]">
        <div className="animate-pulse text-[var(--muted-foreground)] font-mono text-sm">
          Loading...
        </div>
      </div>
    );
  }

  return (
    <div className="h-[100dvh] flex overflow-hidden bg-[var(--background)]">
      {/* Subtle grid pattern overlay */}
      <div className="fixed inset-0 grid-pattern opacity-30 pointer-events-none dark:opacity-30" />

      {/* Mobile sidebar backdrop */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-56 transform
          bg-[var(--card)] backdrop-blur-md
          border-r border-[var(--border)]
          transition-transform duration-300 ease-out lg:translate-x-0 lg:static lg:z-auto
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center justify-between h-16 px-4 border-b border-[var(--border)]">
            <Link href="/tasks" className="flex items-center gap-2 group">
              <img src="/icon-192.png" alt="" className="h-5 w-5" />
              <span className="font-mono text-base font-bold tracking-[0.15em] text-[var(--foreground)] group-hover:text-[var(--accent)] transition-colors">
                AIOS
              </span>
            </Link>
            <button
              onClick={() => setSidebarOpen(false)}
              className="lg:hidden p-2.5 rounded-md hover:bg-[var(--muted)] transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center"
            >
              <XMarkIcon className="w-5 h-5 text-[var(--muted-foreground)]" />
            </button>
          </div>

          {/* Create Task */}
          <div className="px-3 pt-5 pb-2">
            <button
              onClick={() => {
                setSidebarOpen(false);
                router.push('/inbox/new');
              }}
              className={[
                'flex items-center gap-2 w-full px-3 py-2.5 rounded-lg',
                'text-xs font-mono tracking-wider',
                'bg-[var(--accent)] text-[var(--accent-foreground)]',
                'hover:opacity-90 transition-opacity',
              ].join(' ')}
            >
              <PlusIcon className="w-4 h-4" />
              NEW CHAT
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-3 pb-6 space-y-1.5 overflow-y-auto">
            {navigation.map((item) => {
              // Check if this nav item is active
              // Special handling: /settings/triggers should only highlight TRIGGERS, not SETTINGS
              const isActive = pathname === item.href ||
                (item.href === '/tasks' && pathname.startsWith('/tasks')) ||
                (item.href === '/settings/triggers' && pathname.startsWith('/settings/triggers')) ||
                (item.href === '/settings' && pathname.startsWith('/settings') && !pathname.startsWith('/settings/triggers')) ||
                (item.href !== '/tasks' && item.href !== '/settings' && item.href !== '/settings/triggers' && pathname.startsWith(item.href));

              return (
                <Link
                  key={item.name}
                  href={item.href}
                  onClick={() => setSidebarOpen(false)}
                  className={`
                    flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-mono tracking-wider
                    transition-all duration-200
                    ${isActive
                      ? 'bg-[var(--accent)]/15 text-[var(--accent)] border border-[var(--accent)]/30'
                      : 'text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)] border border-transparent'
                    }
                  `}
                >
                  <span className="flex items-center gap-3">
                    <item.icon className="w-4 h-4" />
                    {item.name}
                  </span>
                  {item.showBadge && item.name === 'INBOX' && unreadCount > 0 && (
                    <span className="flex items-center justify-center min-w-[20px] h-5 px-1.5 text-[10px] font-bold rounded-full bg-[var(--accent)] text-[var(--accent-foreground)]">
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                  )}
                  {item.showBadge && item.name === 'DECISIONS' && pendingCount > 0 && (
                    <span className="flex items-center justify-center min-w-[20px] h-5 px-1.5 text-[10px] font-bold rounded-full bg-[var(--destructive)] text-white">
                      {pendingCount > 9 ? '9+' : pendingCount}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>

          {/* User section */}
          <div className="border-t border-[var(--border)] p-3">
            {isAuthenticated && user ? (
              <Menu as="div" className="relative">
                <MenuButton className="flex items-center w-full gap-3 px-3 py-2.5 rounded-lg text-sm hover:bg-[var(--muted)] transition-colors">
                  <div className="w-8 h-8 rounded-full bg-[var(--muted)] border border-[var(--border)] flex items-center justify-center">
                    <UserCircleIcon className="w-5 h-5 text-[var(--muted-foreground)]" />
                  </div>
                  <div className="flex-1 text-left min-w-0">
                    {(user.first_name || user.last_name) && (
                      <p className="font-mono text-xs text-[var(--foreground)] truncate">
                        {[user.first_name, user.last_name].filter(Boolean).join(' ')}
                      </p>
                    )}
                    <p className="font-mono text-[10px] text-[var(--muted-foreground)] truncate">
                      {user.email}
                    </p>
                  </div>
                </MenuButton>
                <MenuItems className="absolute bottom-full left-0 right-0 mb-1 py-1 bg-[var(--card)] border border-[var(--border)] rounded-lg shadow-lg z-10">
                  <MenuItem>
                    {({ focus }) => (
                      <Link
                        href="/settings/account"
                        className={`
                          flex items-center gap-2 w-full px-3 py-2 text-xs font-mono tracking-wider text-left
                          ${focus ? 'bg-[var(--muted)]' : ''}
                          text-[var(--foreground)]
                        `}
                      >
                        <CogIcon className="w-4 h-4" />
                        ACCOUNT SETTINGS
                      </Link>
                    )}
                  </MenuItem>
                  <MenuItem>
                    {({ focus }) => (
                      <button
                        onClick={logout}
                        className={`
                          flex items-center gap-2 w-full px-3 py-2 text-xs font-mono tracking-wider text-left
                          ${focus ? 'bg-[var(--muted)]' : ''}
                          text-[var(--destructive)]
                        `}
                      >
                        <ArrowRightOnRectangleIcon className="w-4 h-4" />
                        SIGN OUT
                      </button>
                    )}
                  </MenuItem>
                </MenuItems>
              </Menu>
            ) : (
              <div className="px-3 py-2 text-xs font-mono tracking-wider text-[var(--muted-foreground)]">
                NOT SIGNED IN
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 relative pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)]">
        {/* Mobile header */}
        <header className="lg:hidden flex items-center h-14 px-4 border-b border-[var(--border)] bg-[var(--card)] backdrop-blur-md">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2.5 -ml-2 rounded-md hover:bg-[var(--muted)] transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center"
          >
            <Bars3Icon className="w-5 h-5 text-[var(--foreground)]" />
          </button>
          <img src="/icon-192.png" alt="" className="ml-3 h-5 w-5" />
          <span className="ml-1.5 font-mono text-sm font-bold tracking-[0.15em] text-[var(--foreground)]">
            AIOS
          </span>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => router.push('/inbox/new')}
              className={[
                'inline-flex items-center justify-center w-10 h-10 rounded-md min-w-[44px] min-h-[44px]',
                'bg-[var(--accent)] text-[var(--accent-foreground)]',
                'hover:opacity-90 transition-opacity',
              ].join(' ')}
              title="New chat"
            >
              <PlusIcon className="w-4 h-4" />
            </button>
            {pendingCount > 0 && (
              <Link
                href="/decisions"
                className="flex items-center gap-1.5 px-2.5 py-2 rounded-full bg-[var(--destructive)] text-white text-xs font-mono font-bold min-h-[44px]"
              >
                <InboxIcon className="w-3.5 h-3.5" />
                {pendingCount}
              </Link>
            )}
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto overflow-x-hidden pb-20 lg:pb-0">
          {children}
        </main>
      </div>

      {/* Bottom navigation (mobile only) */}
      <BottomNav />

      {/* Auth Modal */}
      {showAuthModal && <AuthModal />}
    </div>
  );
}
