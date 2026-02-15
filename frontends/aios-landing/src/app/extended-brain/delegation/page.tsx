import type { Metadata } from 'next'
import {
  ArticleLayout,
  Section,
  P,
  Highlight,
  Accent,
  CalloutBlock,
  CodeBlock,
  ComparisonBlock,
  ClosingLine,
} from '@/components/extended-brain/ArticleLayout'

export const metadata: Metadata = {
  title: 'Delegation, Not Instruction | Extended Brain | aios',
  description:
    'Did you instruct it, or did you delegate to it? The difference defines the result.',
  openGraph: {
    title: 'Delegation, Not Instruction | Extended Brain | aios',
    description:
      'Did you instruct it, or did you delegate to it? The difference defines the result.',
    url: 'https://fluxtopus.com/extended-brain/delegation',
    siteName: 'aios',
    images: [
      {
        url: '/social.png',
        width: 1200,
        height: 630,
        alt: 'Delegation, Not Instruction - aios Extended Brain',
      },
    ],
    locale: 'en_US',
    type: 'article',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Delegation, Not Instruction | Extended Brain | aios',
    description:
      'Did you instruct it, or did you delegate to it? The difference defines the result.',
    images: ['/social.png'],
    creator: '@jvivas_official',
  },
}

export default function DelegationPage() {
  return (
    <ArticleLayout
      title="Delegation, Not Instruction"
      hook="Did you instruct it, or did you delegate to it?"
      ctaText="Start delegating to your AI orchestra."
    >
      <Section title="Stop Micromanaging Your AI">
        <P>
          Most people treat AI like a fast typist. They give it step-by-step
          checklists. Do this. Then this. Then this. Check this condition. Format
          it like that.
        </P>
        <P>
          <Accent>That&apos;s wasting it.</Accent>
        </P>
        <P>
          You hired an employee who can think, and you&apos;re giving them a
          coloring book. AI agents can reason, adapt, and make decisions. But
          only if you let them. Step-by-step instructions strip out everything
          that makes agents useful and reduce them to the scripts you were trying
          to escape.
        </P>
      </Section>

      <Section title="What Delegation Actually Is">
        <P>
          Delegation is the transfer of authority and responsibility for a
          defined outcome. You specify what success looks like, provide relevant
          constraints, share necessary context, and step back.
        </P>
        <ComparisonBlock
          oldLabel="Instruction"
          oldText="Open file customers.csv. Read each line. Check if the email column contains '@company.com'. If yes, add to list A. If no, add to list B. Save list A as internal.csv. Save list B as external.csv."
          newLabel="Delegation"
          newText="Find all customer emails from last month's support tickets and separate internal team members from external customers."
        />
        <P>
          <Highlight>
            Instruction tells the agent what to do at every step. Delegation
            tells the agent what you need.
          </Highlight>{' '}
          The first constrains. The second empowers.
        </P>
        <P>
          With instruction, if the file format changes, everything breaks. With
          delegation, the agent adapts because it understands the goal, not just
          the steps.
        </P>
      </Section>

      <Section title="The Formula">
        <CodeBlock>
{`outcome + context + constraints = delegation

  outcome:     what success looks like
  context:     what's relevant to the task
  constraints: the boundaries and guardrails`}
        </CodeBlock>
        <P>
          <Highlight>Outcome</Highlight> is the clearest part. What does done
          look like? Not how to get there. What the finish line looks like.
        </P>
        <P>
          <Highlight>Context</Highlight> is what the agent needs to know that
          isn&apos;t obvious. Background information, previous decisions, domain
          knowledge, preferences. The things you&apos;d tell a new team member
          on their first day.
        </P>
        <P>
          <Highlight>Constraints</Highlight> are the guardrails that build
          trust. What shouldn&apos;t happen. What requires approval. What the
          limits are. Constraints aren&apos;t about limiting the agent — they&apos;re
          about defining the space where you trust it to operate.
        </P>
      </Section>

      <Section title="Feel the Difference">
        <P>
          You describe what you need. The AI takes an unexpected path — one you
          didn&apos;t anticipate — and it works. Better than your instructions
          would have produced.
        </P>
        <CalloutBlock>
          You asked it to summarize Q3 customer feedback. It found sentiment
          patterns you hadn&apos;t noticed. It flagged three accounts showing
          early churn risk signals. It drafted personalized responses for each
          one. You asked for a summary. It delivered insight.
        </CalloutBlock>
        <P>
          That&apos;s what happens when you delegate instead of instruct. The
          agent brings capabilities you didn&apos;t know to ask for. It connects
          dots you didn&apos;t see. It goes beyond the literal request to serve
          the actual intent.
        </P>
        <P>
          <Accent>
            Instructions get you exactly what you asked for. Delegation gets
            you what you actually needed.
          </Accent>
        </P>
      </Section>

      <ClosingLine>
        Tell machines what to do. Tell intelligence what you need.
      </ClosingLine>
    </ArticleLayout>
  )
}
