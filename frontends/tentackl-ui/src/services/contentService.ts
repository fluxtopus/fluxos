/**
 * Content Service - Fetches extended brain articles from Den CDN
 *
 * Content is stored as markdown files with YAML frontmatter in Den.
 * A manifest.json file provides the article index for listing.
 */

// Base URL for API requests
// In production, set NEXT_PUBLIC_APP_URL to the full domain
// In development inside Docker, use the container's self-reference
const BASE_URL = process.env.NEXT_PUBLIC_APP_URL ||
  (typeof window === 'undefined' ? 'http://localhost:3000' : '');

// Environment variable for the manifest URL (set in production)
// Falls back to local API proxy for development
const CONTENT_MANIFEST_URL = process.env.NEXT_PUBLIC_CONTENT_MANIFEST_URL ||
  `${BASE_URL}/api/content/manifest`;

export interface ExtendedBrainImage {
  id: string;
  alt: string;
  cdn_url: string;
}

export interface ExtendedBrainArticleMeta {
  slug: string;
  title: string;
  hook: string;
  category: 'core' | 'archive';
  badge?: string;
  order: number;
  file_url: string;
  ctaText?: string;
}

export interface ExtendedBrainArticle extends ExtendedBrainArticleMeta {
  images: ExtendedBrainImage[];
  body: string;
}

interface ContentManifest {
  articles: ExtendedBrainArticleMeta[];
  updated_at: string;
}

/**
 * Parse YAML frontmatter from markdown content
 */
function parseFrontmatter(content: string): { frontmatter: Record<string, any>; body: string } {
  const frontmatterRegex = /^---\n([\s\S]*?)\n---\n([\s\S]*)$/;
  const match = content.match(frontmatterRegex);

  if (!match) {
    return { frontmatter: {}, body: content };
  }

  const [, frontmatterStr, body] = match;

  // Simple YAML parsing for our use case
  const frontmatter: Record<string, any> = {};
  const lines = frontmatterStr.split('\n');
  let currentKey = '';
  let currentArray: any[] = [];
  let inArray = false;
  let inArrayObject: Record<string, any> = {};

  for (const line of lines) {
    // Skip empty lines
    if (!line.trim()) continue;

    // Check for array item
    if (line.match(/^\s+-\s/)) {
      const itemMatch = line.match(/^\s+-\s*(.*)$/);
      if (itemMatch) {
        const value = itemMatch[1].trim();
        // Check if it's a key-value pair in array object (like "- id: hero")
        if (value.includes(':')) {
          // Push previous object if exists before starting new one
          if (Object.keys(inArrayObject).length > 0) {
            currentArray.push(inArrayObject);
            inArrayObject = {};
          }
          const [key, ...rest] = value.split(':');
          inArrayObject[key.trim()] = rest.join(':').trim().replace(/^["']|["']$/g, '');
        } else if (value) {
          // Simple array value
          if (inArray && Object.keys(inArrayObject).length > 0) {
            currentArray.push(inArrayObject);
            inArrayObject = {};
          }
          currentArray.push(value.replace(/^["']|["']$/g, ''));
        } else {
          // Start of new object in array (- followed by newline)
          if (Object.keys(inArrayObject).length > 0) {
            currentArray.push(inArrayObject);
          }
          inArrayObject = {};
        }
      }
      continue;
    }

    // Check for continued array object property
    if (inArray && line.match(/^\s{4,}\w+:/)) {
      const [key, ...rest] = line.trim().split(':');
      inArrayObject[key.trim()] = rest.join(':').trim().replace(/^["']|["']$/g, '');
      continue;
    }

    // If we were in an array, save the last object and close it
    if (inArray && !line.match(/^\s+-/) && !line.match(/^\s{4,}/)) {
      if (Object.keys(inArrayObject).length > 0) {
        currentArray.push(inArrayObject);
        inArrayObject = {};
      }
      frontmatter[currentKey] = currentArray;
      inArray = false;
      currentArray = [];
    }

    // Regular key-value pair
    const kvMatch = line.match(/^(\w+):\s*(.*)$/);
    if (kvMatch) {
      const [, key, value] = kvMatch;
      if (!value.trim()) {
        // Start of array or object
        currentKey = key;
        inArray = true;
        currentArray = [];
      } else {
        // Simple value
        let parsedValue: any = value.trim().replace(/^["']|["']$/g, '');
        // Parse booleans
        if (parsedValue === 'true') parsedValue = true;
        if (parsedValue === 'false') parsedValue = false;
        // Parse numbers
        if (/^\d+$/.test(parsedValue)) parsedValue = parseInt(parsedValue, 10);
        frontmatter[key] = parsedValue;
      }
    }
  }

  // Close any remaining array
  if (inArray) {
    if (Object.keys(inArrayObject).length > 0) {
      currentArray.push(inArrayObject);
    }
    frontmatter[currentKey] = currentArray;
  }

  return { frontmatter, body: body.trim() };
}

/**
 * Replace image placeholders with actual CDN URLs
 * Supports: ![Alt]({{images.hero}}) syntax
 */
function resolveImagePlaceholders(body: string, images: ExtendedBrainImage[]): string {
  const imageMap = new Map(images.map(img => [img.id, img]));

  return body.replace(/\{\{images\.(\w+)\}\}/g, (match, imageId) => {
    const image = imageMap.get(imageId);
    return image ? image.cdn_url : match;
  });
}

/**
 * Fetch the content manifest (list of all articles)
 */
export async function getContentManifest(): Promise<ContentManifest> {
  const response = await fetch(CONTENT_MANIFEST_URL, {
    next: { revalidate: 60 }, // Revalidate every 60 seconds
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch content manifest: ${response.status}`);
  }

  return response.json();
}

/**
 * Get all extended brain articles (metadata only, for listing)
 */
export async function getExtendedBrainArticles(): Promise<ExtendedBrainArticleMeta[]> {
  const manifest = await getContentManifest();
  return manifest.articles.sort((a, b) => a.order - b.order);
}

/**
 * Get a single extended brain article by slug (includes full content)
 */
export async function getExtendedBrainArticle(slug: string): Promise<ExtendedBrainArticle | null> {
  const manifest = await getContentManifest();
  const articleMeta = manifest.articles.find(a => a.slug === slug);

  if (!articleMeta) {
    return null;
  }

  // Fetch the markdown file (prepend BASE_URL for server-side fetching)
  const fileUrl = articleMeta.file_url.startsWith('http')
    ? articleMeta.file_url
    : `${BASE_URL}${articleMeta.file_url}`;
  const response = await fetch(fileUrl, {
    next: { revalidate: 60 },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch article: ${response.status}`);
  }

  const content = await response.text();
  const { frontmatter, body } = parseFrontmatter(content);

  // Extract images from frontmatter
  const images: ExtendedBrainImage[] = (frontmatter.images || []).map((img: any) => ({
    id: img.id,
    alt: img.alt || '',
    cdn_url: img.cdn_url,
  }));

  // Resolve image placeholders in body
  const resolvedBody = resolveImagePlaceholders(body, images);

  return {
    ...articleMeta,
    images,
    body: resolvedBody,
    ctaText: frontmatter.ctaText,
  };
}

/**
 * Get articles grouped by category
 */
export async function getExtendedBrainArticlesByCategory(): Promise<{
  core: ExtendedBrainArticleMeta[];
  archive: ExtendedBrainArticleMeta[];
}> {
  const articles = await getExtendedBrainArticles();

  return {
    core: articles.filter(a => a.category === 'core'),
    archive: articles.filter(a => a.category === 'archive'),
  };
}
