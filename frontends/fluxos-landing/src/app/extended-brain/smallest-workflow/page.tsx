import type { Metadata } from 'next'
import {
  ArticleLayout,
  Section,
  P,
  Highlight,
  Accent,
  ClosingLine,
} from '@/components/extended-brain/ArticleLayout'

export const metadata: Metadata = {
  title: 'The Smallest Workflow That Ships | Extended Brain | fluxos',
  description:
    'Ship a 3-step workflow now, not a 12-step masterpiece never.',
  openGraph: {
    title: 'The Smallest Workflow That Ships | Extended Brain | fluxos',
    description:
      'Ship a 3-step workflow now, not a 12-step masterpiece never.',
    url: 'https://fluxtopus.com/extended-brain/smallest-workflow',
    siteName: 'fluxos',
    images: [
      {
        url: '/social.png',
        width: 1200,
        height: 630,
        alt: 'The Smallest Workflow That Ships - fluxos Extended Brain',
      },
    ],
    locale: 'en_US',
    type: 'article',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'The Smallest Workflow That Ships | Extended Brain | fluxos',
    description:
      'Ship a 3-step workflow now, not a 12-step masterpiece never.',
    images: ['/social.png'],
    creator: '@jvivas_official',
  },
}

export default function SmallestWorkflowPage() {
  return (
    <ArticleLayout
      title="The Smallest Workflow That Ships"
      hook="Ship a 3-step workflow now, not a 12-step masterpiece never."
      ctaText="Build your first workflow in 5 minutes."
    >
      <Section title="The Perfectionism Trap">
        <P>
          Everyone has a fantasy automation. The grand vision. A 12-step
          workflow that ingests data from five sources, runs analysis, generates
          reports, sends personalized emails, updates the CRM, and makes coffee.
        </P>
        <P>
          <Accent>It never gets built.</Accent>
        </P>
        <P>
          The gap between where you are and the perfect automation feels too
          large to cross. So you wait. You plan. You research. You compare
          platforms. And the task you wanted to automate keeps eating 15 minutes
          of your day, every day, while you dream about the perfect solution.
        </P>
        <P>
          Meanwhile, the people actually saving time with automation are
          automating one thing at a time.{' '}
          <Highlight>
            Not the grand vision. The next annoying task.
          </Highlight>
        </P>
      </Section>

      <Section title="Minimum Viable Workflow">
        <P>
          Find one task that takes you 15 minutes and you do it at least weekly.
          Not your most complex process. Not your most important workflow. Just
          one repetitive, tedious, predictable task.
        </P>
        <P>
          <Highlight>
            It won&apos;t be glamorous. That&apos;s the point.
          </Highlight>
        </P>
        <P>
          Summarizing customer feedback from a spreadsheet. Researching a
          competitor&apos;s latest blog posts. Formatting raw data into a
          weekly report. Compiling updates from three different tools into one
          Slack message.
        </P>
        <P>
          These aren&apos;t exciting workflows. They&apos;re the ones that
          actually compound. Fifteen minutes saved this week is fifteen minutes
          saved every week. That&apos;s thirteen hours a year from one small
          workflow.
        </P>
      </Section>

      <Section title="The Compound Effect">
        <P>
          Each workflow you build teaches you something. Your first one will feel
          awkward. You&apos;ll over-describe some parts and under-describe
          others. The result will be imperfect.{' '}
          <Accent>That&apos;s fine.</Accent>
        </P>
        <P>
          Your second workflow will be faster. You&apos;ll know what level of
          detail to provide. You&apos;ll understand how agents interpret your
          descriptions. The result will be better.
        </P>
        <P>
          By your fifth workflow, you&apos;ll be seeing patterns. You&apos;ll
          know which tasks automate well and which need more structure.
          You&apos;ll have a library of working workflows you can reference and
          remix.
        </P>
        <P>
          <Highlight>
            That first small workflow isn&apos;t just saving time. It&apos;s an
            investment in your ability to automate everything that follows.
          </Highlight>
        </P>
      </Section>

      <Section title="Permission to Ship Imperfect">
        <P>
          The 80% solution that&apos;s running right now is infinitely more
          valuable than the 100% solution that&apos;s still being planned.
        </P>
        <P>
          Your first workflow doesn&apos;t need to handle every edge case. It
          doesn&apos;t need to be elegant. It doesn&apos;t need to impress
          anyone. It needs to{' '}
          <Highlight>save you time this week</Highlight>.
        </P>
        <P>
          <Accent>
            Most production systems you admire started as something imperfect
            that shipped.
          </Accent>{' '}
          They got better over time because they existed. The ones that stayed
          in the planning phase forever contributed nothing. Done beats perfect
          when perfect means never.
        </P>
      </Section>

      <Section title="Starting Points, Not Endpoints">
        <P>
          Think of your first workflow as week one of a progression:
        </P>
        <P>
          <Highlight>Week 1:</Highlight> Build the basic workflow. Watch it run.
          Note what works and what doesn&apos;t.
        </P>
        <P>
          <Highlight>Week 2:</Highlight> Adjust based on what you observed. Fix
          the obvious gaps. Improve the description where the agent
          misunderstood.
        </P>
        <P>
          <Highlight>Week 3:</Highlight> Extend it. Add a step. Incorporate a
          new data source. Make the output more useful.
        </P>
        <P>
          <Highlight>Week 4:</Highlight> Decide: is this good enough to keep
          running, or is it time to start the next workflow?
        </P>
        <P>
          Either answer is fine. The point is that you&apos;re iterating on
          something real, not planning something theoretical.{' '}
          <Accent>
            Every workflow is a starting point, not an endpoint.
          </Accent>
        </P>
      </Section>
    </ArticleLayout>
  )
}
