'use client';

import React, { useState, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { registerUser } from '../../../services/auth';

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get('returnTo') || '/inbox';

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [organizationName, setOrganizationName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validate name fields
    if (firstName.trim().length < 2) {
      setError('First name must be at least 2 characters');
      return;
    }
    if (lastName.trim().length < 2) {
      setError('Last name must be at least 2 characters');
      return;
    }

    // Validate passwords match
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    // Validate password length
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setIsLoading(true);

    try {
      const result = await registerUser(email, password, firstName.trim(), lastName.trim(), organizationName || undefined);
      // Redirect to email verification page
      const verifyUrl = `/auth/verify-email?email=${encodeURIComponent(email)}${returnTo !== '/inbox' ? `&returnTo=${encodeURIComponent(returnTo)}` : ''}`;
      router.push(verifyUrl);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      // Handle Pydantic validation errors (array of objects) or string errors
      let message: string;
      if (Array.isArray(detail)) {
        message = detail.map((e: any) => e.msg || e.message || String(e)).join(', ');
      } else if (typeof detail === 'object' && detail !== null) {
        message = detail.msg || detail.message || JSON.stringify(detail);
      } else {
        message = detail || err.message || 'Registration failed';
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
            Create Account
          </h1>
          <p className="text-[oklch(0.58_0.01_260)] font-mono text-sm">
            Sign up to save and share your workflows
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-3 border border-[oklch(0.577_0.245_27/0.5)] bg-[oklch(0.577_0.245_27/0.1)] rounded">
            <p className="text-[oklch(0.577_0.245_27)] font-mono text-sm">{error}</p>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="firstName"
                className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2"
              >
                FIRST NAME
              </label>
              <input
                id="firstName"
                type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                required
                minLength={2}
                autoComplete="given-name"
                className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
                placeholder="Jane"
              />
            </div>
            <div>
              <label
                htmlFor="lastName"
                className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2"
              >
                LAST NAME
              </label>
              <input
                id="lastName"
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                required
                minLength={2}
                autoComplete="family-name"
                className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
                placeholder="Doe"
              />
            </div>
          </div>

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
              htmlFor="organizationName"
              className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2"
            >
              ORGANIZATION NAME
            </label>
            <input
              id="organizationName"
              type="text"
              value={organizationName}
              onChange={(e) => setOrganizationName(e.target.value)}
              autoComplete="organization"
              className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
              placeholder="Your company or team name"
            />
            <p className="mt-1 font-mono text-[10px] text-[oklch(0.4_0.01_260)]">
              Optional — defaults to &quot;{firstName.trim() || 'Your'}&apos;s Organization&quot;
            </p>
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
            {isLoading ? 'CREATING ACCOUNT...' : 'CREATE ACCOUNT'}
          </button>
        </form>

        {/* Terms */}
        <p className="mt-6 text-center font-mono text-[10px] text-[oklch(0.4_0.01_260)]">
          By creating an account, you agree to our terms of service
        </p>

        {/* Footer */}
        <div className="mt-6 text-center">
          <p className="text-[oklch(0.58_0.01_260)] font-mono text-sm">
            Already have an account?{' '}
            <Link
              href={`/auth/login${returnTo !== '/inbox' ? `?returnTo=${encodeURIComponent(returnTo)}` : ''}`}
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

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="w-full max-w-md h-[500px] animate-pulse bg-[oklch(0.1_0.02_260/0.5)] rounded-lg" />}>
      <RegisterForm />
    </Suspense>
  );
}
