'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { accountApi } from '../../../services/auth';

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await accountApi.forgotPassword(email);
      // Always redirect to reset page (prevents email enumeration)
      router.push(`/auth/reset-password?email=${encodeURIComponent(email)}`);
    } catch (err: any) {
      // Still redirect — backend always returns success to prevent enumeration
      router.push(`/auth/reset-password?email=${encodeURIComponent(email)}`);
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
            FluxOS
          </span>
        </div>

        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-[oklch(0.95_0.01_90)] mb-2">
            Forgot Password
          </h1>
          <p className="text-[oklch(0.58_0.01_260)] font-mono text-sm">
            Enter your email to receive a reset code
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
              className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
              placeholder="you@example.com"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 font-mono text-sm tracking-wider border-2 border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180)] hover:text-[oklch(0.08_0.02_260)] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'SENDING...' : 'SEND RESET CODE'}
          </button>
        </form>

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-[oklch(0.58_0.01_260)] font-mono text-sm">
            Remember your password?{' '}
            <Link
              href="/auth/login"
              className="text-[oklch(0.65_0.25_180)] hover:underline"
            >
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </motion.div>
  );
}
