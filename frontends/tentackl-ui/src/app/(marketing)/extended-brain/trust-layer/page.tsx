'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { ArticleLayout, useExtendedBrainTheme } from '@/components/ExtendedBrain';

/**
 * Article 6: The Trust Layer
 * Why authentication is the hardest unsolved problem in multi-agent AI
 * Core transformation: "I'll figure out auth later" → "Auth is the foundation"
 */
export default function TrustLayer() {
  return (
    <ArticleLayout
      title="The Trust Layer"
      hook="Authentication is the hardest unsolved problem in multi-agent AI. If your auth layer can't answer &quot;who did what and were they allowed to?&quot; — you have a liability, not a product."
      ctaText="See how InkPass secures your AI orchestra."
    >
      {/* Section 1: The Problem */}
      <ArticleSection delay={0}>
        <SectionTitle>The Question Nobody Asks Until It's Too Late</SectionTitle>
        <Paragraph>
          Most multi-agent platforms treat authentication as an afterthought. A single
          API key. Maybe a JWT. Then the team ships to production and the questions
          start pouring in:
        </Paragraph>
        <QuestionList
          questions={[
            'Which agent performed that action?',
            'Who approved it?',
            'Can Agent B access the same data as Agent A?',
            'Does a subagent inherit the permissions of its parent?',
          ]}
        />
        <Paragraph>
          The answer, almost always, is "we don't know."
        </Paragraph>
        <Paragraph>
          When I built Tentackl — a multi-agent workflow orchestration engine — I
          hit this wall fast. Agents spawn subagents. Subagents call external APIs.
          Users belong to different organizations with different permission levels.
          A simple API key doesn't cut it. You need identity infrastructure
          purpose-built for autonomous systems.
        </Paragraph>
        <Paragraph>
          So I built InkPass.
        </Paragraph>
      </ArticleSection>

      {/* Section 2: Not Adapted. Built. */}
      <ArticleSection delay={0.1}>
        <SectionTitle>Not Adapted. Built.</SectionTitle>
        <Paragraph>
          InkPass is not a user-login library repurposed for agents. It's not
          middleware bolted onto an existing framework. It's an independent
          authentication and authorization service designed from day one for the
          reality that your "users" are sometimes humans, sometimes machines, and
          sometimes machines acting on behalf of humans.
        </Paragraph>
        <Paragraph>
          It runs as its own service, with its own database, its own API, and its
          own security boundary. Any platform can integrate it — not just ours.
        </Paragraph>
      </ArticleSection>

      {/* Section 3: ABAC Over RBAC */}
      <ArticleSection delay={0.2}>
        <SectionTitle>Permissions That Actually Model Reality</SectionTitle>
        <Paragraph>
          Most auth systems give you roles: Admin, User, Viewer. That works for a
          dashboard. It falls apart when an agent needs to execute workflows in
          Organization A during business hours but only read them in Organization B.
        </Paragraph>
        <Paragraph>
          InkPass uses <strong>Attribute-Based Access Control (ABAC)</strong>. Every
          permission check evaluates three dimensions: the resource being accessed,
          the action being performed, and the conditions that apply. A single API
          call answers questions that would otherwise require a wall of if-statements.
        </Paragraph>
        <PermissionCheckBlock />
        <Paragraph>
          This model scales naturally. Adding a new resource or a new condition
          doesn't require refactoring your permission logic — you add a row, not
          a branch.
        </Paragraph>
      </ArticleSection>

      {/* Section 4: Hybrid Authentication */}
      <ArticleSection delay={0.3}>
        <SectionTitle>One Pipeline, Three Methods</SectionTitle>
        <Paragraph>
          Multi-agent systems don't have a single type of caller. Humans use
          browsers. Services call other services. External platforms fire webhooks.
          InkPass handles all three through a unified pipeline:
        </Paragraph>
        <AuthMethodsTable />
        <Paragraph>
          All three methods produce the same internal permission context. There are
          no special cases, no separate code paths. An agent authenticated via API
          key goes through the same ABAC evaluation as a human authenticated via JWT.
        </Paragraph>
      </ArticleSection>

      {/* Section 5: Multi-Tenant Isolation */}
      <ArticleSection delay={0.4}>
        <SectionTitle>Isolation Is Structural, Not a Filter</SectionTitle>
        <Paragraph>
          Every entity in InkPass — users, groups, permissions, API keys, product
          plans — is scoped to an organization. This isn't a filter applied at the
          query level. It's a structural constraint in the data model.
        </Paragraph>
        <Paragraph>
          When Agent A runs on behalf of Organization X, it physically cannot access
          Organization Y's workflows, users, or configuration. This is the kind of
          guarantee that enterprise customers require and that most platforms fake
          with query-level filtering.
        </Paragraph>
      </ArticleSection>

      {/* Section 6: Fail-Safe */}
      <ArticleSection delay={0.5}>
        <SectionTitle>Fail-Safe by Default</SectionTitle>
        <Paragraph>
          This is the design decision that separates InkPass from general-purpose
          auth libraries: if InkPass is unreachable, the answer is <strong>deny</strong>.
        </Paragraph>
        <Paragraph>
          Not "allow and log." Not "cache the last known good state forever." Deny.
        </Paragraph>
        <Paragraph>
          In a world where agents act autonomously — creating workflows, processing
          data, calling external APIs — the safest failure mode is no access at all.
          You can always retry. You can't undo an unauthorized action.
        </Paragraph>
      </ArticleSection>

      {/* Section 7: The Bottom Line */}
      <ArticleSection delay={0.6}>
        <SectionTitle>The Bottom Line</SectionTitle>
        <Paragraph>
          The AI agent space is moving fast. Teams are deploying autonomous systems
          that make real decisions, touch real data, and interact with real users.
        </Paragraph>
        <Paragraph>
          If your auth layer can't answer "who is allowed to do what, and did they
          actually do it," you don't have a product — you have a liability.
        </Paragraph>
        <Paragraph>
          InkPass is open, independent, and built to be the auth backbone for any
          multi-agent platform. If your current auth story is "I'll figure it out
          later," later is going to be expensive.
        </Paragraph>
        <ClosingLine>
          I'd rather you figure it out now.
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

function QuestionList({ questions }: { questions: string[] }) {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <div
      className={`my-6 p-6 rounded-lg transition-colors duration-300 ${
        isLightMode ? 'bg-[oklch(0.94_0.01_260)]' : 'bg-[oklch(0.12_0.02_260)]'
      }`}
    >
      {questions.map((q, i) => (
        <p
          key={i}
          className={`text-base italic mb-2 last:mb-0 ${
            isLightMode
              ? 'text-[oklch(0.35_0.01_260)]'
              : 'text-[oklch(0.65_0.01_260)]'
          }`}
        >
          {q}
        </p>
      ))}
    </div>
  );
}

function PermissionCheckBlock() {
  const { isLightMode } = useExtendedBrainTheme();
  return (
    <div
      className={`my-8 p-6 rounded-lg font-mono text-sm transition-colors duration-300 ${
        isLightMode
          ? 'bg-[oklch(0.94_0.01_260)] text-[oklch(0.25_0.02_260)]'
          : 'bg-[oklch(0.10_0.02_260)] text-[oklch(0.80_0.01_90)]'
      }`}
    >
      <p className={`mb-1 ${isLightMode ? 'text-[oklch(0.50_0.01_260)]' : 'text-[oklch(0.50_0.01_260)]'}`}>
        Permission Check:
      </p>
      <p className="ml-4">
        Resource: <span className={isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'}>"workflows"</span>
      </p>
      <p className="ml-4">
        Action: <span className={isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'}>"execute"</span>
      </p>
      <p className="ml-4">
        Context: <span className={isLightMode ? 'text-[oklch(0.35_0.20_180)]' : 'text-[oklch(0.65_0.25_180)]'}>{'{ org: "acme-corp", time: "business_hours" }'}</span>
      </p>
      <p className={`ml-4 mt-2 font-semibold ${isLightMode ? 'text-[oklch(0.35_0.20_150)]' : 'text-[oklch(0.65_0.25_150)]'}`}>
        Result: ALLOWED
      </p>
    </div>
  );
}

function AuthMethodsTable() {
  const { isLightMode } = useExtendedBrainTheme();
  const methods = [
    { method: 'Bearer Token', mechanism: 'JWT validated by InkPass', useCase: 'Human users via browser or app' },
    { method: 'API Key', mechanism: 'SHA-256 hashed, scoped', useCase: 'Service-to-service communication' },
    { method: 'Webhook Signature', mechanism: 'HMAC verification', useCase: 'External event ingestion' },
  ];

  return (
    <div className="my-8 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr>
            {['Method', 'Mechanism', 'Use Case'].map((h) => (
              <th
                key={h}
                className={`px-4 py-3 text-left font-mono text-xs tracking-wider border-b transition-colors duration-300 ${
                  isLightMode
                    ? 'border-[oklch(0.85_0.01_260)] text-[oklch(0.35_0.20_180)]'
                    : 'border-[oklch(0.25_0.02_260)] text-[oklch(0.65_0.25_180)]'
                }`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {methods.map((row) => (
            <tr key={row.method}>
              <td
                className={`px-4 py-3 font-medium border-b transition-colors duration-300 ${
                  isLightMode
                    ? 'border-[oklch(0.90_0.01_260)] text-[oklch(0.20_0.02_260)]'
                    : 'border-[oklch(0.20_0.02_260)] text-[oklch(0.90_0.01_90)]'
                }`}
              >
                {row.method}
              </td>
              <td
                className={`px-4 py-3 border-b transition-colors duration-300 ${
                  isLightMode
                    ? 'border-[oklch(0.90_0.01_260)] text-[oklch(0.30_0.01_260)]'
                    : 'border-[oklch(0.20_0.02_260)] text-[oklch(0.7_0.01_260)]'
                }`}
              >
                {row.mechanism}
              </td>
              <td
                className={`px-4 py-3 border-b transition-colors duration-300 ${
                  isLightMode
                    ? 'border-[oklch(0.90_0.01_260)] text-[oklch(0.30_0.01_260)]'
                    : 'border-[oklch(0.20_0.02_260)] text-[oklch(0.7_0.01_260)]'
                }`}
              >
                {row.useCase}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
