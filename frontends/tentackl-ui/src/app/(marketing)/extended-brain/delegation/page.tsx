'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { ArticleLayout, useExtendedBrainTheme } from '@/components/ExtendedBrain';

/**
 * Article: Delegation, Not Instruction
 * Why effective AI orchestration is about delegation, not programming
 * Core transformation: "Tell it what to do" → "Tell it what you need"
 */
export default function Delegation() {
  return (
    <ArticleLayout
      title="Delegation, Not Instruction"
      hook="The difference between a struggling AI project and a thriving one often comes down to one thing: did you instruct it, or did you delegate to it?"
      ctaText="Start delegating to your AI orchestra."
    >
      {/* Section 1: The Instruction Trap */}
      <ArticleSection delay={0}>
        <SectionTitle>Stop Micromanaging Your AI</SectionTitle>
        <Paragraph>
          Most people treat AI like a very fast typist. Step one, do this. Step
          two, do that. Click here. Parse this. Save there.
        </Paragraph>
        <Paragraph>
          This is insane. You have a system that can understand context, reason
          about goals, and figure out steps you never thought of — and you're
          giving it a checklist.
        </Paragraph>
        <Paragraph>
          That's not using AI. That's wasting it.
        </Paragraph>
        <Paragraph>
          The instructions assume you thought of everything. You didn't. They
          assume the world won't change. It will. They assume AI doesn't know
          anything you didn't tell it. It knows more than you can possibly
          instruct.
        </Paragraph>
      </ArticleSection>

      {/* Section 2: What Delegation Actually Is */}
      <ArticleSection delay={0.1}>
        <SectionTitle>What Delegation Actually Is</SectionTitle>
        <Paragraph>
          Delegation is the transfer of authority along with responsibility.
        </Paragraph>
        <Paragraph>
          When you delegate, you don't specify every step. You specify the
          outcome, the constraints, and the context. Then you trust the delegate
          to figure out the path.
        </Paragraph>
        <ComparisonBlock
          oldWay={{
            label: 'Instruction',
            content:
              'Open file X, read lines 10-50, extract emails matching pattern Y, save to file Z',
          }}
          newWay={{
            label: 'Delegation',
            content:
              "Find all customer email addresses from last month's support tickets",
          }}
        />
        <Paragraph>
          The instruction breaks if anything changes. The delegation survives
          because it captures intent, not implementation.
        </Paragraph>
      </ArticleSection>

      {/* Section 3: The Three Elements */}
      <ArticleSection delay={0.2}>
        <SectionTitle>The Formula</SectionTitle>
        <Paragraph>
          Effective delegation has three components. Miss any one, and it fails.
        </Paragraph>
        <ElementsBlock />
        <Paragraph>
          <strong>Outcome:</strong> What does success look like? "Customer gets
          their refund processed" is an outcome. "Click the refund button" is
          instruction.
        </Paragraph>
        <Paragraph>
          <strong>Context:</strong> What's relevant? Customer history. Refund
          policy. The edge cases that actually matter.
        </Paragraph>
        <Paragraph>
          <strong>Constraints:</strong> Where are the boundaries? Budget limits.
          Time windows. When to escalate. Constraints aren't restrictions —
          they're guardrails for trust.
        </Paragraph>
      </ArticleSection>

      {/* Section 4: The Shift */}
      <ArticleSection delay={0.3}>
        <SectionTitle>Feel the Difference</SectionTitle>
        <Paragraph>
          Here's how you know you've made the shift:
        </Paragraph>
        <Paragraph>
          You describe what you need. You watch the AI figure out how. It takes
          a path you didn't anticipate — and it works. You realize you would
          have over-specified. You would have constrained it to your limited
          imagination.
        </Paragraph>
        <ShiftBlock />
        <Paragraph>
          That moment — when the AI solves a problem better than your
          instructions would have — that's when you understand. You're not
          programming anymore. You're leading.
        </Paragraph>
        <ClosingLine>
          Tell machines what to do. Tell intelligence what you need.
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
    <h2
      className={`text-2xl md:text-3xl font-bold mb-6 transition-colors duration-300 ${
        isLightMode
          ? 'text-[oklch(0.15_0.02_260)]'
          : 'text-[oklch(0.95_0.01_90)]'
      }`}
    >
      {children}
    </h2>
  );
}

