import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getExtendedBrainArticles, getExtendedBrainArticle } from '@/services/contentService';
import { ArticleLayoutWrapper } from './ArticleLayoutWrapper';

interface PageProps {
  params: Promise<{ slug: string }>;
}

/**
 * Generate static params for SSG
 * This pre-renders all extended brain articles at build time
 */
export async function generateStaticParams() {
  try {
    const articles = await getExtendedBrainArticles();
    return articles.map((article) => ({
      slug: article.slug,
    }));
  } catch (error) {
    // If manifest isn't available yet, return empty array
    console.warn('Could not fetch extended brain articles for static generation:', error);
    return [];
  }
}

/**
 * Generate metadata for SEO
 */
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;

  try {
    const article = await getExtendedBrainArticle(slug);

    if (!article) {
      return {
        title: 'Article Not Found | Tentackl Extended Brain',
      };
    }

    return {
      title: `${article.title} | Tentackl Extended Brain`,
      description: article.hook,
      openGraph: {
        title: article.title,
        description: article.hook,
        type: 'article',
      },
    };
  } catch {
    return {
      title: 'Extended Brain | Tentackl',
    };
  }
}

/**
 * Extended Brain article page - Server Component
 * Fetches article content from Den CDN and renders with ArticleLayout
 */
export default async function ExtendedBrainArticlePage({ params }: PageProps) {
  const { slug } = await params;

  try {
    const article = await getExtendedBrainArticle(slug);

    if (!article) {
      notFound();
    }

    return (
      <ArticleLayoutWrapper
        title={article.title}
        hook={article.hook}
        body={article.body}
        ctaText={article.ctaText}
      />
    );
  } catch (error) {
    console.error('Error fetching extended brain article:', error);
    notFound();
  }
}
