/**
 * API Route: Content Manifest
 *
 * Proxies requests to InkPass (Den) to fetch the extended brain content manifest.
 * In development, fetches from local InkPass. In production, can be replaced with CDN URL.
 */

import { NextResponse } from 'next/server';

// InkPass API URL (Den file storage)
// In Docker: inkpass:8000, locally: localhost:8004
const INKPASS_URL = process.env.INKPASS_API_URL || 'http://inkpass:8000';

// Dev credentials for fetching public content
// In production, manifest would be served from CDN directly
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
  // JWT typically expires in 30 min, cache for 25 min
  tokenExpiry = now + 1500000;

  return cachedToken!;
}

/**
 * Fetch file from Den by folder path and name
 */
async function fetchManifest(token: string): Promise<Response> {
  // List files in /content/extended-brain to find manifest.json
  const listResponse = await fetch(
    `${INKPASS_URL}/api/v1/files?folder_path=/content/extended-brain`,
    {
      headers: { Authorization: `Bearer ${token}` },
    }
  );

  if (!listResponse.ok) {
    // Fallback: return empty manifest for development
    return new Response(
      JSON.stringify({
        articles: [],
        updated_at: new Date().toISOString(),
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }

  const { files } = await listResponse.json();
  const manifest = files.find(
    (f: { name: string }) => f.name === 'manifest.json'
  );

  if (!manifest) {
    // Return empty manifest if not found
    return new Response(
      JSON.stringify({
        articles: [],
        updated_at: new Date().toISOString(),
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }

  // Download the manifest content
  const downloadResponse = await fetch(
    `${INKPASS_URL}/api/v1/files/${manifest.id}/download`,
    {
      headers: { Authorization: `Bearer ${token}` },
    }
  );

  return downloadResponse;
}

export async function GET() {
  try {
    const token = await getAuthToken();
    const response = await fetchManifest(token);

    if (!response.ok) {
      console.error('Failed to fetch manifest:', response.status);
      return NextResponse.json(
        { articles: [], updated_at: new Date().toISOString() },
        { status: 200 }
      );
    }

    const manifest = await response.json();

    return NextResponse.json(manifest, {
      headers: {
        'Cache-Control': 'public, s-maxage=60, stale-while-revalidate=300',
      },
    });
  } catch (error) {
    console.error('Error fetching manifest:', error);
    // Return empty manifest as fallback
    return NextResponse.json(
      { articles: [], updated_at: new Date().toISOString() },
      { status: 200 }
    );
  }
}
