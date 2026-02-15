import { Metadata } from 'next';
import { getExtendedBrainArticlesByCategory } from '@/services/contentService';
import { ExtendedBrainPageClient } from './ExtendedBrainPageClient';

export const metadata: Metadata = {
  title: 'Extended Brain | Tentackl',
  description: 'A new way to think about automation — not as programming, but as delegation to your AI orchestra.',
};

// Fallback articles if manifest isn't available
const fallbackCoreArticles = [
  {
    title: 'Your AI Orchestra',
    hook: "You don't need to learn automation. You already know how to delegate. Like a composer conducting a symphony, you describe the music you want — and your orchestra performs it.",
    slug: 'ai-orchestra',
    badge: 'Start Here',
  },
  {
    title: 'Describe It. Watch It Work.',
    hook: "The moment you watch your first workflow execute, something shifts. Not in the software — in you. There's a difference between hoping something works and knowing it works.",
    slug: 'describe-watch-work',
  },
  {
    title: "Describe, Don't Program",
    hook: "The hardest part of automation isn't technical. It's learning to describe what you actually want. The good news? You already know how.",
    slug: 'describe-dont-program',
  },
  {
    title: 'The Case for Agency',
    hook: "Scripts follow instructions. Agents make decisions. The difference isn't technical — it's the difference between automation that breaks and automation that adapts.",
    slug: 'agency',
  },
  {
    title: 'Delegation, Not Instruction',
    hook: "The difference between a struggling AI project and a thriving one often comes down to one thing: did you instruct it, or did you delegate to it?",
    slug: 'delegation',
  },
  {
    title: 'The Trust Layer',
    hook: 'Authentication is the hardest unsolved problem in multi-agent AI. If your auth layer can\'t answer "who did what and were they allowed to?" — you have a liability, not a product.',
    slug: 'trust-layer',
  },
];

const fallbackArchiveArticles = [
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
];

/**
 * Extended Brain index page - Server Component
 * Fetches article list from Den CDN manifest
 */
export default async function ExtendedBrainPage() {
  let coreArticles = fallbackCoreArticles;
  let archiveArticles = fallbackArchiveArticles;

  try {
    const articles = await getExtendedBrainArticlesByCategory();
    if (articles.core.length > 0) {
      coreArticles = articles.core.map(a => ({
        title: a.title,
        hook: a.hook,
        slug: a.slug,
        badge: a.badge,
      }));
    }
    if (articles.archive.length > 0) {
      archiveArticles = articles.archive.map(a => ({
        title: a.title,
        hook: a.hook,
        slug: a.slug,
        badge: a.badge,
      }));
    }
  } catch (error) {
    // Use fallback articles if manifest fetch fails
    console.warn('Using fallback extended brain articles:', error);
  }

  return (
    <ExtendedBrainPageClient
      coreArticles={coreArticles}
      archiveArticles={archiveArticles}
    />
  );
}
