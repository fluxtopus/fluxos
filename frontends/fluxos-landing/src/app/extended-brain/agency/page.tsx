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
  title: 'The Case for Agency | Extended Brain | fluxos',
  description:
    'Scripts follow instructions. Agents make decisions. The difference changes everything.',
  openGraph: {
    title: 'The Case for Agency | Extended Brain | fluxos',
    description:
      'Scripts follow instructions. Agents make decisions. The difference changes everything.',
    url: 'https://fluxtopus.com/extended-brain/agency',
    siteName: 'fluxos',
    images: [
      {
        url: '/social.png',
        width: 1200,
        height: 630,
        alt: 'The Case for Agency - fluxos Extended Brain',
      },
    ],
    locale: 'en_US',
    type: 'article',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'The Case for Agency | Extended Brain | fluxos',
    description:
      'Scripts follow instructions. Agents make decisions. The difference changes everything.',
    images: ['/social.png'],
    creator: '@jvivas_official',
  },
}

export default function AgencyPage() {
  return (
    <ArticleLayout
      title="The Case for Agency"
      hook="Scripts follow instructions. Agents make decisions."
      ctaText="Build workflows with real agency."
    >
      <Section title="Scripts Are Stupid">
        <P>
          That&apos;s not an insult. It&apos;s a description. Scripted
          automation is deterministic, rigid, and brittle.{' '}
          <Highlight>
            It does exactly what you told it to do, which is the problem.
          </Highlight>
        </P>
        <P>
          A customer asks an unexpected question. The script doesn&apos;t know
          what to do. It either fails silently, gives a wrong answer, or loops
          back to the beginning. There&apos;s no reasoning, no judgment, no
          adaptation. Just instructions running until they can&apos;t.
        </P>
        <CalloutBlock>
          Customer: &quot;I want to return this, but I also want to exchange it
          for the blue version if it&apos;s in stock, otherwise just refund
          me.&quot;
          <br /><br />
          Script: &quot;Would you like to return or exchange?&quot;
          <br /><br />
          Agent: &quot;Let me check if the blue version is available. If it is,
          I&apos;ll set up the exchange. If not, I&apos;ll process your refund
          right away.&quot;
        </CalloutBlock>
        <P>
          The script can&apos;t handle nuance. The agent can.{' '}
          <Accent>
            Scripted automation is a dead end for anything that involves
            judgment.
          </Accent>
        </P>
      </Section>

      <Section title="What Agency Actually Means">
        <P>
          Agency is the capacity to make decisions within boundaries. Not
          unlimited freedom. Not rigid instructions. Something in between.
        </P>
        <P>
          An agent with agency can evaluate a situation, choose an approach,
          adjust when something unexpected happens, and still stay within the
          guardrails you defined.
        </P>
        <ComparisonBlock
          oldLabel="Script"
          oldText="If customer says 'return', open return form. If customer says 'exchange', open exchange form. If customer says anything else, say 'I don't understand.'"
          newLabel="Agent"
          newText="Understand what the customer needs and help them get there. You can process returns, exchanges, and refunds. Escalate to a human if the request is outside these boundaries."
        />
        <P>
          <Highlight>
            The script encodes specific responses. The agent understands
            intent.
          </Highlight>{' '}
          One breaks when reality deviates from the script. The other adapts.
        </P>
      </Section>

      <Section title="Bounded Autonomy">
        <P>
          Agency without boundaries is chaos. Boundaries without agency is a
          script. The sweet spot is{' '}
          <Accent>bounded autonomy</Accent> — freedom to decide within a defined
          space.
        </P>
        <P>
          Think of boundaries as context, not restrictions. They tell the agent
          what matters, what&apos;s off-limits, and when to ask for help.
        </P>
        <CodeBlock>
{`Bounded Autonomy:

  > Clear outcomes, flexible methods
  > Known escalation points
  > Transparent reasoning
  > Defined resource limits`}
        </CodeBlock>
        <P>
          An agent with bounded autonomy knows what success looks like, has
          freedom in how to get there, knows when to stop and ask, and can
          explain why it made the choices it did.
        </P>
        <P>
          This is how good management works with people, too. You don&apos;t
          tell a senior employee every step. You tell them the goal, the
          constraints, and when to loop you in.
        </P>
      </Section>

      <Section title="Make the Shift">
        <P>
          <Highlight>Stop writing scripts. Start defining outcomes.</Highlight>{' '}
          Stop encoding every possible response. Start describing what good
          looks like and letting the agent figure out how to get there.
        </P>
        <P>
          The shift from scripts to agents isn&apos;t just a technical upgrade.
          It&apos;s a fundamental change in how you think about automation. You
          stop being a programmer and start being a leader. You stop encoding
          the past and start enabling the future.
        </P>
      </Section>

      <ClosingLine>
        Scripts encode the past. Agents navigate the future.
      </ClosingLine>
    </ArticleLayout>
  )
}
