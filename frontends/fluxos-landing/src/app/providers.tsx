'use client'

import React, { useEffect } from 'react'
import { PostHogProvider } from 'posthog-js/react'
import { initPostHog, posthog } from '../lib/posthog'

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    initPostHog()
  }, [])

  return (
    <PostHogProvider client={posthog}>
      {children}
    </PostHogProvider>
  )
}
