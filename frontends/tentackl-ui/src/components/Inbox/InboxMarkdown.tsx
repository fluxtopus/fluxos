'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface InboxMarkdownProps {
  content: string;
}

/**
 * Lightweight markdown renderer for inbox messages.
 * Uses CSS variables for theming (no ExtendedBrain theme dependency).
 */
export function InboxMarkdown({ content }: InboxMarkdownProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        a: ({ href, children }) => (
          <a
            href={href}
            className="text-[var(--accent)] underline underline-offset-2 hover:opacity-80"
            target={href?.startsWith('http') ? '_blank' : undefined}
            rel={href?.startsWith('http') ? 'noopener noreferrer' : undefined}
          >
            {children}
          </a>
        ),
        ul: ({ children }) => <ul className="list-disc list-inside my-2 space-y-1">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal list-inside my-2 space-y-1">{children}</ol>,
        li: ({ children }) => <li>{children}</li>,
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-[var(--accent)]/40 pl-3 my-2 text-[var(--muted-foreground)]">
            {children}
          </blockquote>
        ),
        code: ({ className, children, ...props }) => {
          const isInline = !className;
          if (isInline) {
            return (
              <code
                className="px-1 py-0.5 rounded text-xs font-mono bg-[var(--muted)] text-[var(--foreground)]"
                {...props}
              >
                {children}
              </code>
            );
          }
          return (
            <code
              className="block p-3 rounded-lg overflow-x-auto text-xs font-mono bg-[var(--muted)] text-[var(--foreground)]"
              {...props}
            >
              {children}
            </code>
          );
        },
        pre: ({ children }) => (
          <pre className="my-2 rounded-lg overflow-hidden bg-[var(--muted)]">{children}</pre>
        ),
        hr: () => <hr className="my-3 border-t border-[var(--border)]" />,
        h1: ({ children }) => <h1 className="text-base font-bold mb-2 mt-3">{children}</h1>,
        h2: ({ children }) => <h2 className="text-base font-bold mb-2 mt-3">{children}</h2>,
        h3: ({ children }) => <h3 className="text-sm font-semibold mb-1.5 mt-2">{children}</h3>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
