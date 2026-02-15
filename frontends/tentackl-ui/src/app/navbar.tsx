'use client';

import React, { useEffect, useState, Fragment } from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu, Transition } from '@headlessui/react';
import { UserCircleIcon, ArrowRightOnRectangleIcon, Cog6ToothIcon } from '@heroicons/react/24/outline';
import { useWorkflowStore } from '../store/workflowStore';
import { useAuthStore } from '../store/authStore';
import { logoutUser } from '../services/auth';
import { AuthModal } from '../components/Auth/AuthModal';

// Feature flag: Set to true to show full navigation, false for playground-only mode
const SHOW_FULL_NAVIGATION = false;

export function Navbar() {
  const pathname = usePathname();
  const { error, clearError } = useWorkflowStore();
  const { isAuthenticated, user, isInitialized, openAuthModal } = useAuthStore();

  // Clear error when it changes
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => {
        clearError();
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [error, clearError]);

  const navItems = [
    { value: '/', label: 'FLUX' },
    { value: '/playground', label: 'PLAYGROUND' },
    { value: '/tasks', label: 'TASKS' },
    { value: '/workflows', label: 'RUNS' },
    { value: '/specs', label: 'SPECS' },
    { value: '/examples', label: 'EXAMPLES' },
    { value: '/agents', label: 'AGENTS' },
    { value: '/webhooks', label: 'WEBHOOKS' },
    { value: '/approvals', label: 'APPROVALS' },
  ];

  const handleLogout = () => {
    logoutUser();
  };

  return (
    <>
      {/* Top Navbar */}
      <nav className="relative border-b border-[oklch(0.65_0.25_180/0.3)] bg-[oklch(0.08_0.02_260/0.95)] backdrop-blur-md">
        {/* Scan line effect */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute inset-0 bg-gradient-to-b from-[oklch(0.65_0.25_180/0.05)] to-transparent h-px top-0" />
        </div>

        <div className="px-4 md:px-6 py-3 flex items-center justify-between relative">
          {/* Left: Logo + Tagline */}
          <div className="flex items-center gap-4 md:gap-6">
            <Link href="/playground" className="flex items-center gap-2 md:gap-3 group">
              <img src="/icon-192.png" alt="" className="h-5 w-5 md:h-6 md:w-6" />
              <span className="font-mono text-base md:text-lg font-bold tracking-[0.15em] md:tracking-[0.2em] text-[oklch(0.95_0.01_90)] group-hover:text-[oklch(0.65_0.25_180)] transition-colors">
                AIOS
              </span>
            </Link>

            {/* Tagline - hidden on mobile */}
            <div className="hidden sm:flex items-center gap-2">
              <div className="w-px h-4 bg-[oklch(0.3_0.02_260)]" />
              <span className="font-mono text-[10px] md:text-xs tracking-[0.2em] text-[oklch(0.65_0.25_180)] uppercase">
                SEE IT RUN
              </span>
            </div>

            {/* Navigation Tabs - only shown when SHOW_FULL_NAVIGATION is true */}
            {SHOW_FULL_NAVIGATION && (
              <div className="flex items-center gap-1 ml-8">
                {navItems.map((item) => {
                  const isActive = pathname === item.value ||
                    (item.value !== '/' && pathname?.startsWith(item.value));
                  return (
                    <Link
                      key={item.value}
                      href={item.value}
                      className={`px-3 py-1.5 font-mono text-xs tracking-wider transition-all duration-300 border ${
                        isActive
                          ? 'bg-[oklch(0.65_0.25_180/0.2)] border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] shadow-[0_0_10px_oklch(0.65_0.25_180/0.3)]'
                          : 'border-transparent text-[oklch(0.58_0.01_260)] hover:text-[oklch(0.95_0.01_90)] hover:border-[oklch(0.65_0.25_180/0.3)]'
                      }`}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right: Auth + Beta Badge + Status */}
          <div className="flex items-center gap-2 md:gap-4">
            {/* Auth State */}
            {isInitialized && (
              isAuthenticated && user ? (
                <Menu as="div" className="relative">
                  <Menu.Button className="flex items-center gap-2 px-3 py-1.5 border border-[oklch(0.22_0.03_260)] rounded bg-[oklch(0.12_0.02_260/0.5)] hover:border-[oklch(0.65_0.25_180/0.5)] transition-colors">
                    <UserCircleIcon className="w-4 h-4 text-[oklch(0.65_0.25_180)]" />
                    <span className="font-mono text-[10px] md:text-xs tracking-wider text-[oklch(0.95_0.01_90)] max-w-[100px] truncate hidden sm:block">
                      {user.email?.split('@')[0] ?? 'User'}
                    </span>
                  </Menu.Button>

                  <Transition
                    as={Fragment}
                    enter="transition ease-out duration-100"
                    enterFrom="transform opacity-0 scale-95"
                    enterTo="transform opacity-100 scale-100"
                    leave="transition ease-in duration-75"
                    leaveFrom="transform opacity-100 scale-100"
                    leaveTo="transform opacity-0 scale-95"
                  >
                    <Menu.Items className="absolute right-0 mt-2 w-48 origin-top-right border border-[oklch(0.22_0.03_260)] bg-[oklch(0.1_0.02_260)] rounded shadow-lg focus:outline-none z-50">
                      <div className="p-2">
                        <div className="px-3 py-2 border-b border-[oklch(0.22_0.03_260)] mb-2">
                          <p className="font-mono text-xs text-[oklch(0.95_0.01_90)] truncate">
                            {user.email ?? 'Unknown'}
                          </p>
                        </div>

                        <Menu.Item>
                          {({ active }) => (
                            <Link
                              href="/tasks"
                              className={`flex items-center gap-2 px-3 py-2 font-mono text-xs rounded ${
                                active
                                  ? 'bg-[oklch(0.65_0.25_180/0.1)] text-[oklch(0.65_0.25_180)]'
                                  : 'text-[oklch(0.58_0.01_260)]'
                              }`}
                            >
                              <Cog6ToothIcon className="w-4 h-4" />
                              MY TASKS
                            </Link>
                          )}
                        </Menu.Item>

                        <Menu.Item>
                          {({ active }) => (
                            <Link
                              href="/specs"
                              className={`flex items-center gap-2 px-3 py-2 font-mono text-xs rounded ${
                                active
                                  ? 'bg-[oklch(0.65_0.25_180/0.1)] text-[oklch(0.65_0.25_180)]'
                                  : 'text-[oklch(0.58_0.01_260)]'
                              }`}
                            >
                              <Cog6ToothIcon className="w-4 h-4" />
                              MY SPECS
                            </Link>
                          )}
                        </Menu.Item>

                        <Menu.Item>
                          {({ active }) => (
                            <button
                              onClick={handleLogout}
                              className={`w-full flex items-center gap-2 px-3 py-2 font-mono text-xs rounded ${
                                active
                                  ? 'bg-[oklch(0.577_0.245_27/0.1)] text-[oklch(0.577_0.245_27)]'
                                  : 'text-[oklch(0.58_0.01_260)]'
                              }`}
                            >
                              <ArrowRightOnRectangleIcon className="w-4 h-4" />
                              SIGN OUT
                            </button>
                          )}
                        </Menu.Item>
                      </div>
                    </Menu.Items>
                  </Transition>
                </Menu>
              ) : (
                <button
                  onClick={() => openAuthModal('login')}
                  className="px-3 py-1.5 font-mono text-[10px] md:text-xs tracking-wider text-[oklch(0.65_0.25_180)] hover:text-[oklch(0.95_0.01_90)] transition-colors"
                >
                  SIGN IN
                </button>
              )
            )}

            {/* Beta Badge */}
            <div className="px-1.5 md:px-2 py-0.5 rounded border border-[oklch(0.65_0.25_180/0.5)] bg-[oklch(0.65_0.25_180/0.1)]">
              <span className="font-mono text-[8px] md:text-[10px] tracking-wider text-[oklch(0.65_0.25_180)] uppercase">
                BETA
              </span>
            </div>

            {/* System Status */}
            <div className="flex items-center gap-1.5 md:gap-2 px-2 md:px-3 py-1 border border-[oklch(0.22_0.03_260)] rounded bg-[oklch(0.12_0.02_260/0.5)]">
              <div className="w-1.5 md:w-2 h-1.5 md:h-2 rounded-full bg-[oklch(0.78_0.22_150)] pulse-glow" />
              <span className="font-mono text-[8px] md:text-[10px] tracking-wider text-[oklch(0.78_0.22_150)] uppercase">
                ONLINE
              </span>
            </div>
          </div>
        </div>
      </nav>

      {/* Error Banner */}
      {error && (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          className="bg-[oklch(0.577_0.245_27/0.1)] border-b border-[oklch(0.577_0.245_27/0.5)] px-6 py-3 relative"
        >
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-[oklch(0.577_0.245_27)] pulse-glow" />
            <span className="font-mono text-sm text-[oklch(0.577_0.245_27)]">
              ERROR: {error}
            </span>
          </div>
        </motion.div>
      )}

      {/* Auth Modal */}
      <AuthModal />
    </>
  );
}
