'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { ArticleCard } from '@/components/ExtendedBrain';

interface ArticleMeta {
  slug: string;
  title: string;
  hook: string;
  badge?: string;
}

interface ExtendedBrainPageClientProps {
  coreArticles: ArticleMeta[];
  archiveArticles: ArticleMeta[];
}

/**
 * Client component for Extended Brain page
 * Handles interactive archive toggle while receiving data from server
 */
export function ExtendedBrainPageClient({
  coreArticles,
  archiveArticles,
}: ExtendedBrainPageClientProps) {
  const [showArchive, setShowArchive] = useState(false);

  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <section className="relative py-24 md:py-32 overflow-hidden">
        {/* Background Effects */}
        <div className="absolute inset-0 bg-gradient-to-b from-[oklch(0.08_0.02_260)] via-[oklch(0.06_0.03_260)] to-[oklch(0.08_0.02_260)]" />
        <div className="absolute inset-0 grid-pattern opacity-30" />

        {/* Glow effects */}
        <div className="absolute top-1/4 left-1/3 w-96 h-96 bg-[oklch(0.65_0.25_180/0.08)] rounded-full blur-[120px]" />
        <div className="absolute bottom-1/4 right-1/3 w-64 h-64 bg-[oklch(0.7_0.2_150/0.05)] rounded-full blur-[100px]" />

        {/* Content */}
        <div className="relative z-10 max-w-4xl mx-auto px-4 text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            {/* Label */}
            <div className="mb-6 inline-flex items-center gap-2 px-4 py-2 border border-[oklch(0.65_0.25_180/0.3)] rounded-full bg-[oklch(0.65_0.25_180/0.05)]">
              <span className="font-mono text-xs tracking-wider text-[oklch(0.65_0.25_180)]">
                OUR EXTENDED BRAIN
              </span>
            </div>

            {/* Headline */}
            <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight mb-6 text-[oklch(0.95_0.01_90)]">
              Describe it.{' '}
              <span className="text-[oklch(0.65_0.25_180)]">Watch it work.</span>
            </h1>

            {/* Subheadline */}
            <p className="text-lg md:text-xl text-[oklch(0.58_0.01_260)] max-w-2xl mx-auto">
              A new way to think about automation — not as programming,
              but as delegation to your AI orchestra.
            </p>
          </motion.div>
        </div>
      </section>

      {/* Core Articles */}
      <section className="py-16 md:py-24 px-4">
        <div className="max-w-4xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="mb-8"
          >
            <h2 className="font-mono text-xs tracking-wider text-[oklch(0.65_0.25_180)] mb-2">
              THE CORE IDEAS
            </h2>
            <p className="text-[oklch(0.50_0.01_260)]">
              Read these in order for the complete mental model shift.
            </p>
          </motion.div>

          <div className="space-y-6">
            {coreArticles.map((article, index) => (
              <ArticleCard
                key={article.slug}
                title={article.title}
                hook={article.hook}
                slug={article.slug}
                index={index}
                badge={article.badge}
              />
            ))}
          </div>
        </div>
      </section>

      {/* Archive Section */}
      {archiveArticles.length > 0 && (
        <section className="py-16 px-4 border-t border-[oklch(0.22_0.03_260)]">
          <div className="max-w-4xl mx-auto">
            <button
              onClick={() => setShowArchive(!showArchive)}
              className="w-full flex items-center justify-between py-4 group"
            >
              <div>
                <h2 className="font-mono text-xs tracking-wider text-[oklch(0.45_0.01_260)] group-hover:text-[oklch(0.65_0.25_180)] transition-colors">
                  EARLIER THINKING
                </h2>
                <p className="text-sm text-[oklch(0.40_0.01_260)] mt-1">
                  Previous articles exploring similar ideas
                </p>
              </div>
              <span className={`text-[oklch(0.45_0.01_260)] transition-transform duration-300 ${showArchive ? 'rotate-180' : ''}`}>
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </span>
            </button>

            <motion.div
              initial={false}
              animate={{
                height: showArchive ? 'auto' : 0,
                opacity: showArchive ? 1 : 0,
              }}
              transition={{ duration: 0.3 }}
              className="overflow-hidden"
            >
              <div className="space-y-4 pt-6">
                {archiveArticles.map((article, index) => (
                  <ArticleCard
                    key={article.slug}
                    title={article.title}
                    hook={article.hook}
                    slug={article.slug}
                    index={index}
                    compact
                  />
                ))}
              </div>
            </motion.div>
          </div>
        </section>
      )}
    </div>
  );
}
