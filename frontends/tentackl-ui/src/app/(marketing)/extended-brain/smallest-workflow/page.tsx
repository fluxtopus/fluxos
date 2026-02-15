'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { ArticleLayout } from '@/components/ExtendedBrain';

/**
 * Article 2: The Smallest Workflow That Ships
 * Core insight: Start small, ship fast, learn and compound
 */
export default function SmallestWorkflowPage() {
  return (
    <ArticleLayout
      title="The Smallest Workflow That Ships"
      hook="The best automation isn't comprehensive — it's the smallest thing that delivers value today."
      ctaText="Build your first workflow in 5 minutes"
    >
      {/* Section 1: The Perfectionism Trap */}
      <ArticleSection delay={0}>
        <SectionTitle>The Perfectionism Trap</SectionTitle>
        <Paragraph>
          Every entrepreneur has a fantasy version of automation. It's the
          elaborate system that handles everything: capturing leads, nurturing
          prospects, processing orders, managing inventory, sending reports,
          analyzing trends, and making coffee.
        </Paragraph>
        <Paragraph>
          Here's the problem: that system never gets built.
        </Paragraph>
        <Paragraph>
          The gap between "basic automation" and "comprehensive system" feels so
          large that most people never start. They spend weeks planning the
          perfect workflow. They research every edge case. They design elaborate
          decision trees. And then... nothing ships.
        </Paragraph>
        <Paragraph>
          Meanwhile, their competitors are automating one small thing at a time,
          learning as they go, and compounding those improvements over months.
        </Paragraph>
      </ArticleSection>

      {/* Section 2: Minimum Viable Workflow */}
      <ArticleSection delay={0.1}>
        <SectionTitle>Minimum Viable Workflow</SectionTitle>
        <Paragraph>
          Ask yourself: what's the one task you do repeatedly that takes 15
          minutes each time? Not the most important task. Not the most complex.
          Just something repetitive that you do often.
        </Paragraph>
        <Paragraph>
          Maybe it's:
        </Paragraph>
        <BulletList
          items={[
            "Summarizing customer feedback from your inbox",
            "Researching a competitor's recent blog posts",
            "Formatting data from one tool to use in another",
            "Generating a weekly status update from your project tracker",
          ]}
        />
        <Paragraph>
          None of these are glamorous. None will transform your business
          overnight. But each one, automated, gives you back 15 minutes. Do that
          daily, and you've reclaimed over an hour per week. Do it for five
          tasks, and you've freed up an entire workday each month.
        </Paragraph>
        <Paragraph>
          That's the minimum viable workflow: not a system that does everything,
          but a simple automation that does one thing well.
        </Paragraph>
      </ArticleSection>

      {/* Section 3: The Compound Effect */}
      <ArticleSection delay={0.2}>
        <SectionTitle>The Compound Effect</SectionTitle>
        <Paragraph>
          Here's what people miss about starting small: each workflow you build
          teaches you something that makes the next one easier.
        </Paragraph>
        <Paragraph>
          Your first workflow will be awkward. You'll make mistakes. You'll
          realize halfway through that you should have structured it differently.
          That's fine — that's learning.
        </Paragraph>
        <Paragraph>
          Your second workflow will be faster. You'll know what works and what
          doesn't. You'll have intuition about how to break down a task into
          steps.
        </Paragraph>
        <Paragraph>
          By your fifth workflow, you'll start seeing patterns. You'll recognize
          when a new task can reuse pieces from previous workflows. You'll know
          immediately how to structure something that would have taken you hours
          to figure out before.
        </Paragraph>
        <Paragraph>
          This is the compound effect of shipping small. Each workflow isn't just
          about saving time on one task — it's an investment in your ability to
          automate everything else.
        </Paragraph>
      </ArticleSection>

      {/* Section 4: Permission to Ship Imperfect */}
      <ArticleSection delay={0.3}>
        <SectionTitle>Permission to Ship Imperfect</SectionTitle>
        <Paragraph>
          Let's be direct: your first workflow will be imperfect. It might miss
          edge cases. It might need manual cleanup occasionally. It might not
          handle every possible input gracefully.
        </Paragraph>
        <Paragraph>
          That's okay. In fact, it's better than okay — it's correct.
        </Paragraph>
        <Paragraph>
          Shipping an imperfect automation that works 80% of the time is
          infinitely better than designing a perfect automation that exists only
          in your planning documents. The 80% solution is saving you time right
          now. The perfect solution is saving you nothing.
        </Paragraph>
        <Paragraph>
          Here's a secret from software engineering: most production systems
          started imperfect and improved over time. The best automation isn't the
          one that launched perfectly — it's the one that launched at all.
        </Paragraph>
      </ArticleSection>

      {/* Section 5: Starting Points, Not Endpoints */}
      <ArticleSection delay={0.4}>
        <SectionTitle>Starting Points, Not Endpoints</SectionTitle>
        <Paragraph>
          When you use Tentackl's examples gallery or describe a workflow in
          natural language, think of what you create as a starting point, not an
          endpoint.
        </Paragraph>
        <Paragraph>
          The goal isn't to get it right the first time. The goal is to get
          something running that you can observe, learn from, and improve.
        </Paragraph>
        <BulletList
          items={[
            <><strong>Week 1:</strong> Build a basic workflow. Watch it run. Note what it gets wrong.</>,
            <><strong>Week 2:</strong> Adjust based on what you learned. Add handling for the most common failure.</>,
            <><strong>Week 3:</strong> Extend it slightly. Maybe add one more step or handle one more input type.</>,
            <><strong>Week 4:</strong> Consider: is this workflow good enough now? Or do you want to start a new one?</>,
          ]}
        />
        <Paragraph>
          By the end of the month, you'll have a workflow that actually fits your
          needs — not because you designed it perfectly upfront, but because you
          shaped it through use.
        </Paragraph>
        <Paragraph>
          So here's your permission: ship the smallest workflow that does
          something useful. Ship it today. Watch it work. Learn. Repeat.
        </Paragraph>
        <Paragraph>
          The only workflow that fails is the one that never runs.
        </Paragraph>
      </ArticleSection>
    </ArticleLayout>
  );
}

// Helper components for consistent article styling

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
  return (
    <h2 className="text-2xl md:text-3xl font-bold text-[oklch(0.95_0.01_90)] mb-6">
      {children}
    </h2>
  );
}

function Paragraph({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-lg text-[oklch(0.7_0.01_260)] leading-relaxed mb-4">
      {children}
    </p>
  );
}

function BulletList({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="text-lg text-[oklch(0.7_0.01_260)] leading-relaxed mb-4 space-y-2 ml-6">
      {items.map((item, index) => (
        <li
          key={index}
          className="relative pl-4 before:content-[''] before:absolute before:left-0 before:top-3 before:w-1.5 before:h-1.5 before:bg-[oklch(0.65_0.25_180)] before:rounded-full"
        >
          {item}
        </li>
      ))}
    </ul>
  );
}
