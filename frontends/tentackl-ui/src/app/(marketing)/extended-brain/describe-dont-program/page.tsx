'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { ArticleLayout, useExtendedBrainTheme } from '@/components/ExtendedBrain';

/**
 * Article 3: Describe, Don't Program
 * The practical shift — how to think about your work differently
 * Core transformation: "How do I build this automation?" → "What do I want done?"
 */
export default function DescribeDontProgram() {
  return (
    <ArticleLayout
      title="Describe, Don't Program"
      hook="The hardest part of automation isn't technical. It's learning to describe what you actually want."
      ctaText="Describe your first workflow."
    >
      {/* Section 1: The Old Way */}
      <ArticleSection delay={0}>
        <SectionTitle>The Old Way</SectionTitle>
        <Paragraph>
          For decades, automation meant programming.
        </Paragraph>
        <Paragraph>
          You had to think like a machine. Break tasks into atomic steps. Handle every
          possible exception. Anticipate every edge case. Build decision trees that
          covered every branch.
        </Paragraph>
        <Paragraph>
          If you didn't specify something, it didn't happen. If you didn't handle an
          error, the whole thing crashed. The machine did exactly what you told it —
          nothing more, nothing less.
        </Paragraph>
        <Paragraph>
          This required a specific kind of thinking. Technical thinking. And most
          business owners either had to learn it or hire someone who had.
        </Paragraph>
        <Paragraph>
          The automation was only as good as your ability to think mechanically.
        </Paragraph>
      </ArticleSection>

      {/* Section 2: The New Way */}
      <ArticleSection delay={0.1}>
        <SectionTitle>The New Way</SectionTitle>
        <Paragraph>
          But here's the thing: machines have changed.
        </Paragraph>
        <Paragraph>
          AI agents don't need step-by-step instructions. They need to understand what
          you want. Give them an outcome, and they figure out the path. Give them a
          problem, and they work toward a solution.
        </Paragraph>
        <Paragraph>
          This means the skill that matters has shifted.
        </Paragraph>
        <Paragraph>
          It's no longer "can you program a solution?" It's "can you describe what
          you want?"
        </Paragraph>
        <Paragraph>
          And describing what you want is something you already know how to do. You
          do it every time you explain a task to a colleague. Every time you write a
          brief. Every time you tell someone "here's what I need."
        </Paragraph>
        <Paragraph>
          The technical barrier is gone. What remains is clarity.
        </Paragraph>
      </ArticleSection>

      {/* Section 3: The Art of Clear Description */}
      <ArticleSection delay={0.2}>
        <SectionTitle>The Art of Clear Description</SectionTitle>
        <Paragraph>
          What does good delegation to AI look like? The same thing good delegation
          to humans looks like:
        </Paragraph>
        <PrincipleBlock
          number={1}
          title="Outcome Over Process"
          bad="Search for articles, read them, extract key points, summarize..."
          good="Give me a summary of recent news about [topic]."
          insight="You describe where you want to end up, not how to get there."
        />
        <PrincipleBlock
          number={2}
          title="Context Over Assumptions"
          bad="Analyze the data."
          good="Analyze last month's sales data and highlight any unusual patterns that might indicate problems or opportunities."
          insight="You give enough context for intelligent decisions."
        />
        <PrincipleBlock
          number={3}
          title="Intent Over Mechanics"
          bad="Send an email with subject X and body Y to list Z at time T."
          good="Notify our customers about the upcoming maintenance window. Make sure they know what to expect and when."
          insight="You share why, not just what."
        />
        <Paragraph>
          The pattern is simple: treat your AI orchestra like a smart team member
          who needs to understand the mission, not a machine that needs to be programmed.
        </Paragraph>
      </ArticleSection>

      {/* Section 4: Your First Description */}
      <ArticleSection delay={0.3}>
        <SectionTitle>Your First Description</SectionTitle>
        <Paragraph>
          Here's a framework for thinking about any task you want to delegate:
        </Paragraph>
        <FrameworkList
          items={[
            { question: "What's the outcome?", detail: "What does \"done\" look like? What will exist that doesn't exist now?" },
            { question: "What context matters?", detail: "What would a smart person need to know to do this well?" },
            { question: "What does good look like?", detail: "How will you know if the result is right?" },
          ]}
        />
        <Paragraph>
          That's it. Answer those three questions, and you've written a workflow
          description.
        </Paragraph>
        <ExampleBlock />
        <Paragraph>
          That's a workflow. You just wrote it. No programming required.
        </Paragraph>
      </ArticleSection>

      {/* Section 5: What Happens Next */}
      <ArticleSection delay={0.4}>
        <SectionTitle>What Happens Next</SectionTitle>
        <Paragraph>
          Each description teaches you to describe better.
        </Paragraph>
        <Paragraph>
          Your first workflows will be rough. You'll realize you weren't clear about
          something. The output won't quite match what you had in your head. That's
          fine — that's learning.
        </Paragraph>
        <Paragraph>
          But with each iteration, you get better at the art of clear description.
          You learn what context matters. You learn how to specify "good." You develop
          intuition for how to express what you want.
        </Paragraph>
        <Paragraph>
          This is a skill that compounds. The better you get at describing, the more
          you can delegate. The more you delegate, the more practice you get. The more
          practice, the better you get.
        </Paragraph>
        <Paragraph>
          And here's the beautiful part: this skill transfers. Getting better at
          describing what you want to AI makes you better at describing what you want
          to humans. It makes you better at thinking about work itself.
        </Paragraph>
      </ArticleSection>

      {/* Section 6: The Only Skill You Need */}
      <ArticleSection delay={0.5}>
        <SectionTitle>The Only Skill You Need</SectionTitle>
        <Paragraph>
          Programming required learning a new language — the language of machines.
        </Paragraph>
        <Paragraph>
          Delegation requires something different — clarity about what you actually want.
        </Paragraph>
        <Paragraph>
          You already know how to delegate — you do it every day with colleagues.
          But humans fill in gaps. They ask clarifying questions. They make
          reasonable assumptions. This forgiving environment means we rarely have
          to be perfectly clear.
        </Paragraph>
        <Paragraph>
          AI raises the bar. Not because it's inflexible, but because it takes your
          words seriously. It does what you describe, not what you vaguely intended.
          Which means you have to mean what you say.
        </Paragraph>
        <Paragraph>
          This is actually a gift. Because when you learn to describe what you really
          want, you often discover you weren't clear about it yourself. The act of
          describing forces clarity. And clarity is valuable everywhere.
        </Paragraph>
        <Paragraph>
          So here's the invitation: stop trying to learn automation. Start learning
          to describe what you want.
        </Paragraph>
        <ClosingLine>
          The AI will handle the rest.
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

function PrincipleBlock({
  number,
  title,
  bad,
  good,
  insight,
}: {
  number: number;
  title: string;
  bad: string;
  good: string;
  insight: string;
}) {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <div className={`my-8 p-6 rounded-lg transition-colors duration-300 ${
      isLightMode ? 'bg-[oklch(0.94_0.01_260)]' : 'bg-[oklch(0.12_0.02_260)]'
    }`}>
      <h3 className={`font-mono text-sm tracking-wider mb-4 ${
        isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'
      }`}>
        {number}. {title.toUpperCase()}
      </h3>
      <div className="mb-3">
        <span className={`font-mono text-xs ${
          isLightMode ? 'text-[oklch(0.50_0.01_260)]' : 'text-[oklch(0.50_0.01_260)]'
        }`}>Bad:</span>
        <p className={`text-base italic ${
          isLightMode ? 'text-[oklch(0.45_0.01_260)]' : 'text-[oklch(0.55_0.01_260)]'
        }`}>"{bad}"</p>
      </div>
      <div className="mb-3">
        <span className={`font-mono text-xs ${
          isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'
        }`}>Good:</span>
        <p className={`text-base font-medium ${
          isLightMode ? 'text-[oklch(0.25_0.02_260)]' : 'text-[oklch(0.85_0.01_90)]'
        }`}>"{good}"</p>
      </div>
      <p className={`text-sm mt-4 ${
        isLightMode ? 'text-[oklch(0.40_0.01_260)]' : 'text-[oklch(0.60_0.01_260)]'
      }`}>
        {insight}
      </p>
    </div>
  );
}

function FrameworkList({
  items,
}: {
  items: { question: string; detail: string }[];
}) {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <ol className={`my-6 space-y-4 ${
      isLightMode ? 'text-[oklch(0.30_0.01_260)]' : 'text-[oklch(0.7_0.01_260)]'
    }`}>
      {items.map((item, index) => (
        <li key={index} className="flex gap-3">
          <span className={`font-mono text-lg font-bold ${
            isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'
          }`}>{index + 1}.</span>
          <div>
            <span className="font-semibold">{item.question}</span>
            <span className={`ml-2 ${
              isLightMode ? 'text-[oklch(0.45_0.01_260)]' : 'text-[oklch(0.55_0.01_260)]'
            }`}>{item.detail}</span>
          </div>
        </li>
      ))}
    </ol>
  );
}

