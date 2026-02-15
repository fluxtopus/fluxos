'use client';

import React, { useState, useEffect, Fragment } from 'react';
import { Dialog, Transition, Tab } from '@headlessui/react';
import { XMarkIcon, LockClosedIcon } from '@heroicons/react/24/outline';
import { motion } from 'framer-motion';
import { useAuthStore } from '../../store/authStore';
import { loginUser, registerUser } from '../../services/auth';

/**
 * Auth modal - triggered when anonymous user attempts a gated action
 * Shows login/register forms in a modal dialog
 */
export function AuthModal() {
  const {
    showAuthModal,
    authModalTab,
    pendingAction,
    closeAuthModal,
    setAuthModalTab,
  } = useAuthStore();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form when modal opens/closes
  useEffect(() => {
    if (!showAuthModal) {
      setEmail('');
      setPassword('');
      setConfirmPassword('');
      setError(null);
    }
  }, [showAuthModal]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await loginUser(email, password);
      // Modal will close and pending action will execute via store
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
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setIsLoading(true);

    try {
      await registerUser(email, password);
      // Modal will close and pending action will execute via store
    } catch (err: any) {
      const message = err.response?.data?.detail || err.message || 'Registration failed';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  // Get action description for display
  const getActionDescription = () => {
    if (!pendingAction) return 'Continue';
    switch (pendingAction.type) {
      case 'save':
        return 'Save your workflow';
      case 'share':
        return 'Share your workflow';
      case 'copy':
        return 'Copy this template';
      case 'edit':
        return 'Edit this workflow';
      default:
        return 'Continue';
    }
  };

  return (
    <Transition appear show={showAuthModal} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={closeAuthModal}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-[oklch(0_0_0/0.7)] backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden border border-[oklch(0.22_0.03_260)] bg-[oklch(0.1_0.02_260)] rounded-lg shadow-xl transition-all">
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b border-[oklch(0.22_0.03_260)]">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 flex items-center justify-center border border-[oklch(0.65_0.25_180/0.5)] rounded-lg bg-[oklch(0.65_0.25_180/0.1)]">
                      <LockClosedIcon className="w-5 h-5 text-[oklch(0.65_0.25_180)]" />
                    </div>
                    <div>
                      <Dialog.Title className="text-lg font-bold text-[oklch(0.95_0.01_90)]">
                        Sign in required
                      </Dialog.Title>
                      <p className="font-mono text-xs text-[oklch(0.58_0.01_260)]">
                        {getActionDescription()}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={closeAuthModal}
                    className="p-2 text-[oklch(0.58_0.01_260)] hover:text-[oklch(0.95_0.01_90)] transition-colors"
                  >
                    <XMarkIcon className="w-5 h-5" />
                  </button>
                </div>

                {/* Tabs */}
                <Tab.Group
                  selectedIndex={authModalTab === 'login' ? 0 : 1}
                  onChange={(index) => setAuthModalTab(index === 0 ? 'login' : 'register')}
                >
                  <Tab.List className="flex border-b border-[oklch(0.22_0.03_260)]">
                    <Tab
                      className={({ selected }) =>
                        `flex-1 py-3 font-mono text-xs tracking-wider transition-colors ${
                          selected
                            ? 'text-[oklch(0.65_0.25_180)] border-b-2 border-[oklch(0.65_0.25_180)]'
                            : 'text-[oklch(0.58_0.01_260)] hover:text-[oklch(0.95_0.01_90)]'
                        }`
                      }
                    >
                      SIGN IN
                    </Tab>
                    <Tab
                      className={({ selected }) =>
                        `flex-1 py-3 font-mono text-xs tracking-wider transition-colors ${
                          selected
                            ? 'text-[oklch(0.65_0.25_180)] border-b-2 border-[oklch(0.65_0.25_180)]'
                            : 'text-[oklch(0.58_0.01_260)] hover:text-[oklch(0.95_0.01_90)]'
                        }`
                      }
                    >
                      SIGN UP
                    </Tab>
                  </Tab.List>

                  <Tab.Panels className="p-6">
                    {/* Error */}
                    {error && (
                      <div className="mb-4 p-3 border border-[oklch(0.577_0.245_27/0.5)] bg-[oklch(0.577_0.245_27/0.1)] rounded">
                        <p className="text-[oklch(0.577_0.245_27)] font-mono text-sm">{error}</p>
                      </div>
                    )}

                    {/* Login Tab */}
                    <Tab.Panel>
                      <form onSubmit={handleLogin} className="space-y-4">
                        <div>
                          <label className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2">
                            EMAIL
                          </label>
                          <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            autoComplete="email"
                            className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
                            placeholder="you@example.com"
                          />
                        </div>

                        <div>
                          <label className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2">
                            PASSWORD
                          </label>
                          <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            autoComplete="current-password"
                            className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
                            placeholder="••••••••"
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
                    </Tab.Panel>

                    {/* Register Tab */}
                    <Tab.Panel>
                      <form onSubmit={handleRegister} className="space-y-4">
                        <div>
                          <label className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2">
                            EMAIL
                          </label>
                          <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            autoComplete="email"
                            className="w-full px-4 py-3 bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded text-[oklch(0.95_0.01_90)] font-mono text-sm focus:outline-none focus:border-[oklch(0.65_0.25_180)] transition-colors"
                            placeholder="you@example.com"
                          />
                        </div>

                        <div>
                          <label className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2">
                            PASSWORD
                          </label>
                          <input
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
                          <label className="block font-mono text-xs tracking-wider text-[oklch(0.58_0.01_260)] mb-2">
                            CONFIRM PASSWORD
                          </label>
                          <input
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
                    </Tab.Panel>
                  </Tab.Panels>
                </Tab.Group>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}
