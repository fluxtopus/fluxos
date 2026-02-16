import type { Metadata } from 'next'
import {
  ArticleLayout,
  Section,
  P,
  Highlight,
  Accent,
  ComparisonBlock,
  ClosingLine,
} from '@/components/extended-brain/ArticleLayout'

export const metadata: Metadata = {
  title: 'Your AI Orchestra | Extended Brain | fluxos',
  description:
    "You don't need to learn automation. You already know how to delegate.",
  openGraph: {
    title: 'Your AI Orchestra | Extended Brain | fluxos',
    description:
      "You don't need to learn automation. You already know how to delegate.",
    url: 'https://fluxtopus.com/extended-brain/ai-orchestra',
    siteName: 'fluxos',
    images: [
      {
        url: '/social.png',
        width: 1200,
        height: 630,
        alt: 'Your AI Orchestra - fluxos Extended Brain',
      },
    ],
    locale: 'en_US',
    type: 'article',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Your AI Orchestra | Extended Brain | fluxos',
    description:
      "You don't need to learn automation. You already know how to delegate.",
    images: ['/social.png'],
    creator: '@jvivas_official',
  },
}

export default function AiOrchestraPage() {
  return (
    <ArticleLayout
      title="Your AI Orchestra"
      hook="You don't need to learn automation. You already know how to delegate."
      ctaText="Describe what you need. Watch your orchestra perform."
    >
      <Section title="The Composer Doesn't Play Every Instrument">
        <P>
          A composer writes the score. They describe how the music should sound,
          which instruments carry the melody, where the crescendo builds, and
          when silence speaks louder than sound.{' '}
          <Highlight>They never pick up every instrument and play it
          themselves.</Highlight>
        </P>
        <P>
          The same principle applies to getting work done with AI. You already
          know how to describe what you want. You do it every time you delegate
          to a colleague, brief a freelancer, or explain a task to a new hire.
        </P>
        <P>
          But automation never worked like that.{' '}
          <Accent>For too long, automation meant programming.</Accent> It meant
          thinking in steps, conditions, loops, and error handling. It meant
          becoming a developer just to avoid doing repetitive work. That barrier
          kept most people out.
        </P>
        <P>
          The barrier was never about capability. It was about the interface.
          Automation tools asked you to think like a machine when you already
          knew how to think like a leader.
        </P>
      </Section>

      <Section title="What Delegation Actually Looks Like">
        <P>
          The shift is subtle but profound. Instead of describing{' '}
          <Highlight>how</Highlight> to do something, you describe{' '}
          <Highlight>what</Highlight> you want done. The AI figures out the how.
        </P>
        <ComparisonBlock
          oldLabel="Old Way (Programming)"
          oldText="Open browser. Navigate to URL. Find element with class 'search-input'. Type query string. Wait for results. Parse HTML response. Extract text from first 10 results. Save to CSV file at path..."
          newLabel="New Way (Delegation)"
          newText="Research the top competitors in our space and summarize what they launched this quarter."
        />
        <ComparisonBlock
          oldLabel="Old Way (Programming)"
          oldText="Connect to email API. Filter messages by date range. For each message, extract sender, subject, body. Run sentiment analysis function. Group by category. Generate report object..."
          newLabel="New Way (Delegation)"
          newText="Go through last week's customer emails and tell me what people are happy about and what's frustrating them."
        />
        <P>
          Same outcomes. Completely different cognitive load. One requires you to
          think like a machine. The other requires you to think like yourself.
        </P>
      </Section>

      <Section title="Your First Performance">
        <P>
          The first time you describe a workflow in plain language and watch it
          execute, something clicks. It feels less like using a tool and more
          like briefing a team.
        </P>
        <P>
          <Highlight>
            You don&apos;t need to be more technical. You need to be more clear.
          </Highlight>
        </P>
        <P>
          Clarity is a skill you already have. You use it in every email, every
          Slack message, every meeting where you explain what needs to happen.
          The difference is that now, clarity is enough. You don&apos;t need to
          translate your clarity into code. You just need to say what you mean.
        </P>
        <P>
          Your AI orchestra doesn&apos;t need sheet music written in a
          programming language. It needs a composer who knows what the music
          should sound like.
        </P>
      </Section>

      <Section title="This Changes How You Think About Work">
        <P>
          Once you internalize this, every repetitive task in your day starts
          looking different. That weekly report you assemble manually. Those
          competitor updates you research by hand. The data you copy between
          systems.
        </P>
        <P>
          <Accent>
            Each one becomes a potential delegation.
          </Accent>
        </P>
        <P>
          The question stops being &quot;what can I automate?&quot; and becomes{' '}
          <Highlight>&quot;what do I want done?&quot;</Highlight> That&apos;s a
          fundamentally different question. The first one puts the burden on your
          technical ability. The second puts the burden on your clarity of
          thought.
        </P>
        <P>
          And clarity of thought is something you can always improve, no
          programming required.
        </P>
      </Section>

      <ClosingLine>
        Describe the music. Watch your orchestra perform.
      </ClosingLine>
    </ArticleLayout>
  )
}
