import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: 'Extended Brain | aios',
  description: 'A new way to think about automation — not as programming, but as delegation to your AI orchestra.',
  openGraph: {
    title: 'Extended Brain | aios',
    description: 'A new way to think about automation — not as programming, but as delegation to your AI orchestra.',
    url: 'https://fluxtopus.com/extended-brain',
    siteName: 'aios',
    images: [{ url: '/social.png', width: 1200, height: 630, alt: 'aios Extended Brain' }],
    locale: 'en_US',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Extended Brain | aios',
    description: 'A new way to think about automation — not as programming, but as delegation to your AI orchestra.',
    images: ['/social.png'],
    creator: '@jvivas_official',
  },
}

const coreArticles = [
  {
    title: 'Your AI Orchestra',
    hook: "You don't need to learn automation. You already know how to delegate.",
    slug: 'ai-orchestra',
    badge: 'START HERE',
  },
  {
    title: 'Describe It. Watch It Work.',
    hook: "There's a difference between hoping something works and knowing it works.",
    slug: 'describe-watch-work',
  },
  {
    title: "Describe, Don't Program",
    hook: "The hardest part of automation isn't technical. It's learning to describe what you actually want.",
    slug: 'describe-dont-program',
  },
  {
    title: 'The Case for Agency',
    hook: "Scripts follow instructions. Agents make decisions. The difference isn't technical.",
    slug: 'agency',
  },
  {
    title: 'Delegation, Not Instruction',
    hook: "Did you instruct it, or did you delegate to it?",
    slug: 'delegation',
  },
  {
    title: 'The Trust Layer',
    hook: 'If your auth layer can\'t answer "who did what and were they allowed to?" — you have a liability, not a product.',
    slug: 'trust-layer',
  },
]

const archiveArticles = [
  {
    title: 'The Automation Paradox',
    hook: 'Why the most valuable automation is observable, not invisible.',
    slug: 'automation-paradox',
  },
  {
    title: 'The Smallest Workflow That Ships',
    hook: 'Ship a 3-step workflow now, not a 12-step masterpiece never.',
    slug: 'smallest-workflow',
  },
  {
    title: 'Your AI Employees',
    hook: 'Think of agents as employees with jobs, not scripts that run.',
    slug: 'ai-employees',
  },
]

export default function ExtendedBrainPage() {
  return (
    <main className="min-h-screen bg-[#0b0d10] text-[#728c96] font-mono text-sm selection:bg-[#3b6e75] selection:text-white">
      <div className="max-w-3xl mx-auto px-6 py-16 md:py-24">

        {/* Back to home */}
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-[#485a62] hover:text-[#3b6e75] transition-colors mb-12 text-xs uppercase tracking-wider"
        >
          <span>&lt;</span> AIOS
        </Link>

        {/* Header */}
        <div className="mb-16 border border-[#1b2b34] p-6">
          <div className="flex gap-4 border-b border-[#1b2b34] pb-4 mb-6">
            <span className="text-[#3b6e75] font-bold">EXTENDED BRAIN</span>
            <span className="text-[#2d4f56] animate-pulse">● LOADED</span>
          </div>
          <h1 className="text-2xl md:text-3xl text-[#a8b8bf] font-bold mb-4">
            Describe it.{' '}
            <span className="text-[#3b6e75]">Watch it work.</span>
          </h1>
          <p className="text-[#5a6f7a] leading-relaxed">
            A new way to think about automation — not as programming,
            but as delegation to your AI orchestra.
          </p>
        </div>

        {/* Core Articles */}
        <div className="mb-16">
          <p className="text-[#3b6e75] text-xs uppercase tracking-wider mb-2">
            THE CORE IDEAS
          </p>
          <p className="text-[#485a62] mb-8 text-xs">
            Read these in order for the complete mental model shift.
          </p>

          <div className="space-y-4">
            {coreArticles.map((article, i) => (
              <Link
                key={article.slug}
                href={`/extended-brain/${article.slug}`}
                className="group block border border-[#1b2b34] hover:border-[#3b6e75]/50 transition-all duration-300 p-5"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-[#485a62] text-xs">
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      {article.badge && (
                        <span className="text-[#3b6e75] text-xs border border-[#3b6e75]/30 px-2 py-0.5">
                          {article.badge}
                        </span>
                      )}
                    </div>
                    <h3 className="text-[#a8b8bf] group-hover:text-[#3b6e75] transition-colors font-bold text-base mb-1">
                      {article.title}
                    </h3>
                    <p className="text-[#5a6f7a] text-sm">
                      {article.hook}
                    </p>
                  </div>
                  <span className="text-[#485a62] group-hover:text-[#3b6e75] group-hover:translate-x-1 transition-all mt-6 shrink-0">
                    &gt;
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </div>

        {/* Archive Articles */}
        <div className="border-t border-[#1b2b34] pt-12">
          <p className="text-[#485a62] text-xs uppercase tracking-wider mb-2">
            EARLIER THINKING
          </p>
          <p className="text-[#2d4f56] mb-8 text-xs">
            Previous articles exploring similar ideas.
          </p>

          <div className="space-y-3">
            {archiveArticles.map((article) => (
              <Link
                key={article.slug}
                href={`/extended-brain/${article.slug}`}
                className="group flex items-center justify-between py-3 border-b border-[#1b2b34]/50 hover:border-[#3b6e75]/30 transition-colors"
              >
                <div>
                  <h3 className="text-[#728c96] group-hover:text-[#3b6e75] transition-colors text-sm">
                    {article.title}
                  </h3>
                  <p className="text-[#485a62] text-xs mt-0.5">
                    {article.hook}
                  </p>
                </div>
                <span className="text-[#485a62] group-hover:text-[#3b6e75] ml-4 shrink-0">
                  &gt;
                </span>
              </Link>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="mt-16 pt-8 border-t border-[#1b2b34] flex justify-between text-[#485a62] text-xs">
          <Link href="/" className="hover:text-[#3b6e75] transition-colors">
            &lt; AIOS
          </Link>
          <Link href="/automate-your-business" className="hover:text-[#3b6e75] transition-colors">
            AUTOMATE YOUR BUSINESS &gt;
          </Link>
        </div>
      </div>
    </main>
  )
}