function ExampleBlock() {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <div className={`my-8 p-6 rounded-lg border-l-4 transition-colors duration-300 ${
      isLightMode
        ? 'bg-[oklch(0.94_0.01_260)] border-[oklch(0.45_0.20_180)]'
        : 'bg-[oklch(0.12_0.02_260)] border-[oklch(0.65_0.25_180)]'
    }`}>
      <p className={`font-mono text-xs tracking-wider mb-4 ${
        isLightMode ? 'text-[oklch(0.45_0.01_260)]' : 'text-[oklch(0.55_0.01_260)]'
      }`}>EXAMPLE</p>
      <p className={`text-lg font-medium mb-4 ${
        isLightMode ? 'text-[oklch(0.20_0.02_260)]' : 'text-[oklch(0.90_0.01_90)]'
      }`}>
        Task: "Keep me informed about what competitors are doing."
      </p>
      <ol className={`space-y-2 text-base ${
        isLightMode ? 'text-[oklch(0.35_0.01_260)]' : 'text-[oklch(0.65_0.01_260)]'
      }`}>
        <li>
          <span className={isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'}>1. Outcome:</span>{' '}
          A weekly summary of competitor activities that might affect our business.
        </li>
        <li>
          <span className={isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'}>2. Context:</span>{' '}
          We're in [industry]. Our main competitors are [A, B, C]. I care most about
          pricing changes, new features, and marketing campaigns.
        </li>
        <li>
          <span className={isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'}>3. Good looks like:</span>{' '}
          A brief, scannable summary that highlights what's actually important, not just
          everything that happened.
        </li>
      </ol>
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
