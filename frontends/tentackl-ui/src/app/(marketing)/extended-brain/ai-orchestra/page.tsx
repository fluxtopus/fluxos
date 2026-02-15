'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { ArticleLayout, useExtendedBrainTheme } from '@/components/ExtendedBrain';

/**
 * Article 1: Your AI Orchestra
 * The foundational mental model - read this first
 * Core transformation: "I need to learn automation tools" → "I already know how to delegate"
 */
export default function AIOrchestra() {
  return (
    <ArticleLayout
      title="Your AI Orchestra"
      hook="You don't need to learn automation. You already know how to delegate."
      ctaText="Describe what you need. Watch your orchestra perform."
    >
      {/* Section 1: The Composer Doesn't Play Every Instrument */}
      <ArticleSection delay={0}>
        <SectionTitle>The Composer Doesn't Play Every Instrument</SectionTitle>
        <Paragraph>
          When a composer creates a symphony, they don't learn to play every instrument.
          They don't personally bow each violin or strike each timpani. They describe the
          music they want — the tempo, the dynamics, the emotion — and the orchestra
          performs it.
        </Paragraph>
        <Paragraph>
          This is what working with AI should feel like.
        </Paragraph>
        <Paragraph>
          For too long, automation has meant programming. Writing rules. Handling
          exceptions. Becoming, in essence, a machine yourself — thinking in steps and
          conditions instead of outcomes and intentions.
        </Paragraph>
        <Paragraph>
          But you already know how to get work done through others. You do it every day.
          You tell a colleague "research our competitors' pricing" — you don't say "open
          Chrome, navigate to competitor-a.com, find the pricing page, copy the numbers
          into a spreadsheet..."
        </Paragraph>
        <Paragraph>
          That's not how delegation works. And it's not how AI should work either.
        </Paragraph>
      </ArticleSection>

      {/* Section 2: What Delegation Actually Looks Like */}
      <ArticleSection delay={0.1}>
        <SectionTitle>What Delegation Actually Looks Like</SectionTitle>
        <Paragraph>
          Here's the shift:
        </Paragraph>
        <ComparisonBlock
          oldWay="Search Google for X, open the first three results, extract the main points, format them as bullet points, check for accuracy, compile into a summary..."
          newWay="Research X and summarize the key findings."
        />
        <ComparisonBlock
          oldWay="Connect to the database, query orders from the last 30 days, filter by status, group by customer, calculate totals, generate a CSV, email it to..."
          newWay="Send me a monthly sales summary by customer."
        />
        <Paragraph>
          The difference isn't just shorter instructions. It's a fundamentally different
          relationship with the work. You're not engineering a solution. You're describing
          what you need.
        </Paragraph>
      </ArticleSection>

      {/* Section 3: Your First Performance */}
      <ArticleSection delay={0.2}>
        <SectionTitle>Your First Performance</SectionTitle>
        <Paragraph>
          The first time you describe a workflow in plain language and watch it build
          itself, something clicks.
        </Paragraph>
        <Paragraph>
          It's not that the technology is impressive (though it is). It's that you
          realize you've been thinking about this wrong. You don't need to become more
          technical. You need to become more clear.
        </Paragraph>
        <Paragraph>
          Clear about what you actually want.
        </Paragraph>
        <Paragraph>
          Clear about what outcome matters.
        </Paragraph>
        <Paragraph>
          Clear about what "done" looks like.
        </Paragraph>
        <Paragraph>
          These are skills you already have. You use them every time you delegate to a
          human. The only difference is now you're delegating to an AI orchestra — a
          team of specialized agents who coordinate without meetings and handoff work
          without email.
        </Paragraph>
        <Paragraph>
          And here's what makes it different from other automation: you can watch them
          work. Not because you have to — but because seeing builds understanding, and
          understanding builds trust. You describe what you want at a high level, then
          watch your orchestra figure out the details.
        </Paragraph>
      </ArticleSection>

      {/* Section 4: This Changes How You Think About Work */}
      <ArticleSection delay={0.3}>
        <SectionTitle>This Changes How You Think About Work</SectionTitle>
        <Paragraph>
          Once you see work this way, you can't unsee it.
        </Paragraph>
        <Paragraph>
          Every repetitive task becomes a potential delegation.
        </Paragraph>
        <Paragraph>
          Every "I wish someone could just..." becomes a workflow description.
        </Paragraph>
        <Paragraph>
          Every process that lives in your head becomes something your AI orchestra
          can perform.
        </Paragraph>
        <Paragraph>
          The question stops being "what can I automate?" and becomes "what do I want
          done?"
        </Paragraph>
        <Paragraph>
          That's a much better question. Because you always know what you want done.
          You just didn't know you could simply... say it.
        </Paragraph>
        <Paragraph>
          Now you can.
        </Paragraph>
        <ClosingLine>
          Describe the music. Watch your orchestra perform.
        </ClosingLine>
      </ArticleSection>
    </ArticleLayout>
  );
}

// Helper components for consistent article styling with light mode support

function ArticleSection({
  children,
  delay = 0,
}: {
  children: React.ReactNode;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.6, delay }}
      className="mb-12"
    >
      {children}
    </motion.div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <h2 className={`text-2xl md:text-3xl font-bold mb-6 transition-colors duration-300 ${
      isLightMode ? 'text-[oklch(0.15_0.02_260)]' : 'text-[oklch(0.95_0.01_90)]'
    }`}>
      {children}
    </h2>
  );
}

function Paragraph({ children }: { children: React.ReactNode }) {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <p className={`text-lg leading-relaxed mb-4 transition-colors duration-300 ${
      isLightMode ? 'text-[oklch(0.30_0.01_260)]' : 'text-[oklch(0.7_0.01_260)]'
    }`}>
      {children}
    </p>
  );
}

function ComparisonBlock({ oldWay, newWay }: { oldWay: string; newWay: string }) {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <div className={`my-8 p-6 rounded-lg transition-colors duration-300 ${
      isLightMode ? 'bg-[oklch(0.94_0.01_260)]' : 'bg-[oklch(0.12_0.02_260)]'
    }`}>
      <div className="mb-4">
        <span className={`font-mono text-xs tracking-wider ${
          isLightMode ? 'text-[oklch(0.50_0.01_260)]' : 'text-[oklch(0.50_0.01_260)]'
        }`}>OLD WAY (Programming):</span>
        <p className={`text-base mt-1 italic ${
          isLightMode ? 'text-[oklch(0.45_0.01_260)]' : 'text-[oklch(0.55_0.01_260)]'
        }`}>"{oldWay}"</p>
      </div>
      <div>
        <span className={`font-mono text-xs tracking-wider ${
          isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'
        }`}>NEW WAY (Delegation):</span>
        <p className={`text-base mt-1 font-medium ${
          isLightMode ? 'text-[oklch(0.25_0.02_260)]' : 'text-[oklch(0.85_0.01_90)]'
        }`}>"{newWay}"</p>
      </div>
    </div>
  );
}

function ClosingLine({ children }: { children: React.ReactNode }) {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <p className={`text-xl font-medium mt-8 transition-colors duration-300 ${
      isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'
    }`}>
      {children}
    </p>
  );
}
