import type { Metadata } from 'next'
import {
  ArticleLayout,
  Section,
  P,
  Highlight,
  Accent,
  CodeBlock,
  ClosingLine,
} from '@/components/extended-brain/ArticleLayout'

export const metadata: Metadata = {
  title: 'The Trust Layer | Extended Brain | fluxos',
  description:
    'If your auth layer can\'t answer "who did what and were they allowed to?" — you have a liability, not a product.',
  openGraph: {
    title: 'The Trust Layer | Extended Brain | fluxos',
    description:
      'If your auth layer can\'t answer "who did what and were they allowed to?" — you have a liability, not a product.',
    url: 'https://fluxtopus.com/extended-brain/trust-layer',
    siteName: 'fluxos',
    images: [
      {
        url: '/social.png',
        width: 1200,
        height: 630,
        alt: 'The Trust Layer - fluxos Extended Brain',
      },
    ],
    locale: 'en_US',
    type: 'article',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'The Trust Layer | Extended Brain | fluxos',
    description:
      'If your auth layer can\'t answer "who did what and were they allowed to?" — you have a liability, not a product.',
    images: ['/social.png'],
    creator: '@jvivas_official',
  },
}

export default function TrustLayerPage() {
  return (
    <ArticleLayout
      title="The Trust Layer"
      hook='If your auth layer can&apos;t answer "who did what and were they allowed to?" — you have a liability, not a product.'
      ctaText="See how InkPass secures your AI orchestra."
    >
      <Section title="The Question Nobody Asks Until It's Too Late">
        <P>
          Most platforms handle authentication the same way: a single API key,
          maybe a JWT if they&apos;re feeling ambitious, and a roles table that
          was designed for a dashboard, not an autonomous system.
        </P>
        <P>
          Then the questions start pouring in.{' '}
          <Highlight>Which agent accessed that data?</Highlight> Who approved
          that action? Who can see this customer&apos;s information? Can this
          agent create new agents? What happens if the auth service goes down?
        </P>
        <P>
          The answer, more often than not:{' '}
          <Accent>&quot;We don&apos;t know.&quot;</Accent>
        </P>
        <P>
          That&apos;s why I built InkPass. Not as an afterthought. Not as a
          feature. As an independent service with its own security boundary,
          designed from day one for systems where autonomous agents make
          decisions on behalf of humans.
        </P>
      </Section>

      <Section title="Not Adapted. Built.">
        <P>
          InkPass is not a login library repurposed for multi-agent systems.
          It&apos;s not an open-source auth tool with a few extra columns bolted
          on. It&apos;s an independent authentication and authorization service.
        </P>
        <P>
          <Highlight>
            Own service. Own database. Own API. Own security boundary.
          </Highlight>
        </P>
        <P>
          Every authentication decision flows through a single, auditable
          pipeline. Every permission check is evaluated against the same policy
          engine. Every action is traceable to a specific identity, whether
          that&apos;s a human user, an API integration, or an autonomous agent.
        </P>
      </Section>

      <Section title="Permissions That Actually Model Reality">
        <P>
          Roles work for simple systems. Admin, User, Viewer. Fine for a
          dashboard. Completely inadequate for a system where Agent A can read
          customer data but not modify it, Agent B can send emails but only to
          verified addresses, and Agent C can create new agents but only within
          its own workspace.
        </P>
        <P>
          InkPass uses attribute-based access control.{' '}
          <Accent>
            Resource + action + conditions.
          </Accent>{' '}
          Permissions model what actually happens in the real world, not what
          fits neatly into a roles table.
        </P>
        <CodeBlock>
{`Permission Check:

  identity:  agent:research-bot-7
  action:    read
  resource:  customer:feedback:q3-2024
  conditions:
    - organization: acme-corp
    - workspace: product-team
    - data_classification: internal

  result: ALLOW
  reason: agent has 'read' on 'customer:feedback:*'
          within 'product-team' workspace
  audit:  logged to immutable trail`}
        </CodeBlock>
        <P>
          Every check is explicit. Every decision is logged. Every permission
          maps to a real action in a real context.
        </P>
      </Section>

      <Section title="One Pipeline, Three Methods">
        <P>
          Authentication comes in three forms, but all produce the same
          permission context.
        </P>
        <P>
          <Highlight>Bearer Token (JWT)</Highlight> — for human users and
          interactive sessions. Cryptographically signed, short-lived, carrying
          identity claims that the permission engine evaluates.
        </P>
        <P>
          <Highlight>API Key (SHA-256)</Highlight> — for service-to-service
          communication and integrations. Hashed, never stored in plaintext,
          scoped to specific resources and actions.
        </P>
        <P>
          <Highlight>Webhook Signature (HMAC)</Highlight> — for inbound events
          from external systems. Verified against shared secrets, timestamped to
          prevent replay attacks.
        </P>
        <P>
          <Accent>
            Three entry points. One permission pipeline. No special cases.
          </Accent>{' '}
          Whether you authenticated with a JWT, an API key, or a webhook
          signature, the same policy engine evaluates your permissions the same
          way.
        </P>
      </Section>

      <Section title="Isolation Is Structural, Not a Filter">
        <P>
          Every entity in InkPass is scoped to an organization. Not by a WHERE
          clause in a query. Not by a middleware filter that hopefully catches
          everything.{' '}
          <Highlight>Structurally.</Highlight>
        </P>
        <P>
          Organization ID is part of every key, every path, every permission
          evaluation. You don&apos;t query across organizations and filter
          results. You physically cannot access data outside your boundary.
        </P>
        <P>
          This is the difference between a security policy and a security
          architecture. Policies can be misconfigured, bypassed, or forgotten.{' '}
          <Accent>
            Structural constraints are built into the system itself.
          </Accent>
        </P>
      </Section>

      <Section title="Fail-Safe by Default">
        <P>
          If InkPass is unreachable, the answer is <Highlight>deny</Highlight>.
        </P>
        <P>
          Not &quot;allow and log it.&quot; Not &quot;cache the last known
          permission and hope.&quot; Not &quot;retry indefinitely while the
          request hangs.&quot; Deny.
        </P>
        <P>
          <Accent>You can retry a denied request. You can&apos;t undo an
          unauthorized action.</Accent> Every fail-safe decision in InkPass
          follows this principle: when in doubt, protect the system. A brief
          interruption in service is always preferable to a breach in trust.
        </P>
      </Section>

      <Section title="The Bottom Line">
        <P>
          If you&apos;re building a system where AI agents act autonomously,
          your authentication layer isn&apos;t a feature — it&apos;s the
          foundation. It must answer three questions at all times:{' '}
          <Highlight>Who did this?</Highlight>{' '}
          <Highlight>What did they do?</Highlight>{' '}
          <Highlight>Were they allowed to?</Highlight>
        </P>
        <P>
          If your auth layer can&apos;t answer those questions definitively and
          immediately, you don&apos;t have a secure system. You have a system
          that hasn&apos;t been tested yet.
        </P>
      </Section>

      <ClosingLine>
        I&apos;d rather you figure it out now.
      </ClosingLine>
    </ArticleLayout>
  )
}
