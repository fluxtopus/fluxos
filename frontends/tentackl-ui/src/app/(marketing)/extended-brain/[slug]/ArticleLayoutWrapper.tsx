'use client';

import { ArticleLayout, MarkdownRenderer } from '@/components/ExtendedBrain';

interface ArticleLayoutWrapperProps {
  title: string;
  hook: string;
  body: string;
  ctaText?: string;
}

/**
 * Client component wrapper for ArticleLayout with markdown content
 * Separates server/client boundary for Next.js App Router
 */
export function ArticleLayoutWrapper({
  title,
  hook,
  body,
  ctaText,
}: ArticleLayoutWrapperProps) {
  return (
    <ArticleLayout
      title={title}
      hook={hook}
      ctaText={ctaText}
      defaultLightMode={true}
    >
      <MarkdownRenderer content={body} />
    </ArticleLayout>
  );
}
