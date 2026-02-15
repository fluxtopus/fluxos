'use client';

import React from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';

/**
 * Marketing landing page
 * Primary CTA: Try Playground (no signup required)
 */
export default function LandingPage() {
  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <section className="relative min-h-[80vh] flex items-center justify-center overflow-hidden">
        {/* Background Effects */}
        <div className="absolute inset-0 bg-gradient-to-b from-[oklch(0.08_0.02_260)] via-[oklch(0.06_0.03_260)] to-[oklch(0.08_0.02_260)]" />
        <div className="absolute inset-0 grid-pattern opacity-30" />

        {/* Glow effects */}
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-[oklch(0.65_0.25_180/0.1)] rounded-full blur-[120px]" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-[oklch(0.7_0.2_150/0.05)] rounded-full blur-[120px]" />

        {/* Content */}
        <div className="relative z-10 max-w-4xl mx-auto px-4 text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            {/* Tagline */}
            <div className="mb-6 inline-flex items-center gap-2 px-4 py-2 border border-[oklch(0.65_0.25_180/0.3)] rounded-full bg-[oklch(0.65_0.25_180/0.05)]">
              <div className="w-2 h-2 rounded-full bg-[oklch(0.78_0.22_150)] pulse-glow" />
              <span className="font-mono text-xs tracking-wider text-[oklch(0.65_0.25_180)]">
                MULTI-AGENT WORKFLOW ORCHESTRATION
              </span>
            </div>

            {/* Main Headline */}
            <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight mb-6">
              <span className="text-[oklch(0.95_0.01_90)]">Describe it.</span>
              <br />
              <span className="text-[oklch(0.65_0.25_180)]">Watch it build.</span>
              <br />
              <span className="text-[oklch(0.78_0.22_150)]">See it run.</span>
            </h1>

            {/* Subheadline */}
            <p className="text-lg md:text-xl text-[oklch(0.58_0.01_260)] max-w-2xl mx-auto mb-10">
              Turn natural language into powerful multi-agent workflows.
              AI plans and executes complex tasks while you watch in real-time.
            </p>

            {/* CTAs */}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link
                href="/playground"
                className="group relative px-8 py-4 font-mono text-sm tracking-wider border-2 border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180)] hover:text-[oklch(0.08_0.02_260)] transition-all duration-300 shadow-[0_0_20px_oklch(0.65_0.25_180/0.3)] hover:shadow-[0_0_30px_oklch(0.65_0.25_180/0.5)]"
              >
                TRY PLAYGROUND
                <span className="ml-2 group-hover:translate-x-1 inline-block transition-transform">
                  →
                </span>
              </Link>

              <Link
                href="/auth/register"
                className="px-8 py-4 font-mono text-sm tracking-wider border border-[oklch(0.3_0.02_260)] text-[oklch(0.58_0.01_260)] hover:border-[oklch(0.65_0.25_180/0.5)] hover:text-[oklch(0.95_0.01_90)] transition-all duration-300"
              >
                SIGN UP FREE
              </Link>
            </div>

            {/* Trust badge */}
            <p className="mt-8 font-mono text-xs text-[oklch(0.4_0.01_260)]">
              No credit card required • Try without signing up
            </p>
          </motion.div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-24 px-4">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="text-center mb-16"
          >
            <h2 className="text-3xl md:text-4xl font-bold text-[oklch(0.95_0.01_90)] mb-4">
              How It Works
            </h2>
            <p className="text-[oklch(0.58_0.01_260)] max-w-2xl mx-auto">
              From idea to execution in seconds
            </p>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-8">
            {/* Step 1 */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.1 }}
              className="p-6 border border-[oklch(0.22_0.03_260)] bg-[oklch(0.1_0.02_260/0.5)] rounded-lg"
            >
              <div className="w-12 h-12 mb-4 flex items-center justify-center border border-[oklch(0.65_0.25_180)] rounded-lg text-[oklch(0.65_0.25_180)]">
                <span className="font-mono text-xl">1</span>
              </div>
              <h3 className="text-xl font-bold text-[oklch(0.95_0.01_90)] mb-2">
                Describe Your Workflow
              </h3>
              <p className="text-[oklch(0.58_0.01_260)]">
                Tell the AI what you want to accomplish in plain language. No coding required.
              </p>
            </motion.div>

            {/* Step 2 */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="p-6 border border-[oklch(0.22_0.03_260)] bg-[oklch(0.1_0.02_260/0.5)] rounded-lg"
            >
              <div className="w-12 h-12 mb-4 flex items-center justify-center border border-[oklch(0.65_0.25_180)] rounded-lg text-[oklch(0.65_0.25_180)]">
                <span className="font-mono text-xl">2</span>
              </div>
              <h3 className="text-xl font-bold text-[oklch(0.95_0.01_90)] mb-2">
                Watch It Build
              </h3>
              <p className="text-[oklch(0.58_0.01_260)]">
                AI generates a complete workflow with multiple agents, each handling a specific task.
              </p>
            </motion.div>

            {/* Step 3 */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="p-6 border border-[oklch(0.22_0.03_260)] bg-[oklch(0.1_0.02_260/0.5)] rounded-lg"
            >
              <div className="w-12 h-12 mb-4 flex items-center justify-center border border-[oklch(0.78_0.22_150)] rounded-lg text-[oklch(0.78_0.22_150)]">
                <span className="font-mono text-xl">3</span>
              </div>
              <h3 className="text-xl font-bold text-[oklch(0.95_0.01_90)] mb-2">
                See It Run
              </h3>
              <p className="text-[oklch(0.58_0.01_260)]">
                Execute and monitor your workflow in real-time with full visibility into each step.
              </p>
            </motion.div>
          </div>
        </div>
      </section>

      {/* Use Cases Section */}
      <section className="py-24 px-4 bg-[oklch(0.06_0.02_260)]">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="text-center mb-16"
          >
            <h2 className="text-3xl md:text-4xl font-bold text-[oklch(0.95_0.01_90)] mb-4">
              What You Can Build
            </h2>
            <p className="text-[oklch(0.58_0.01_260)] max-w-2xl mx-auto">
              Automate complex tasks that would take hours manually
            </p>
          </motion.div>

          <div className="grid md:grid-cols-2 gap-6">
            {[
              {
                title: 'Data Processing Pipelines',
                description: 'Fetch, transform, and analyze data from multiple APIs',
              },
              {
                title: 'Research & Analysis',
                description: 'Gather information, summarize findings, generate reports',
              },
              {
                title: 'Content Generation',
                description: 'Create and optimize content across multiple channels',
              },
              {
                title: 'Webhook Integrations',
                description: 'Respond to events with intelligent multi-step automation',
              },
            ].map((item, index) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.6, delay: index * 0.1 }}
                className="p-6 border border-[oklch(0.22_0.03_260)] rounded-lg hover:border-[oklch(0.65_0.25_180/0.5)] transition-colors"
              >
                <h3 className="text-lg font-bold text-[oklch(0.95_0.01_90)] mb-2">
                  {item.title}
                </h3>
                <p className="text-[oklch(0.58_0.01_260)]">{item.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-24 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <h2 className="text-3xl md:text-4xl font-bold text-[oklch(0.95_0.01_90)] mb-6">
              Ready to automate?
            </h2>
            <p className="text-[oklch(0.58_0.01_260)] mb-8 max-w-xl mx-auto">
              Start building workflows in seconds. No signup required to try.
            </p>
            <Link
              href="/playground"
              className="inline-flex items-center px-8 py-4 font-mono text-sm tracking-wider border-2 border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180)] hover:text-[oklch(0.08_0.02_260)] transition-all duration-300 shadow-[0_0_20px_oklch(0.65_0.25_180/0.3)] hover:shadow-[0_0_30px_oklch(0.65_0.25_180/0.5)]"
            >
              OPEN PLAYGROUND →
            </Link>
          </motion.div>
        </div>
      </section>
    </div>
  );
}
