'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { ArticleLayout } from '@/components/ExtendedBrain';

/**
 * Article 3: Your AI Employees
 * Core insight: Think of agents as employees with jobs, not scripts that run
 */
export default function AIEmployeesPage() {
  return (
    <ArticleLayout
      title="Your AI Employees: A New Mental Model for Automation"
      hook="Stop thinking about automation tools. Start thinking about AI employees."
      ctaText="Describe what you need and watch your AI team build it"
    >
      {/* Section 1: The Old Mental Model */}
      <ArticleSection delay={0}>
        <SectionTitle>The Old Mental Model</SectionTitle>
        <Paragraph>
          For decades, we've thought about automation the same way: as scripts
          that run. You define the steps. You specify the conditions. You program
          the logic. The machine executes exactly what you told it.
        </Paragraph>
        <Paragraph>
          This mental model made sense when automation meant "do this exact
          sequence of keystrokes" or "if this cell changes, update that cell."
          The machine was a tireless rule-follower, nothing more.
        </Paragraph>
        <Paragraph>
          But this model has a fundamental limitation: you have to think of
          everything in advance. Every edge case. Every exception. Every possible
          input. If you don't program it, it doesn't happen.
        </Paragraph>
        <Paragraph>
          The result? Brittle automation that breaks when reality doesn't match
          your assumptions. Endless maintenance as you patch holes. Growing
          complexity as you try to handle "just one more case."
        </Paragraph>
      </ArticleSection>

      {/* Section 2: The New Mental Model */}
      <ArticleSection delay={0.1}>
        <SectionTitle>The New Mental Model</SectionTitle>
        <Paragraph>
          What if, instead of scripts, you thought about AI agents the way you
          think about employees?
        </Paragraph>
        <Paragraph>
          An employee doesn't need step-by-step instructions for every task. You
          tell them the outcome you want: "Research our competitors' pricing" or
          "Summarize this customer feedback" or "Prepare a report on last month's
          sales." They figure out how to get there.
        </Paragraph>
        <Paragraph>
          They use judgment. They handle unexpected situations. They ask
          clarifying questions when needed. They bring their skills to the
          problem rather than executing a predefined script.
        </Paragraph>
        <Paragraph>
          This is how AI agents work. You describe the outcome you want. The
          agent figures out how to achieve it. When it encounters something
          unexpected, it adapts. When it needs more information, it gathers it.
        </Paragraph>
        <Paragraph>
          You're not programming anymore. You're delegating.
        </Paragraph>
      </ArticleSection>

      {/* Section 3: The Org Chart Analogy */}
      <ArticleSection delay={0.2}>
        <SectionTitle>The Org Chart Analogy</SectionTitle>
        <Paragraph>
          In Tentackl, a workflow is essentially an org chart for your AI
          employees. Each node is a role. Each agent has a specific job. The
          workflow defines who reports to whom and how work flows between them.
        </Paragraph>
        <Paragraph>
          Think about it:
        </Paragraph>
        <BulletList
          items={[
            <><strong>The Research Agent</strong> — Their job is to gather information. Give them a topic, they come back with relevant data.</>,
            <><strong>The Analysis Agent</strong> — Their job is to make sense of data. Give them raw information, they identify patterns and insights.</>,
            <><strong>The Writing Agent</strong> — Their job is to communicate clearly. Give them findings, they produce readable output.</>,
            <><strong>The Validator Agent</strong> — Their job is quality control. They check work before it's finalized.</>,
          ]}
        />
        <Paragraph>
          When you design a workflow, you're deciding which roles you need and
          how they should collaborate. Just like building a team for a project.
        </Paragraph>
      </ArticleSection>

      {/* Section 4: Delegation Without Meetings */}
      <ArticleSection delay={0.3}>
        <SectionTitle>Delegation Without Meetings</SectionTitle>
        <Paragraph>
          Here's where AI employees beat human employees for certain tasks: they
          coordinate without meetings.
        </Paragraph>
        <Paragraph>
          In a human team, collaboration requires communication overhead.
          Handoffs need to be explained. Status updates need to be shared.
          Misunderstandings need to be resolved. This overhead is necessary and
          valuable for complex, ambiguous work — but it's expensive for routine
          tasks.
        </Paragraph>
        <Paragraph>
          AI agents pass context seamlessly. Agent A finishes its work and hands
          off to Agent B with complete context. No meetings. No email chains. No
          "sorry, I didn't realize you needed that format." The handoff is
          instant and complete.
        </Paragraph>
        <Paragraph>
          This doesn't mean AI replaces human judgment. It means AI handles the
          routine coordination so humans can focus on the decisions that actually
          need human insight.
        </Paragraph>
      </ArticleSection>

      {/* Section 5: Designing Outcomes */}
      <ArticleSection delay={0.4}>
        <SectionTitle>Designing Outcomes, Not Steps</SectionTitle>
        <Paragraph>
          When you adopt this mental model, something shifts in how you approach
          automation. Instead of thinking "what steps should this execute?" you
          think "what outcome do I want?"
        </Paragraph>
        <Paragraph>
          This is a more natural way to think. When you hire a contractor, you
          don't specify every hammer swing. You say "I want a deck that looks
          like this" and trust their expertise to get there.
        </Paragraph>
        <Paragraph>
          The same applies to AI workflows:
        </Paragraph>
        <BulletList
          items={[
            <><strong>Instead of:</strong> "Search Google for X, open the first three results, copy the text, format it as bullet points..."</>,
            <><strong>Say:</strong> "Research X and summarize the key findings."</>,
          ]}
        />
        <BulletList
          items={[
            <><strong>Instead of:</strong> "Open the spreadsheet, filter column B for values greater than 100, calculate the average of column C..."</>,
            <><strong>Say:</strong> "Analyze this data and highlight significant trends."</>,
          ]}
        />
        <Paragraph>
          You describe the destination. The AI figures out the route.
        </Paragraph>
        <Paragraph>
          This isn't laziness — it's leverage. You're using your human judgment
          for what matters (defining outcomes) and delegating execution to
          systems that handle it well.
        </Paragraph>
        <Paragraph>
          So next time you're thinking about automation, try this: imagine you're
          hiring a small team for the job. What roles would you need? What would
          you tell each person? How would work flow between them?
        </Paragraph>
        <Paragraph>
          That's your workflow. That's your AI team. Describe what you need, and
          watch them build it.
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
