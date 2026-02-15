/**
 * API Route: Content Article
 *
 * Proxies requests to InkPass (Den) to fetch extended brain article content.
 * Looks up article by slug in /content/extended-brain folder.
 */

import { NextRequest, NextResponse } from 'next/server';

// InkPass API URL (Den file storage)
// In Docker: inkpass:8000, locally: localhost:8004
const INKPASS_URL = process.env.INKPASS_API_URL || 'http://inkpass:8000';

// Dev credentials for fetching public content
const DEV_EMAIL = process.env.DEV_EMAIL || 'dev@example.com';
const DEV_PASSWORD = process.env.DEV_PASSWORD || 'DevPassword123!';

let cachedToken: string | null = null;
let tokenExpiry = 0;

/**
 * Get auth token from InkPass (with caching)
 */
async function getAuthToken(): Promise<string> {
  const now = Date.now();

  // Return cached token if still valid (with 5 min buffer)
  if (cachedToken && tokenExpiry > now + 300000) {
    return cachedToken;
  }

  const response = await fetch(`${INKPASS_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: DEV_EMAIL, password: DEV_PASSWORD }),
  });

  if (!response.ok) {
    throw new Error(`Auth failed: ${response.status}`);
  }

  const data = await response.json();
  cachedToken = data.access_token;
  tokenExpiry = now + 1500000;

  return cachedToken!;
}

interface RouteParams {
  params: Promise<{ slug: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { slug } = await params;
    const token = await getAuthToken();

    // List files in /content/extended-brain to find the article
    const listResponse = await fetch(
      `${INKPASS_URL}/api/v1/files?folder_path=/content/extended-brain`,
      {
        headers: { Authorization: `Bearer ${token}` },
      }
    );

    if (!listResponse.ok) {
      return NextResponse.json({ error: 'Failed to list articles' }, { status: 500 });
    }

    const { files } = await listResponse.json();

    // Find article by slug (e.g., octopus-kitchen.md for slug "octopus-kitchen")
    const articleFile = files.find(
      (f: { name: string }) =>
        f.name === `${slug}.md` || f.name.startsWith(`${slug}-`)
    );

    if (!articleFile) {
      return NextResponse.json({ error: 'Article not found' }, { status: 404 });
    }

    // Download the article content
    const downloadResponse = await fetch(
      `${INKPASS_URL}/api/v1/files/${articleFile.id}/download`,
      {
        headers: { Authorization: `Bearer ${token}` },
      }
    );

    if (!downloadResponse.ok) {
      return NextResponse.json(
        { error: 'Failed to download article' },
        { status: 500 }
      );
    }

    const content = await downloadResponse.text();

    return new NextResponse(content, {
      headers: {
        'Content-Type': 'text/markdown',
        'Cache-Control': 'public, s-maxage=60, stale-while-revalidate=300',
      },
    });
  } catch (error) {
    console.error('Error fetching article:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
