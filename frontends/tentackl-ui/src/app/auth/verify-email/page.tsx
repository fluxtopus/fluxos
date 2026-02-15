'use client';

import React, { useState, Suspense, useRef, useEffect } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { verifyEmail, resendVerification, loginUser } from '../../../services/auth';

function VerifyEmailForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const email = searchParams.get('email') || '';
  const returnTo = searchParams.get('returnTo') || '/inbox';

  const [code, setCode] = useState(['', '', '', '', '', '']);
  const [isLoading, setIsLoading] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [showPasswordPrompt, setShowPasswordPrompt] = useState(false);

  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Focus first input on mount
  useEffect(() => {
    inputRefs.current[0]?.focus();
  }, []);

  const handleCodeChange = (index: number, value: string) => {
    // Only allow digits
    const digit = value.replace(/\D/g, '').slice(-1);

    const newCode = [...code];
    newCode[index] = digit;
    setCode(newCode);

    // Auto-focus next input
    if (digit && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !code[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    const newCode = [...code];
    for (let i = 0; i < pasted.length; i++) {
      newCode[i] = pasted[i];
    }
    setCode(newCode);
    // Focus the last filled input or the next empty one
    const focusIndex = Math.min(pasted.length, 5);
    inputRefs.current[focusIndex]?.focus();
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const fullCode = code.join('');
    if (fullCode.length !== 6) {
      setError('Please enter the 6-digit code');
      return;
    }

    setIsLoading(true);

    try {
      await verifyEmail(email, fullCode);
      setSuccess('Email verified successfully!');
      setShowPasswordPrompt(true);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      let message: string;
      if (Array.isArray(detail)) {
        message = detail.map((e: any) => e.msg || e.message || String(e)).join(', ');
      } else if (typeof detail === 'object' && detail !== null) {
        message = detail.msg || detail.message || JSON.stringify(detail);
      } else {
        message = detail || err.message || 'Verification failed';
      }
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await loginUser(email, password);
      router.push(returnTo);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      let message: string;
      if (typeof detail === 'string') {
        message = detail;
      } else {
        message = err.message || 'Login failed';
      }
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    setError(null);
    setSuccess(null);
    setIsResending(true);

    try {
      await resendVerification(email);
      setSuccess('Verification code sent! Check your email.');
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(detail || err.message || 'Failed to resend code');
    } finally {
      setIsResending(false);
    }
  };

  if (!email) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md"
      >
        <div className="border border-[oklch(0.22_0.03_260)] bg-[oklch(0.1_0.02_260/0.8)] backdrop-blur-md rounded-lg p-8 text-center">
          <h1 className="text-2xl font-bold text-[oklch(0.95_0.01_90)] mb-4">
            Email Required
          </h1>
          <p className="text-[oklch(0.58_0.01_260)] font-mono text-sm mb-6">
            Please register first to verify your email.
          </p>
          <Link
            href="/auth/register"
            className="inline-block py-3 px-6 font-mono text-sm tracking-wider border-2 border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180)] hover:text-[oklch(0.08_0.02_260)] transition-all duration-300"
          >
            GO TO REGISTER
          </Link>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="w-full max-w-md"
    >
      <div className="border border-[oklch(0.22_0.03_260)] bg-[oklch(0.1_0.02_260/0.8)] backdrop-blur-md rounded-lg p-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-[oklch(0.95_0.01_90)] mb-2">
            {showPasswordPrompt ? 'Email Verified!' : 'Verify Your Email'}
          </h1>
          <p className="text-[oklch(0.58_0.01_260)] font-mono text-sm">
            {showPasswordPrompt
              ? 'Enter your password to sign in'
              : `We sent a code to ${email}`
            }
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-3 border border-[oklch(0.577_0.245_27/0.5)] bg-[oklch(0.577_0.245_27/0.1)] rounded">
            <p className="text-[oklch(0.577_0.245_27)] font-mono text-sm">{error}</p>
          </div>
        )}

        {/* Success */}
        {success && !showPasswordPrompt && (
          <div className="mb-6 p-3 border border-[oklch(0.65_0.25_180/0.5)] bg-[oklch(0.65_0.25_180/0.1)] rounded">
            <p className="text-[oklch(0.65_0.25_180)] font-mono text-sm">{success}</p>
          </div>
        )}

        {showPasswordPrompt ? (
          /* Password prompt after verification */
          <form onSubmit={handleLogin} className="space-y-6">
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
                autoFocus
                className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
                placeholder="Enter your password"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 font-mono text-sm tracking-wider border-2 border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180)] hover:text-[oklch(0.08_0.02_260)] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? 'SIGNING IN...' : 'SIGN IN'}
            </button>
          </form>
        ) : (
          /* Verification code form */
          <form onSubmit={handleVerify} className="space-y-6">
            {/* 6-digit code input */}
            <div>
              <label className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-4 text-center">
                VERIFICATION CODE
              </label>
              <div className="flex justify-center gap-2" onPaste={handlePaste}>
                {code.map((digit, index) => (
                  <input
                    key={index}
                    ref={(el) => { inputRefs.current[index] = el; }}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => handleCodeChange(index, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(index, e)}
                    className="w-12 h-14 text-center text-2xl font-mono bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
                  />
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading || code.join('').length !== 6}
              className="w-full py-3 font-mono text-sm tracking-wider border-2 border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180)] hover:text-[oklch(0.08_0.02_260)] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? 'VERIFYING...' : 'VERIFY EMAIL'}
            </button>
          </form>
        )}

        {/* Resend link */}
        {!showPasswordPrompt && (
          <div className="mt-6 text-center">
            <p className="text-[oklch(0.58_0.01_260)] font-mono text-sm">
              Didn't receive the code?{' '}
              <button
                onClick={handleResend}
                disabled={isResending}
                className="text-[oklch(0.65_0.25_180)] hover:underline disabled:opacity-50"
              >
                {isResending ? 'Sending...' : 'Resend'}
              </button>
            </p>
          </div>
        )}

        {/* Footer */}
        <div className="mt-6 text-center">
          <p className="text-[oklch(0.58_0.01_260)] font-mono text-sm">
            Wrong email?{' '}
            <Link
              href="/auth/register"
              className="text-[oklch(0.65_0.25_180)] hover:underline"
            >
              Register again
            </Link>
          </p>
        </div>
      </div>
    </motion.div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="w-full max-w-md h-96 animate-pulse bg-[oklch(0.1_0.02_260/0.5)] rounded-lg" />}>
      <VerifyEmailForm />
    </Suspense>
  );
}
