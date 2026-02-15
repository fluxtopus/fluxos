'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { ArticleLayout, useExtendedBrainTheme } from '@/components/ExtendedBrain';

/**
 * Article: The Case for Agency
 * Why smart autonomous systems need real decision-making authority
 * Core transformation: "Automated" → "Autonomous"
 */
export default function Agency() {
  return (
    <ArticleLayout
      title="The Case for Agency"
      hook="Scripts follow instructions. Agents make decisions. The difference isn't technical — it's the difference between automation that breaks and automation that adapts."
      ctaText="Build workflows with real agency."
    >
      {/* Section 1: The Brittleness Problem */}
      <ArticleSection delay={0}>
        <SectionTitle>Scripts Are Stupid</SectionTitle>
        <Paragraph>
          Let's be direct: scripted automation is a dead end.
        </Paragraph>
        <Paragraph>
          You write a script to handle customer inquiries. It works for a week.
          Then someone asks a question you didn't anticipate. The script doesn't
          adapt. It doesn't think. It does exactly what you told it — which is
          now the wrong thing.
        </Paragraph>
        <ExampleBlock />
        <Paragraph>
          This isn't a bug. It's the nature of scripts. They encode your
          assumptions at a moment in time. The world moves on. Your script doesn't.
        </Paragraph>
        <Paragraph>
          Everyone knows this. Everyone keeps writing scripts anyway. It's insane.
        </Paragraph>
      </ArticleSection>

      {/* Section 2: What Agency Actually Means */}
      <ArticleSection delay={0.1}>
        <SectionTitle>What Agency Actually Means</SectionTitle>
        <Paragraph>
          Agency is the capacity to make decisions within boundaries.
        </Paragraph>
        <Paragraph>
          Not unlimited freedom — that's chaos. Not rigid instructions — that's
          scripts. Agency is the space between: clear outcomes, flexible methods.
        </Paragraph>
        <ComparisonBlock
          oldWay={{
            label: 'Script',
            content: 'If customer asks X, respond with Y',
          }}
          newWay={{
            label: 'Agent',
            content: 'Understand what the customer needs and help them get it',
          }}
        />
        <Paragraph>
          The script handles one case. The agent handles intent. When something
          new appears, the script crashes. The agent reasons.
        </Paragraph>
      </ArticleSection>

      {/* Section 3: Bounded Autonomy */}
      <ArticleSection delay={0.2}>
        <SectionTitle>Bounded Autonomy</SectionTitle>
        <Paragraph>
          The key is boundaries. An agent without constraints is dangerous. An
          agent without agency is just a script with extra steps.
        </Paragraph>
        <BoundaryBlock />
        <Paragraph>
          Good boundaries aren't restrictions. They're context. They tell the
          agent: here's your domain, here's what success looks like, here's
          where you ask for help.
        </Paragraph>
        <Paragraph>
          Within those boundaries, the agent has full authority. That's not
          giving up control. That's delegating with clarity.
        </Paragraph>
      </ArticleSection>

      {/* Section 4: The Shift */}
      <ArticleSection delay={0.3}>
        <SectionTitle>Make the Shift</SectionTitle>
        <Paragraph>
          Stop writing scripts. Start defining outcomes.
        </Paragraph>
        <Paragraph>
          Give an agent a small decision. Watch it reason. See it handle a case
          you never wrote code for. Feel the difference between hoping your
          automation survives and knowing it adapts.
        </Paragraph>
        <Paragraph>
          That's agency. Not a feature. A fundamentally different way to build.
        </Paragraph>
        <ClosingLine>
          Scripts encode the past. Agents navigate the future.
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

function ExampleBlock() {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <div
      className={`my-8 p-6 rounded-lg border-l-4 transition-colors duration-300 ${
        isLightMode
          ? 'bg-[oklch(0.94_0.01_260)] border-[oklch(0.7_0.15_30)]'
          : 'bg-[oklch(0.12_0.02_260)] border-[oklch(0.6_0.2_30)]'
      }`}
    >
      <p
        className={`text-sm font-mono mb-3 ${
          isLightMode
            ? 'text-[oklch(0.5_0.15_30)]'
            : 'text-[oklch(0.7_0.2_30)]'
        }`}
      >
        WHAT ACTUALLY HAPPENS:
      </p>
      <p
        className={`text-base mb-3 ${
          isLightMode
            ? 'text-[oklch(0.35_0.01_260)]'
            : 'text-[oklch(0.6_0.01_260)]'
        }`}
      >
        Customer: "I ordered the blue one but I'm wondering if I should have
        gotten the red instead. Can I see what it would look like?"
      </p>
      <p
        className={`text-base mb-2 ${
          isLightMode
            ? 'text-[oklch(0.50_0.01_260)]'
            : 'text-[oklch(0.45_0.01_260)]'
        }`}
      >
        <strong>Script:</strong> "I don't understand. Would you like to return your order?"
      </p>
      <p
        className={`text-base ${
          isLightMode
            ? 'text-[oklch(0.25_0.15_180)]'
            : 'text-[oklch(0.65_0.25_180)]'
        }`}
      >
        <strong>Agent:</strong> "Here's the red version on a similar setup. Want me
        to start an exchange, or just keep this as reference?"
      </p>
    </div>
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

function BoundaryBlock() {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <div
      className={`my-8 p-6 rounded-lg transition-colors duration-300 ${
        isLightMode ? 'bg-[oklch(0.94_0.01_260)]' : 'bg-[oklch(0.12_0.02_260)]'
      }`}
    >
      <p
        className={`text-sm font-mono tracking-wide mb-3 ${
          isLightMode
            ? 'text-[oklch(0.35_0.20_180)]'
            : 'text-[oklch(0.65_0.25_180)]'
        }`}
      >
        EFFECTIVE BOUNDARIES:
      </p>
      <ul
        className={`space-y-2 text-base ${
          isLightMode
            ? 'text-[oklch(0.35_0.01_260)]'
            : 'text-[oklch(0.6_0.01_260)]'
        }`}
      >
        <li>• Clear outcomes, flexible methods</li>
        <li>• Known escalation points</li>
        <li>• Transparent reasoning</li>
        <li>• Defined resource limits</li>
      </ul>
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
