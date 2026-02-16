import Link from 'next/link'

interface ArticleLayoutProps {
  title: string
  hook: string
  children: React.ReactNode
  ctaText?: string
}

export function ArticleLayout({
  title,
  hook,
  children,
  ctaText = 'See this in action',
}: ArticleLayoutProps) {
  return (
    <main className="min-h-screen bg-[#0b0d10] text-[#728c96] font-mono text-sm selection:bg-[#3b6e75] selection:text-white">
      <div className="max-w-3xl mx-auto px-6 py-16 md:py-24">

        {/* Back */}
        <Link
          href="/extended-brain"
          className="inline-flex items-center gap-2 text-[#485a62] hover:text-[#3b6e75] transition-colors mb-12 text-xs uppercase tracking-wider"
        >
          <span>&lt;</span> EXTENDED BRAIN
        </Link>

        {/* Hero */}
        <header className="mb-16 border border-[#1b2b34] p-6">
          <div className="flex gap-4 border-b border-[#1b2b34] pb-4 mb-6">
            <span className="text-[#3b6e75] font-bold">ARTICLE</span>
            <span className="text-[#2d4f56] animate-pulse">● READING</span>
          </div>
          <h1 className="text-2xl md:text-3xl text-[#a8b8bf] font-bold mb-4 leading-tight">
            {title}
          </h1>
          <p className="text-[#3b6e75] leading-relaxed">
            {hook}
          </p>
        </header>

        {/* Body */}
        <article className="space-y-12">
          {children}
        </article>

        {/* Signature */}
        <div className="mt-16 text-right">
          <span className="text-[#3b6e75] text-sm tracking-wider">— JV</span>
        </div>

        {/* CTA */}
        <div className="mt-8 pt-8 border-t border-[#1b2b34] text-center">
          <p className="text-[#5a6f7a] mb-4">{ctaText}</p>
          <Link
            href="/automate-your-business"
            className="inline-block border border-[#3b6e75] text-[#a8b8bf] py-2 px-6 text-xs uppercase tracking-wider hover:bg-[#3b6e75]/20 hover:border-[#a8b8bf]/40 transition-all"
          >
            Try It &gt;
          </Link>
        </div>

        {/* Footer nav */}
        <div className="mt-12 pt-8 border-t border-[#1b2b34] flex justify-between text-[#485a62] text-xs">
          <Link href="/extended-brain" className="hover:text-[#3b6e75] transition-colors">
            &lt; ALL ARTICLES
          </Link>
          <Link href="/" className="hover:text-[#3b6e75] transition-colors">
            FluxOS &gt;
          </Link>
        </div>
      </div>
    </main>
  )
}

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-lg md:text-xl text-[#a8b8bf] font-bold mb-4">{title}</h2>
      <div className="space-y-4">{children}</div>
    </section>
  )
}

export function P({ children }: { children: React.ReactNode }) {
  return <p className="text-[#728c96] leading-relaxed">{children}</p>
}

export function Highlight({ children }: { children: React.ReactNode }) {
  return <span className="text-[#a8b8bf]">{children}</span>
}

export function Accent({ children }: { children: React.ReactNode }) {
  return <span className="text-[#3b6e75]">{children}</span>
}

export function CalloutBlock({ children }: { children: React.ReactNode }) {
  return (
    <div className="border-l-2 border-[#3b6e75] pl-4 py-2 my-4 text-[#5a6f7a] italic">
      {children}
    </div>
  )
}

export function CodeBlock({ children }: { children: React.ReactNode }) {
  return (
    <div className="border border-[#1b2b34] bg-[#0d1117] p-4 my-4 text-[#728c96] overflow-x-auto">
      <pre className="text-xs">{children}</pre>
    </div>
  )
}

export function ComparisonBlock({
  oldLabel,
  oldText,
  newLabel,
  newText,
}: {
  oldLabel: string
  oldText: string
  newLabel: string
  newText: string
}) {
  return (
    <div className="border border-[#1b2b34] my-4">
      <div className="p-4 border-b border-[#1b2b34]">
        <p className="text-[#485a62] text-xs uppercase tracking-wider mb-1">{oldLabel}</p>
        <p className="text-[#5a6f7a] italic">"{oldText}"</p>
      </div>
      <div className="p-4 bg-[#0d1117]">
        <p className="text-[#3b6e75] text-xs uppercase tracking-wider mb-1">{newLabel}</p>
        <p className="text-[#a8b8bf]">"{newText}"</p>
      </div>
    </div>
  )
}

export function ClosingLine({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[#3b6e75] text-base font-bold mt-8">{children}</p>
  )
}
