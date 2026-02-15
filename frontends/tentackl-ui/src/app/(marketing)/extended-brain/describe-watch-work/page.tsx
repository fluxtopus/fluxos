'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { ArticleLayout, useExtendedBrainTheme } from '@/components/ExtendedBrain';

/**
 * Article 2: Describe It. Watch It Work.
 * The experience of using Tentackl — why visibility matters emotionally
 * Core transformation: "I hope this works" → "I know this works"
 */
export default function DescribeWatchWork() {
  return (
    <ArticleLayout
      title="Describe It. Watch It Work."
      hook="The moment you watch your first workflow execute, something shifts. Not in the software — in you."
      ctaText="Watch a workflow execute in real-time."
    >
      {/* Section 1: The Shift */}
      <ArticleSection delay={0}>
        <SectionTitle>The Shift</SectionTitle>
        <Paragraph>
          There's a difference between believing something works and knowing it works.
        </Paragraph>
        <Paragraph>
          When automation happens in a black box — when you push a button and results
          appear — you're always believing. Hoping. Trusting that whatever happened
          in there was correct.
        </Paragraph>
        <Paragraph>
          When you can watch each step execute, see each agent receive its task,
          observe data flow from one stage to the next — that's knowing.
        </Paragraph>
        <Paragraph>
          This isn't just a feature. It's the foundation of everything.
        </Paragraph>
      </ArticleSection>

      {/* Section 2: Knowing vs. Hoping */}
      <ArticleSection delay={0.1}>
        <SectionTitle>Knowing vs. Hoping</SectionTitle>
        <Paragraph>
          Think about the last time you delegated something important to a black box
          system.
        </Paragraph>
        <Paragraph>
          Maybe it was an email automation that you set up months ago. Is it still
          working? Are the emails going out? Are they saying the right thing? You
          check occasionally, hoping nothing broke. But you don't really know.
        </Paragraph>
        <Paragraph>
          Now imagine you could watch. Not obsessively, not constantly — just when
          you want to. You could see your AI team working: this agent researching,
          that one analyzing, another one writing the output. You'd see the handoffs
          happen. You'd notice if something looked wrong before it became a problem.
        </Paragraph>
        <Paragraph>
          That's not oversight. That's understanding.
        </Paragraph>
        <Paragraph>
          And understanding is what lets you trust.
        </Paragraph>
      </ArticleSection>

      {/* Section 3: The Control You Actually Want */}
      <ArticleSection delay={0.2}>
        <SectionTitle>The Control You Actually Want</SectionTitle>
        <Paragraph>
          Here's what nobody tells you about automation: the goal isn't to remove
          yourself from the process entirely. It's to remove yourself from the
          tedious parts while staying connected to what matters.
        </Paragraph>
        <Paragraph>
          You don't want to check every email before it sends. But you might want to
          see how your AI team handles an unusual request. You don't want to approve
          every step. But you want to know the steps are happening.
        </Paragraph>
        <Paragraph>
          This is the control that matters — not micromanagement, but awareness.
          The ability to glance at your AI orchestra performing and know, at a glance,
          that the music sounds right.
        </Paragraph>
        <Paragraph>
          When something's off, you'll notice. Not because you're watching every note,
          but because you've developed intuition for how it should look.
        </Paragraph>
      </ArticleSection>

      {/* Section 4: Building Confidence Through Visibility */}
      <ArticleSection delay={0.3}>
        <SectionTitle>Building Confidence Through Visibility</SectionTitle>
        <Paragraph>
          Here's what happens when you can see your workflows execute:
        </Paragraph>
        <Paragraph>
          First, you understand. You watch a few runs and start to grasp what's
          actually happening. The mystery dissolves. This agent does this. That agent
          does that. Data flows like this.
        </Paragraph>
        <Paragraph>
          Then, you trust. Not blind trust — informed trust. You've seen it work.
          You know what "normal" looks like. You can spot anomalies.
        </Paragraph>
        <Paragraph>
          Finally, you delegate more. Because now you know what your AI orchestra
          can handle. You've watched them perform. You've seen them succeed. So you
          give them more complex pieces to play.
        </Paragraph>
        <CycleBlock />
        <Paragraph>
          Each turn of the cycle, you become more confident. Each turn, you delegate
          more. Each turn, you free yourself for work that actually needs you.
        </Paragraph>
      </ArticleSection>

      {/* Section 5: The Moment It Clicks */}
      <ArticleSection delay={0.4}>
        <SectionTitle>The Moment It Clicks</SectionTitle>
        <Paragraph>
          There's a moment, usually a few workflows in, where it clicks.
        </Paragraph>
        <Paragraph>
          You're watching your AI team handle something that used to take you an hour.
          You see each step complete. You see the output appear. And you realize:
          this is actually working. Not "probably working." Working.
        </Paragraph>
        <Paragraph>
          In that moment, your relationship with automation changes forever.
        </Paragraph>
        <Paragraph>
          You stop hoping and start knowing. You stop checking obsessively and start
          glancing confidently. You stop wondering if it's working and start thinking
          about what else your orchestra can play.
        </Paragraph>
        <Paragraph>
          That's the moment I built this for.
        </Paragraph>
        <ClosingLine>
          Describe it. Watch it work.
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

function CycleBlock() {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <div className={`my-8 p-6 rounded-lg text-center transition-colors duration-300 ${
      isLightMode ? 'bg-[oklch(0.94_0.01_260)]' : 'bg-[oklch(0.12_0.02_260)]'
    }`}>
      <p className={`text-lg font-mono tracking-wide ${
        isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'
      }`}>
        see → understand → trust → delegate → see
      </p>
      <p className={`text-sm mt-2 ${
        isLightMode ? 'text-[oklch(0.45_0.01_260)]' : 'text-[oklch(0.55_0.01_260)]'
      }`}>
        The virtuous cycle of visibility
      </p>
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
