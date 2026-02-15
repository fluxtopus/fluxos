'use client';

import React from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';

interface SoftCTAProps {
  text?: string;
  href?: string;
  buttonText?: string;
  isLightMode?: boolean;
}

/**
 * Soft call-to-action component for extended brain articles
 * Gentle nudge to try the playground without being pushy
 */
export function SoftCTA({
  text = 'See this in action',
  href = '/playground',
  buttonText = 'TRY THE PLAYGROUND',
  isLightMode = false,
}: SoftCTAProps) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.6 }}
      className={`py-16 px-4 transition-colors duration-300 ${
        isLightMode ? 'bg-[oklch(0.95_0.01_90)]' : 'bg-[oklch(0.06_0.02_260)]'
      }`}
    >
      <div className="max-w-3xl mx-auto text-center">
        {/* Divider line */}
        <div className={`w-16 h-px mx-auto mb-8 transition-colors duration-300 ${
          isLightMode ? 'bg-[oklch(0.45_0.20_180/0.4)]' : 'bg-[oklch(0.65_0.25_180/0.3)]'
        }`} />

        {/* CTA text */}
        <p className={`text-lg mb-6 transition-colors duration-300 ${
          isLightMode ? 'text-[oklch(0.40_0.01_260)]' : 'text-[oklch(0.58_0.01_260)]'
        }`}>{text}</p>

        {/* Button */}
        <Link
          href={href}
          className={`group inline-flex items-center px-6 py-3 font-mono text-xs tracking-wider border transition-all duration-300 ${
            isLightMode
              ? 'border-[oklch(0.45_0.20_180/0.5)] text-[oklch(0.35_0.20_180)] hover:bg-[oklch(0.45_0.20_180/0.1)] hover:border-[oklch(0.35_0.20_180)]'
              : 'border-[oklch(0.65_0.25_180/0.5)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180/0.1)] hover:border-[oklch(0.65_0.25_180)]'
          }`}
        >
          {buttonText}
          <span className="ml-2 group-hover:translate-x-1 transition-transform">
            →
          </span>
        </Link>
      </div>
    </motion.section>
  );
}
