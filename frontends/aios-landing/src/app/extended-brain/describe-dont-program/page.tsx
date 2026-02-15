import type { Metadata } from 'next'
import {
  ArticleLayout,
  Section,
  P,
  Highlight,
  Accent,
  ComparisonBlock,
  CodeBlock,
  ClosingLine,
} from '@/components/extended-brain/ArticleLayout'

export const metadata: Metadata = {
  title: "Describe, Don't Program | Extended Brain | aios",
  description:
    "The hardest part of automation isn't technical. It's learning to describe what you actually want.",
  openGraph: {
    title: "Describe, Don't Program | Extended Brain | aios",
    description:
      "The hardest part of automation isn't technical. It's learning to describe what you actually want.",
    url: 'https://fluxtopus.com/extended-brain/describe-dont-program',
    siteName: 'aios',
    images: [
      {
        url: '/social.png',
        width: 1200,
        height: 630,
        alt: "Describe, Don't Program - aios Extended Brain",
      },
    ],
    locale: 'en_US',
    type: 'article',
  },
  twitter: {
    card: 'summary_large_image',
    title: "Describe, Don't Program | Extended Brain | aios",
    description:
      "The hardest part of automation isn't technical. It's learning to describe what you actually want.",
    images: ['/social.png'],
    creator: '@jvivas_official',
  },
}

export default function DescribeDontProgramPage() {
  return (
    <ArticleLayout
      title="Describe, Don't Program"
      hook="The hardest part of automation isn't technical. It's learning to describe what you actually want."
      ctaText="Describe your first workflow."
    >
      <Section title="The Old Way">
        <P>
          Automation used to mean programming. Not always in the traditional
          sense — you didn&apos;t always need to write Python or JavaScript —
          but you still had to think like a machine.
        </P>
        <P>
          Break this task into atomic steps. Define every condition. Handle every
          edge case. Specify the exact sequence. If this, then that. If not,
          then something else. On error, retry. On timeout, fallback.
        </P>
        <P>
          <Highlight>
            It demanded technical thinking from people who weren&apos;t
            technical.
          </Highlight>{' '}
          And even for those who were, it was tedious. The mental overhead of
          translating human intent into machine instructions was the real cost of
          automation. Not the tools. Not the platforms. The translation.
        </P>
      </Section>

      <Section title="The New Way">
        <P>
          AI agents don&apos;t need step-by-step instructions. They need to
          understand what you want. The skill has shifted from{' '}
          <Accent>&quot;program a solution&quot;</Accent> to{' '}
          <Accent>&quot;describe what you want.&quot;</Accent>
        </P>
        <P>
          That sounds trivial. It isn&apos;t. Most people have spent years
          learning to think in steps and procedures because that&apos;s what
          tools demanded. Unlearning that takes practice.
        </P>
        <P>
          <Highlight>
            The technical barrier is gone. The clarity barrier remains.
          </Highlight>{' '}
          The question is no longer &quot;can I build this?&quot; but &quot;can
          I describe this clearly enough?&quot;
        </P>
      </Section>

      <Section title="The Art of Clear Description">
        <P>
          Three principles separate vague descriptions from actionable ones.
        </P>
        <P>
          <Highlight>1. Outcome Over Process</Highlight>
        </P>
        <ComparisonBlock
          oldLabel="Process-Focused"
          oldText="Open the spreadsheet, go to column B, filter by date, copy the values, paste them into a new sheet, sort descending..."
          newLabel="Outcome-Focused"
          newText="Show me this month's top-performing products ranked by revenue."
        />
        <P>
          <Highlight>2. Context Over Assumptions</Highlight>
        </P>
        <ComparisonBlock
          oldLabel="Assumes Knowledge"
          oldText="Summarize the feedback."
          newLabel="Provides Context"
          newText="Summarize last quarter's customer feedback from our support tickets. We're looking for patterns in feature requests and recurring complaints."
        />
        <P>
          <Highlight>3. Intent Over Mechanics</Highlight>
        </P>
        <ComparisonBlock
          oldLabel="Mechanical"
          oldText="Send an email to each person on the list with their name in the subject line and the template text in the body."
          newLabel="Intent-Driven"
          newText="Reach out to everyone who signed up last week with a personalized welcome that references what they showed interest in."
        />
      </Section>

      <Section title="Your First Description">
        <P>
          Here&apos;s a framework for your first workflow description. Answer
          three questions:
        </P>
        <P>
          <Highlight>What&apos;s the outcome?</Highlight> What does success look
          like when this is done?
        </P>
        <P>
          <Highlight>What&apos;s the context?</Highlight> What does the AI need
          to know to do this well?
        </P>
        <P>
          <Highlight>What does good look like?</Highlight> How would you know
          the result is actually useful?
        </P>
        <CodeBlock>
{`Example: Competitor Monitoring Workflow

Outcome:
  A weekly summary of what our top 3 competitors
  launched, changed, or announced.

Context:
  Competitors are [Company A], [Company B], [Company C].
  Check their blogs, changelogs, and social accounts.
  We care about product features, pricing changes,
  and major partnerships.

What good looks like:
  A brief, scannable summary I can share with the team
  in Monday's standup. Bullet points, not essays.
  Flag anything that directly competes with our roadmap.`}
        </CodeBlock>
        <P>
          No programming. No flowcharts. No conditional logic. Just a clear
          description of what you want, with enough context for an intelligent
          agent to figure out the rest.
        </P>
      </Section>

      <Section title="The Only Skill You Need">
        <P>
          Programming is learning a new language. Delegation is learning clarity.
          One of these you already practice every day.
        </P>
        <P>
          <Accent>
            AI raises the bar on clarity because it takes your words seriously.
          </Accent>{' '}
          A vague request to a colleague gets clarified through conversation. A
          vague request to an AI agent gets executed literally. The AI
          won&apos;t push back and ask what you really meant. It will do exactly
          what you described.
        </P>
        <P>
          That&apos;s not a limitation. It&apos;s an invitation to be precise.
          And precision in describing what you want is a skill that pays
          dividends far beyond automation.
        </P>
      </Section>

      <ClosingLine>The AI will handle the rest.</ClosingLine>
    </ArticleLayout>
  )
}
