'use client';

import React from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';

interface ArticleCardProps {
  title: string;
  hook: string;
  slug: string;
  index: number;
  badge?: string;
  compact?: boolean;
}

/**
 * Card component for extended brain article listings
 * Displays article title, hook, and links to full article
 */
export function ArticleCard({ title, hook, slug, index, badge, compact = false }: ArticleCardProps) {
  if (compact) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.4, delay: index * 0.05 }}
      >
        <Link
          href={`/extended-brain/${slug}`}
          className="group flex items-center justify-between p-4 border border-[oklch(0.18_0.02_260)] bg-[oklch(0.08_0.02_260/0.5)] rounded-lg hover:border-[oklch(0.65_0.25_180/0.3)] transition-all duration-300"
        >
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-[oklch(0.80_0.01_90)] group-hover:text-[oklch(0.65_0.25_180)] transition-colors truncate">
              {title}
            </h3>
            <p className="text-sm text-[oklch(0.45_0.01_260)] mt-1 truncate">
              {hook}
            </p>
          </div>
          <span className="ml-4 text-[oklch(0.45_0.01_260)] group-hover:text-[oklch(0.65_0.25_180)] group-hover:translate-x-1 transition-all">
            →
          </span>
        </Link>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.6, delay: index * 0.1 }}
    >
      <Link
        href={`/extended-brain/${slug}`}
        className="group block p-8 border border-[oklch(0.22_0.03_260)] bg-[oklch(0.1_0.02_260/0.5)] rounded-lg hover:border-[oklch(0.65_0.25_180/0.5)] hover:shadow-[0_0_30px_oklch(0.65_0.25_180/0.1)] transition-all duration-300"
      >
        {/* Article number and badge */}
        <div className="flex items-center gap-3 mb-4">
          <span className="font-mono text-xs tracking-wider text-[oklch(0.65_0.25_180)]">
            ARTICLE {String(index + 1).padStart(2, '0')}
          </span>
          {badge && (
            <span className="px-2 py-0.5 text-xs font-mono tracking-wider bg-[oklch(0.65_0.25_180/0.15)] text-[oklch(0.65_0.25_180)] rounded">
              {badge.toUpperCase()}
            </span>
          )}
        </div>

        {/* Title */}
        <h3 className="text-xl md:text-2xl font-bold text-[oklch(0.95_0.01_90)] mb-4 group-hover:text-[oklch(0.65_0.25_180)] transition-colors">
          {title}
        </h3>

        {/* Hook */}
        <p className="text-[oklch(0.58_0.01_260)] leading-relaxed mb-6">
          {hook}
        </p>

        {/* Read more */}
        <span className="inline-flex items-center font-mono text-xs tracking-wider text-[oklch(0.65_0.25_180)] group-hover:text-[oklch(0.95_0.01_90)] transition-colors">
          READ ARTICLE
          <span className="ml-2 group-hover:translate-x-1 transition-transform">
            →
          </span>
        </span>
      </Link>
    </motion.div>
  );
}
