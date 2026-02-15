'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { SoftCTA } from './SoftCTA';

interface ArticleLayoutProps {
  title: string;
  hook: string;
  children: React.ReactNode;
  ctaText?: string;
  defaultLightMode?: boolean;
}

/**
 * Layout wrapper for extended brain articles
 * Provides consistent styling, back navigation, soft CTA, and reading mode toggle
 * Defaults to light mode for better readability
 */
export function ArticleLayout({
  title,
  hook,
  children,
  ctaText = 'See this in action',
  defaultLightMode = true,
}: ArticleLayoutProps) {
  const [isLightMode, setIsLightMode] = useState(defaultLightMode);

  return (
    <div className={`min-h-screen transition-colors duration-300 ${isLightMode ? 'extended-brain-light' : ''}`}>
      {/* Hero Section */}
      <section className="relative py-24 md:py-32 overflow-hidden">
        {/* Background Effects - Dark Mode */}
        <div className={`absolute inset-0 transition-colors duration-300 ${
          isLightMode
            ? 'bg-gradient-to-b from-[oklch(0.97_0.01_90)] via-[oklch(0.98_0.005_90)] to-[oklch(0.97_0.01_90)]'
            : 'bg-gradient-to-b from-[oklch(0.08_0.02_260)] via-[oklch(0.06_0.03_260)] to-[oklch(0.08_0.02_260)]'
        }`} />
        <div className={`absolute inset-0 grid-pattern ${isLightMode ? 'opacity-10' : 'opacity-20'}`} />

        {/* Subtle glow */}
        <div className={`absolute top-1/3 left-1/4 w-96 h-96 rounded-full blur-[120px] transition-colors duration-300 ${
          isLightMode ? 'bg-[oklch(0.65_0.15_180/0.1)]' : 'bg-[oklch(0.65_0.25_180/0.05)]'
        }`} />

        {/* Content */}
        <div className="relative z-10 max-w-3xl mx-auto px-4">
          {/* Back link and Reading Mode Toggle */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="flex items-center justify-between mb-8"
          >
            <Link
              href="/extended-brain"
              className={`inline-flex items-center font-mono text-xs tracking-wider transition-colors ${
                isLightMode
                  ? 'text-[oklch(0.45_0.01_260)] hover:text-[oklch(0.35_0.25_180)]'
                  : 'text-[oklch(0.58_0.01_260)] hover:text-[oklch(0.65_0.25_180)]'
              }`}
            >
              <span className="mr-2">←</span>
              EXTENDED BRAIN
            </Link>

            {/* Reading Mode Toggle */}
            <button
              onClick={() => setIsLightMode(!isLightMode)}
              className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full font-mono text-xs tracking-wider transition-all ${
                isLightMode
                  ? 'bg-[oklch(0.15_0.02_260)] text-[oklch(0.95_0.01_90)] hover:bg-[oklch(0.25_0.02_260)]'
                  : 'bg-[oklch(0.95_0.01_90)] text-[oklch(0.15_0.02_260)] hover:bg-[oklch(0.85_0.01_90)]'
              }`}
              aria-label={isLightMode ? 'Switch to dark mode' : 'Switch to light mode'}
            >
              {isLightMode ? (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                  </svg>
                  DARK
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                  </svg>
                  LIGHT
                </>
              )}
            </button>
          </motion.div>

          {/* Title */}
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className={`text-3xl md:text-5xl font-bold mb-6 leading-tight transition-colors duration-300 ${
              isLightMode ? 'text-[oklch(0.15_0.02_260)]' : 'text-[oklch(0.95_0.01_90)]'
            }`}
          >
            {title}
          </motion.h1>

          {/* Hook */}
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className={`text-xl leading-relaxed transition-colors duration-300 ${
              isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'
            }`}
          >
            {hook}
          </motion.p>
        </div>
      </section>

      {/* Article Content */}
      <section className={`py-16 px-4 transition-colors duration-300 ${
        isLightMode ? 'bg-[oklch(0.98_0.005_90)]' : ''
      }`}>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="max-w-3xl mx-auto"
        >
          <ExtendedBrainThemeContext.Provider value={{ isLightMode }}>
            <div className={`prose-tentackl ${isLightMode ? 'prose-light' : ''}`}>{children}</div>
          </ExtendedBrainThemeContext.Provider>

          {/* Signature */}
          <div className="mt-16 text-right">
            <span className={`text-sm tracking-wider transition-colors duration-300 ${
              isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'
            }`}>
              — JV
            </span>
          </div>
        </motion.div>
      </section>

      {/* Soft CTA */}
      <SoftCTA text={ctaText} isLightMode={isLightMode} />

      {/* Back to extended brain */}
      <section className={`py-16 px-4 border-t transition-colors duration-300 ${
        isLightMode
          ? 'border-[oklch(0.85_0.01_260)] bg-[oklch(0.97_0.01_90)]'
          : 'border-[oklch(0.22_0.03_260)]'
      }`}>
        <div className="max-w-3xl mx-auto text-center">
          <Link
            href="/extended-brain"
            className={`inline-flex items-center font-mono text-xs tracking-wider transition-colors ${
              isLightMode
                ? 'text-[oklch(0.45_0.01_260)] hover:text-[oklch(0.35_0.25_180)]'
                : 'text-[oklch(0.58_0.01_260)] hover:text-[oklch(0.65_0.25_180)]'
            }`}
          >
            <span className="mr-2">←</span>
            BACK TO EXTENDED BRAIN
          </Link>
        </div>
      </section>
    </div>
  );
}

// Context for child components to access theme (defaults to light mode)
export const ExtendedBrainThemeContext = React.createContext<{ isLightMode: boolean }>({ isLightMode: true });

export function useExtendedBrainTheme() {
  return React.useContext(ExtendedBrainThemeContext);
}
