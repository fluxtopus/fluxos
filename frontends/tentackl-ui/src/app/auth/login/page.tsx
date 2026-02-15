'use client';

import React, { useState, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { loginUser } from '../../../services/auth';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get('returnTo') || '/inbox';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await loginUser(email, password);
      router.push(returnTo);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      // Handle Pydantic validation errors (array of objects) or string errors
      let message: string;
      if (Array.isArray(detail)) {
        message = detail.map((e: any) => e.msg || e.message || String(e)).join(', ');
      } else if (typeof detail === 'object' && detail !== null) {
        message = detail.msg || detail.message || JSON.stringify(detail);
      } else {
        message = detail || err.message || 'Login failed';
      }

      // If email not verified, redirect to verification page
      if (message.toLowerCase().includes('email not verified')) {
        const verifyUrl = `/auth/verify-email?email=${encodeURIComponent(email)}${returnTo !== '/inbox' ? `&returnTo=${encodeURIComponent(returnTo)}` : ''}`;
        router.push(verifyUrl);
        return;
      }

      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="w-full max-w-md"
    >
      <div className="border border-[oklch(0.22_0.03_260)] bg-[oklch(0.1_0.02_260/0.8)] backdrop-blur-md rounded-lg p-8">
        {/* Logo */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <img src="/icon-192.png" alt="" className="h-7 w-7" />
          <span className="font-mono text-xl font-bold tracking-[0.2em] text-[oklch(0.65_0.25_180)]">
            AIOS
          </span>
        </div>

        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-[oklch(0.95_0.01_90)] mb-2">
            Welcome Back
          </h1>
          <p className="text-[oklch(0.58_0.01_260)] font-mono text-sm">
            Sign in to save and share your workflows
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-3 border border-[oklch(0.577_0.245_27/0.5)] bg-[oklch(0.577_0.245_27/0.1)] rounded">
            <p className="text-[oklch(0.577_0.245_27)] font-mono text-sm">{error}</p>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label
              htmlFor="email"
              className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2"
            >
              EMAIL
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              inputMode="email"
              className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2"
            >
              PASSWORD
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
              placeholder="••••••••"
            />
          </div>

          <div className="flex justify-end">
            <Link
              href="/auth/forgot-password"
              className="font-mono text-xs text-[oklch(0.58_0.01_260)] hover:text-[oklch(0.65_0.25_180)] transition-colors"
            >
              Forgot password?
            </Link>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 font-mono text-sm tracking-wider border-2 border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180)] hover:text-[oklch(0.08_0.02_260)] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'SIGNING IN...' : 'SIGN IN'}
          </button>
        </form>

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-[oklch(0.58_0.01_260)] font-mono text-sm">
            Don't have an account?{' '}
            <Link
              href={`/auth/register${returnTo !== '/inbox' ? `?returnTo=${encodeURIComponent(returnTo)}` : ''}`}
              className="text-[oklch(0.65_0.25_180)] hover:underline"
            >
              Sign up
            </Link>
          </p>
        </div>
      </div>
    </motion.div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="w-full max-w-md h-96 animate-pulse bg-[oklch(0.1_0.02_260/0.5)] rounded-lg" />}>
      <LoginForm />
    </Suspense>
  );
}
