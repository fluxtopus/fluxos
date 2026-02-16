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
  title: 'Your AI Employees | Extended Brain | fluxos',
  description:
    'Stop thinking about automation tools. Start thinking about AI employees.',
  openGraph: {
    title: 'Your AI Employees | Extended Brain | fluxos',
    description:
      'Stop thinking about automation tools. Start thinking about AI employees.',
    url: 'https://fluxtopus.com/extended-brain/ai-employees',
    siteName: 'fluxos',
    images: [
      {
        url: '/social.png',
        width: 1200,
        height: 630,
        alt: 'Your AI Employees - fluxos Extended Brain',
      },
    ],
    locale: 'en_US',
    type: 'article',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Your AI Employees | Extended Brain | fluxos',
    description:
      'Stop thinking about automation tools. Start thinking about AI employees.',
    images: ['/social.png'],
    creator: '@jvivas_official',
  },
}

export default function AiEmployeesPage() {
  return (
    <ArticleLayout
      title="Your AI Employees"
      hook="Stop thinking about automation tools. Start thinking about AI employees."
      ctaText="Describe what you need and watch your AI team build it."
    >
      <Section title="The Old Mental Model">
        <P>
          Automation used to mean scripts that run. You define the steps, the
          conditions, the logic, and the error handling. The machine executes
          exactly what you wrote, nothing more and nothing less.
        </P>
        <P>
          <Highlight>
            Exact execution sounds like a feature. It&apos;s actually a
            limitation.
          </Highlight>
        </P>
        <P>
          Scripts are brittle. Change the input format and they break. Add an
          edge case and they fail. Ask them to handle ambiguity and they freeze.
          They do precisely what you told them, which means they can only handle
          situations you anticipated.
        </P>
      </Section>

      <Section title="The New Mental Model">
        <P>
          Think about AI agents the way you think about employees.{' '}
          <Accent>
            You describe the outcome, and they figure out how to get there.
          </Accent>
        </P>
        <P>
          An employee doesn&apos;t need step-by-step instructions for every
          task. They need context, goals, and boundaries. They adapt when
          something unexpected happens. They ask questions when they&apos;re
          unsure. They bring their own skills and judgment to the work.
        </P>
        <P>
          AI agents work the same way. Give them a role, a goal, and the
          information they need. They&apos;ll figure out the approach, handle
          unexpected inputs, and produce results that match your intent — even
          when the specifics weren&apos;t scripted.
        </P>
      </Section>

      <Section title="The Org Chart Analogy">
        <P>
          A workflow isn&apos;t a flowchart anymore. It&apos;s an org chart.
        </P>
        <P>
          <Highlight>Research Agent</Highlight> — gathers information from
          specified sources. Knows how to search, filter, and extract relevant
          data. Passes findings to the next agent.
        </P>
        <P>
          <Highlight>Analysis Agent</Highlight> — takes raw research and
          identifies patterns, trends, and insights. Separates signal from
          noise. Highlights what matters.
        </P>
        <P>
          <Highlight>Writing Agent</Highlight> — takes analysis and produces
          clear, readable output. Knows your tone, your format preferences,
          your audience. Drafts something you&apos;d be comfortable sharing.
        </P>
        <P>
          <Highlight>Validator Agent</Highlight> — reviews the output for
          accuracy, completeness, and quality. Catches errors the writing agent
          missed. Ensures the final product meets your standards.
        </P>
        <P>
          <Accent>
            You&apos;re not designing a flowchart. You&apos;re designing which
            roles you need and how they collaborate.
          </Accent>{' '}
          Just like building a real team.
        </P>
      </Section>

      <Section title="Delegation Without Meetings">
        <P>
          Real teams have a coordination problem. Meetings, email chains, Slack
          threads, status updates. The work itself takes an hour. The
          coordination takes three.
        </P>
        <P>
          AI agents don&apos;t have this problem. They coordinate without
          meetings. They pass context seamlessly between each other. There are
          no email chains, no waiting for responses, no scheduling conflicts.{' '}
          <Highlight>Instant handoff, zero overhead.</Highlight>
        </P>
        <P>
          When the Research Agent finishes gathering data, the Analysis Agent
          picks it up immediately. No &quot;hey, I finished that thing, it&apos;s
          in the shared drive.&quot; No waiting until Monday&apos;s standup. The
          work flows continuously because the coordination is built into the
          system.
        </P>
      </Section>

      <Section title="Designing Outcomes, Not Steps">
        <P>
          When you hire a contractor to renovate your kitchen, you don&apos;t
          hand them a list of every hammer swing. You show them what you want
          the kitchen to look like.{' '}
          <Highlight>
            &quot;I want it to look like this&quot;
          </Highlight>{' '}
          not &quot;swing the hammer at this angle, 47 times, on this wall.&quot;
        </P>
        <P>
          The same principle applies to AI workflows.{' '}
          <Accent>
            &quot;Research our competitors and summarize what they shipped this
            quarter&quot;
          </Accent>{' '}
          not &quot;open browser, navigate to URL, find element with class name,
          extract text, save to file.&quot;
        </P>
        <P>
          The outcome is the same. The cognitive load is completely different.
          One requires you to think like a project manager. The other requires
          you to think like a programmer. And you already know which one you are.
        </P>
      </Section>

      <ClosingLine>
        Describe what you need and watch your AI team build it.
      </ClosingLine>
    </ArticleLayout>
  )
}
