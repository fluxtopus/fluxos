import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Middleware to control route access.
 *
 * Public routes (no auth required):
 * - /auth/* (login, register)
 *
 * Root `/` redirects to /auth/login.
 * Protected routes redirect to /inbox (requires auth).
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Root redirects to login (no public landing page)
  if (pathname === '/') {
    return NextResponse.redirect(new URL('/auth/login', request.url));
  }

  // Allow auth routes
  if (pathname.startsWith('/auth')) {
    return NextResponse.next();
  }


  // Redirect old /delegations to /tasks (backward compatibility)
  if (pathname === '/delegations' || pathname.startsWith('/delegations/')) {
    const newPath = pathname.replace('/delegations', '/tasks');
    return NextResponse.redirect(new URL(newPath, request.url));
  }

  // Allow app routes (main authenticated experience)
  if (
    pathname === '/tasks' ||
    pathname.startsWith('/tasks/') ||
    pathname === '/decisions' ||
    pathname.startsWith('/decisions/') ||
    pathname === '/settings' ||
    pathname.startsWith('/settings/') ||
    pathname === '/activity' ||
    pathname.startsWith('/activity/') ||
    pathname === '/capabilities' ||
    pathname.startsWith('/capabilities/') ||
    pathname === '/agents' ||
    pathname.startsWith('/agents/') ||
    pathname === '/inbox' ||
    pathname.startsWith('/inbox/') ||
    pathname === '/automations' ||
    pathname.startsWith('/automations/')
  ) {
    return NextResponse.next();
  }

  // Allow Next.js internals and static assets
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/api') ||
    pathname.includes('.') // static files like .js, .css, .ico
  ) {
    return NextResponse.next();
  }

  // Redirect everything else to inbox
  return NextResponse.redirect(new URL('/inbox', request.url));
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
