'use client';

import React from 'react';

/**
 * Auth layout - minimal centered layout for login/register pages
 * No navbar — logo is part of each form card
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center p-4 dark bg-[var(--background)]">
      {children}
    </div>
  );
}
