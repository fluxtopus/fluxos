/**
 * API Route: Content Images
 *
 * Proxies image requests to InkPass (Den) for serving article images.
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
  params: Promise<{ id: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { id } = await params;
    const token = await getAuthToken();

    // Download the image from Den
    const downloadResponse = await fetch(
      `${INKPASS_URL}/api/v1/files/${id}/download`,
      {
        headers: { Authorization: `Bearer ${token}` },
      }
    );

    if (!downloadResponse.ok) {
      return NextResponse.json({ error: 'Image not found' }, { status: 404 });
    }

    // Get content type from response
    const contentType = downloadResponse.headers.get('content-type') || 'image/png';
    const imageBuffer = await downloadResponse.arrayBuffer();

    return new NextResponse(imageBuffer, {
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'public, max-age=86400, stale-while-revalidate=604800',
      },
    });
  } catch (error) {
    console.error('Error fetching image:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
