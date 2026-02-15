'use client';

import React from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';

/**
 * Marketing layout - minimal navigation for landing page
 * No app navbar, just logo and auth links
 */
export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Minimal Marketing Header */}
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-[oklch(0.65_0.25_180/0.2)] bg-[oklch(0.08_0.02_260/0.9)] backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 md:px-6 py-4 flex items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-3 group">
            <img src="/icon-192.png" alt="" className="h-6 w-6" />
            <span className="font-mono text-lg md:text-xl font-bold tracking-[0.2em] text-[oklch(0.95_0.01_90)] group-hover:text-[oklch(0.65_0.25_180)] transition-colors">
              AIOS
            </span>
          </Link>

          {/* Auth Links */}
          <div className="flex items-center gap-3">
            <Link
              href="/auth/login"
              className="px-4 py-2 font-mono text-xs tracking-wider text-[oklch(0.65_0.25_180)] hover:text-[oklch(0.95_0.01_90)] transition-colors"
            >
              SIGN IN
            </Link>
            <Link
              href="/auth/register"
              className="px-4 py-2 font-mono text-xs tracking-wider border border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180/0.1)] transition-all"
            >
              SIGN UP
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 pt-16">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-[oklch(0.65_0.25_180/0.2)] bg-[oklch(0.06_0.02_260)]">
        <div className="max-w-7xl mx-auto px-4 md:px-6 py-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <span className="font-mono text-xs text-[oklch(0.58_0.01_260)] flex items-center gap-1.5">
              <img src="/icon-192.png" alt="" className="h-4 w-4" />
              AIOS - Multi-Agent Workflow Orchestration
            </span>
            <div className="flex items-center gap-6">
              <Link
                href="/extended-brain"
                className="font-mono text-xs text-[oklch(0.58_0.01_260)] hover:text-[oklch(0.65_0.25_180)] transition-colors"
              >
                EXTENDED BRAIN
              </Link>
              <Link
                href="/playground"
                className="font-mono text-xs text-[oklch(0.58_0.01_260)] hover:text-[oklch(0.65_0.25_180)] transition-colors"
              >
                PLAYGROUND
              </Link>
              <Link
                href="/specs/public"
                className="font-mono text-xs text-[oklch(0.58_0.01_260)] hover:text-[oklch(0.65_0.25_180)] transition-colors"
              >
                GALLERY
              </Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