function Paragraph({ children }: { children: React.ReactNode }) {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <p
      className={`text-lg leading-relaxed mb-4 transition-colors duration-300 ${
        isLightMode
          ? 'text-[oklch(0.30_0.01_260)]'
          : 'text-[oklch(0.7_0.01_260)]'
      }`}
    >
      {children}
    </p>
  );
}

function ComparisonBlock({
  oldWay,
  newWay,
}: {
  oldWay: { label: string; content: string };
  newWay: { label: string; content: string };
}) {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <div className="my-8 grid md:grid-cols-2 gap-4">
      <div
        className={`p-5 rounded-lg transition-colors duration-300 ${
          isLightMode
            ? 'bg-[oklch(0.94_0.01_260)]'
            : 'bg-[oklch(0.12_0.02_260)]'
        }`}
      >
        <p
          className={`text-xs font-mono tracking-wider mb-2 ${
            isLightMode
              ? 'text-[oklch(0.50_0.01_260)]'
              : 'text-[oklch(0.45_0.01_260)]'
          }`}
        >
          {oldWay.label.toUpperCase()}
        </p>
        <p
          className={`text-base ${
            isLightMode
              ? 'text-[oklch(0.35_0.01_260)]'
              : 'text-[oklch(0.6_0.01_260)]'
          }`}
        >
          "{oldWay.content}"
        </p>
      </div>
      <div
        className={`p-5 rounded-lg border transition-colors duration-300 ${
          isLightMode
            ? 'bg-[oklch(0.96_0.03_180)] border-[oklch(0.75_0.15_180)]'
            : 'bg-[oklch(0.12_0.04_180)] border-[oklch(0.35_0.15_180)]'
        }`}
      >
        <p
          className={`text-xs font-mono tracking-wider mb-2 ${
            isLightMode
              ? 'text-[oklch(0.35_0.20_180)]'
              : 'text-[oklch(0.65_0.25_180)]'
          }`}
        >
          {newWay.label.toUpperCase()}
        </p>
        <p
          className={`text-base ${
            isLightMode
              ? 'text-[oklch(0.25_0.05_180)]'
              : 'text-[oklch(0.75_0.05_180)]'
          }`}
        >
          "{newWay.content}"
        </p>
      </div>
    </div>
  );
}

function ElementsBlock() {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <div
      className={`my-8 p-6 rounded-lg text-center transition-colors duration-300 ${
        isLightMode ? 'bg-[oklch(0.94_0.01_260)]' : 'bg-[oklch(0.12_0.02_260)]'
      }`}
    >
      <p
        className={`text-lg font-mono tracking-wide ${
          isLightMode
            ? 'text-[oklch(0.35_0.20_180)]'
            : 'text-[oklch(0.65_0.25_180)]'
        }`}
      >
        outcome + context + constraints = delegation
      </p>
    </div>
  );
}

function ShiftBlock() {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <div
      className={`my-8 p-6 rounded-lg border-l-4 transition-colors duration-300 ${
        isLightMode
          ? 'bg-[oklch(0.96_0.03_180)] border-[oklch(0.55_0.20_180)]'
          : 'bg-[oklch(0.12_0.04_180)] border-[oklch(0.65_0.25_180)]'
      }`}
    >
      <p
        className={`text-base italic ${
          isLightMode
            ? 'text-[oklch(0.25_0.05_180)]'
            : 'text-[oklch(0.75_0.05_180)]'
        }`}
      >
        You asked it to "summarize customer feedback from Q3." It found sentiment
        patterns you didn't ask for, flagged three accounts at churn risk, and
        drafted responses. You would have asked for a summary. It delivered
        insight.
      </p>
    </div>
  );
}

function ClosingLine({ children }: { children: React.ReactNode }) {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <p
      className={`text-xl font-medium mt-8 transition-colors duration-300 ${
        isLightMode
          ? 'text-[oklch(0.35_0.20_180)]'
          : 'text-[oklch(0.65_0.25_180)]'
      }`}
    >
      {children}
    </p>
  );
}
