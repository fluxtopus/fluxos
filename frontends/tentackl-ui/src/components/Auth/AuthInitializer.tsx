'use client';

import { useEffect } from 'react';
import { initializeAuth } from '../../services/auth';

/**
 * Component to initialize auth state on app load
 * Checks for existing token and validates it
 */
export function AuthInitializer() {
  useEffect(() => {
    initializeAuth();
  }, []);

  return null;
}
