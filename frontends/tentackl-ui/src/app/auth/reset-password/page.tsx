'use client';

import React, { useState, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { accountApi } from '../../../services/auth';

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const emailParam = searchParams.get('email') || '';

  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setIsLoading(true);

    try {
      await accountApi.resetPassword(emailParam, code, newPassword);
      setSuccess(true);
      // Redirect to login after a brief pause
      setTimeout(() => {
        router.push('/auth/login');
      }, 2000);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      let message: string;
      if (Array.isArray(detail)) {
        message = detail.map((e: any) => e.msg || e.message || String(e)).join(', ');
      } else if (typeof detail === 'object' && detail !== null) {
        message = detail.msg || detail.message || JSON.stringify(detail);
      } else {
        message = detail || err.message || 'Password reset failed';
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
            Reset Password
          </h1>
          <p className="text-[oklch(0.58_0.01_260)] font-mono text-sm">
            Enter the code sent to your email
          </p>
        </div>

        {/* Success */}
        {success && (
          <div className="mb-6 p-3 border border-[oklch(0.65_0.25_180/0.5)] bg-[oklch(0.65_0.25_180/0.1)] rounded">
            <p className="text-[oklch(0.65_0.25_180)] font-mono text-sm">
              Password reset successfully. Redirecting to login...
            </p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mb-6 p-3 border border-[oklch(0.577_0.245_27/0.5)] bg-[oklch(0.577_0.245_27/0.1)] rounded">
            <p className="text-[oklch(0.577_0.245_27)] font-mono text-sm">{error}</p>
          </div>
        )}

        {!success && (
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label
                htmlFor="code"
                className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2"
              >
                VERIFICATION CODE
              </label>
              <input
                id="code"
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
                maxLength={6}
                autoComplete="one-time-code"
                className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm tracking-[0.3em] text-center focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
                placeholder="000000"
              />
            </div>

            <div>
              <label
                htmlFor="newPassword"
                className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2"
              >
                NEW PASSWORD
              </label>
              <input
                id="newPassword"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                autoComplete="new-password"
                className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
                placeholder="••••••••"
              />
              <p className="mt-1 font-mono text-[10px] text-[oklch(0.4_0.01_260)]">
                At least 8 characters
              </p>
            </div>

            <div>
              <label
                htmlFor="confirmPassword"
                className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2"
              >
                CONFIRM PASSWORD
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                autoComplete="new-password"
                className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 font-mono text-sm tracking-wider border-2 border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180)] hover:text-[oklch(0.08_0.02_260)] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? 'RESETTING...' : 'RESET PASSWORD'}
            </button>
          </form>
        )}

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-[oklch(0.58_0.01_260)] font-mono text-sm">
            <Link
              href="/auth/login"
              className="text-[oklch(0.65_0.25_180)] hover:underline"
            >
              Back to sign in
            </Link>
          </p>
        </div>
      </div>
    </motion.div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="w-full max-w-md h-96 animate-pulse bg-[oklch(0.1_0.02_260/0.5)] rounded-lg" />}>
      <ResetPasswordForm />
    </Suspense>
  );
}
