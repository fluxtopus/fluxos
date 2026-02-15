'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { ArticleLayout } from '@/components/ExtendedBrain';

/**
 * Article 1: The Automation Paradox
 * Core insight: Observable automation builds more trust than invisible magic
 */
export default function AutomationParadoxPage() {
  return (
    <ArticleLayout
      title="The Automation Paradox: Why Watching the Work Matters"
      hook="The most valuable automation isn't invisible — it's observable."
      ctaText="Watch a workflow execute in real-time"
    >
      {/* Section 1: The Black Box Problem */}
      <ArticleSection delay={0}>
        <SectionTitle>The Black Box Problem</SectionTitle>
        <Paragraph>
          We've been sold a myth about automation: that the best kind is invisible.
          Push a button, magic happens, results appear. The less you see, the
          better it works. Right?
        </Paragraph>
        <Paragraph>
          Wrong. This "black box" approach to automation creates a fundamental
          problem: it erodes trust over time. When you can't see what's happening
          inside a system, every unexpected output becomes suspicious. Every
          failure becomes mysterious. Every success becomes... lucky?
        </Paragraph>
        <Paragraph>
          For small business owners, this uncertainty is costly. You end up
          checking the automation's work manually — defeating the entire purpose.
          Or worse, you discover weeks later that something broke and nobody
          noticed.
        </Paragraph>
      </ArticleSection>

      {/* Section 2: The Psychology of Visibility */}
      <ArticleSection delay={0.1}>
        <SectionTitle>The Psychology of Visibility</SectionTitle>
        <Paragraph>
          Here's what behavioral economists have known for decades: people trust
          what they can see. It's why open kitchens in restaurants increase
          customer satisfaction — even though the food is exactly the same.
        </Paragraph>
        <Paragraph>
          The same principle applies to automation. When you watch a workflow
          execute step by step, something interesting happens in your brain:
        </Paragraph>
        <BulletList
          items={[
            "You understand what's actually happening",
            "You notice when something looks wrong before it fails",
            "You build intuition about how the system works",
            "You gain confidence that the output is legitimate",
          ]}
        />
        <Paragraph>
          This isn't just about feeling good. It's about developing the
          situational awareness that lets you trust automation with increasingly
          important tasks.
        </Paragraph>
      </ArticleSection>

      {/* Section 3: The Dashboard Paradox */}
      <ArticleSection delay={0.2}>
        <SectionTitle>The Dashboard Paradox</SectionTitle>
        <Paragraph>
          Consider this paradox: we demand dashboards for everything — sales
          metrics, website traffic, team performance — because we believe that
          what gets measured gets managed. Yet when it comes to automation, we
          accept black boxes.
        </Paragraph>
        <Paragraph>
          Why the double standard? Partly because early automation tools made
          visibility hard. Logging was an afterthought. Real-time monitoring was
          expensive. So we learned to work without it.
        </Paragraph>
        <Paragraph>
          But here's the thing: automation without visibility is like driving
          with your eyes closed. You might reach your destination, but you won't
          know how you got there — or how to repeat it.
        </Paragraph>
      </ArticleSection>

      {/* Section 4: Our Approach */}
      <ArticleSection delay={0.3}>
        <SectionTitle>A Different Approach</SectionTitle>
        <Paragraph>
          When I built Tentackl, I made a counterintuitive decision: visibility
          isn't a debugging feature — it's the foundation. Every workflow you
          create shows you exactly what's happening, in real-time:
        </Paragraph>
        <BulletList
          items={[
            'Watch each agent receive its task and start working',
            'See data flow between steps as it happens',
            'Understand why each decision was made',
            'Catch problems the moment they occur, not hours later',
          ]}
        />
        <Paragraph>
          This might seem like overhead. It's actually the opposite. When you can
          see what's happening, you spend less time debugging, less time
          second-guessing, and less time manually checking results.
        </Paragraph>
      </ArticleSection>

      {/* Section 5: For Your Business */}
      <ArticleSection delay={0.4}>
        <SectionTitle>What This Means for You</SectionTitle>
        <Paragraph>
          If you're a business owner considering automation, here's our advice:
          don't settle for black boxes. Any tool that hides what it's doing is a
          tool you'll eventually distrust.
        </Paragraph>
        <Paragraph>
          The goal isn't to eliminate human oversight — it's to make oversight
          efficient and meaningful. When you can see your automation working, you
          can:
        </Paragraph>
        <BulletList
          items={[
            <><strong>Start small with confidence</strong> — observe simple workflows before trusting complex ones</>,
            <><strong>Delegate progressively</strong> — give automation more responsibility as you understand it better</>,
            <><strong>Debug faster</strong> — when something breaks, you'll know exactly where and why</>,
            <><strong>Learn and improve</strong> — watching patterns emerge helps you build better workflows</>,
          ]}
        />
        <Paragraph>
          The automation paradox is this: the systems you can see working are the
          ones you'll trust to work without watching. Visibility is the path to
          true automation — not an obstacle to it.
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
