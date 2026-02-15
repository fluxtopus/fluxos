'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  SunIcon,
  MoonIcon,
  ComputerDesktopIcon,
} from '@heroicons/react/24/outline';
import { useAuthStore } from '../../../../store/authStore';
import { useThemeStore } from '../../../../store/themeStore';
import { accountApi, logoutUser } from '../../../../services/auth';

export default function AccountSettingsPage() {
  const router = useRouter();
  const { user, setUser } = useAuthStore();
  const { mode: themeMode, setMode: setThemeMode } = useThemeStore();

  // Personal info
  const [firstName, setFirstName] = useState(user?.first_name || '');
  const [lastName, setLastName] = useState(user?.last_name || '');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSuccess, setProfileSuccess] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Email change
  const [showEmailChange, setShowEmailChange] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [emailOtp, setEmailOtp] = useState('');
  const [emailStep, setEmailStep] = useState<'input' | 'verify'>('input');
  const [emailSaving, setEmailSaving] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);

  // Organization
  const [orgName, setOrgName] = useState('');
  const [orgSaving, setOrgSaving] = useState(false);
  const [orgSuccess, setOrgSuccess] = useState(false);
  const [orgError, setOrgError] = useState<string | null>(null);

  // Load org data
  useEffect(() => {
    if (user?.organization_id) {
      accountApi.getOrganization(user.organization_id).then((org) => {
        setOrgName(org.name || '');
      }).catch(() => {});
    }
  }, [user?.organization_id]);

  // Sync user data when store changes
  useEffect(() => {
    setFirstName(user?.first_name || '');
    setLastName(user?.last_name || '');
  }, [user?.first_name, user?.last_name]);

  const handleProfileSave = async () => {
    setProfileError(null);
    setProfileSuccess(false);

    if (firstName.trim().length < 2) {
      setProfileError('First name must be at least 2 characters');
      return;
    }
    if (lastName.trim().length < 2) {
      setProfileError('Last name must be at least 2 characters');
      return;
    }

    setProfileSaving(true);
    try {
      const result = await accountApi.updateProfile({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
      });
      // Update store
      if (user) {
        setUser({
          ...user,
          first_name: result.first_name,
          last_name: result.last_name,
        });
      }
      setProfileSuccess(true);
      setTimeout(() => setProfileSuccess(false), 3000);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setProfileError(typeof detail === 'string' ? detail : 'Failed to update profile');
    } finally {
      setProfileSaving(false);
    }
  };

  const handleEmailInitiate = async () => {
    setEmailError(null);
    setEmailSaving(true);
    try {
      await accountApi.initiateEmailChange(newEmail);
      setEmailStep('verify');
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setEmailError(typeof detail === 'string' ? detail : 'Failed to send verification code');
    } finally {
      setEmailSaving(false);
    }
  };

  const handleEmailConfirm = async () => {
    setEmailError(null);
    setEmailSaving(true);
    try {
      await accountApi.confirmEmailChange(emailOtp);
      // Force logout and redirect to login
      logoutUser();
      router.push('/auth/login');
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setEmailError(typeof detail === 'string' ? detail : 'Invalid or expired verification code');
    } finally {
      setEmailSaving(false);
    }
  };

  const handleOrgSave = async () => {
    setOrgError(null);
    setOrgSuccess(false);

    if (orgName.trim().length < 2) {
      setOrgError('Organization name must be at least 2 characters');
      return;
    }

    if (!user?.organization_id) return;

    setOrgSaving(true);
    try {
      await accountApi.updateOrganization(user.organization_id, {
        name: orgName.trim(),
      });
      setOrgSuccess(true);
      setTimeout(() => setOrgSuccess(false), 3000);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setOrgError(typeof detail === 'string' ? detail : 'Failed to update organization');
    } finally {
      setOrgSaving(false);
    }
  };

  const inputClass = 'w-full px-4 py-2.5 bg-[var(--background)] border border-[var(--border)] rounded-lg text-sm text-[var(--foreground)] font-mono focus:outline-none focus:border-[var(--accent)] transition-colors';
  const labelClass = 'block font-mono text-xs tracking-wider text-[var(--muted-foreground)] mb-2';
  const btnPrimary = 'px-4 py-2 font-mono text-xs tracking-wider border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--accent-foreground)] rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed';
  const btnSecondary = 'px-4 py-2 font-mono text-xs tracking-wider border border-[var(--border)] text-[var(--muted-foreground)] hover:bg-[var(--muted)] rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed';

  return (
    <div className="space-y-8">
      {/* Personal Info */}
      <section className="border border-[var(--border)] rounded-lg p-6 bg-[var(--card)]">
        <h2 className="text-sm font-bold text-[var(--foreground)] tracking-tight mb-1">Personal Info</h2>
        <p className="text-xs font-mono text-[var(--muted-foreground)] mb-5">Update your name</p>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label htmlFor="settings-first-name" className={labelClass}>FIRST NAME</label>
            <input
              id="settings-first-name"
              type="text"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              className={inputClass}
            />
          </div>
          <div>
            <label htmlFor="settings-last-name" className={labelClass}>LAST NAME</label>
            <input
              id="settings-last-name"
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              className={inputClass}
            />
          </div>
        </div>

        {profileError && (
          <p className="text-xs font-mono text-[var(--destructive)] mb-3">{profileError}</p>
        )}
        {profileSuccess && (
          <p className="text-xs font-mono text-[var(--accent)] mb-3">Profile updated</p>
        )}

        <button onClick={handleProfileSave} disabled={profileSaving} className={btnPrimary}>
          {profileSaving ? 'SAVING...' : 'SAVE'}
        </button>
      </section>

      {/* Email */}
      <section className="border border-[var(--border)] rounded-lg p-6 bg-[var(--card)]">
        <h2 className="text-sm font-bold text-[var(--foreground)] tracking-tight mb-1">Email</h2>
        <p className="text-xs font-mono text-[var(--muted-foreground)] mb-5">
          Current: <span className="text-[var(--foreground)]">{user?.email}</span>
        </p>

        {!showEmailChange ? (
          <button onClick={() => setShowEmailChange(true)} className={btnSecondary}>
            CHANGE EMAIL
          </button>
        ) : (
          <div className="space-y-4">
            {emailStep === 'input' && (
              <>
                <div>
                  <label htmlFor="new-email" className={labelClass}>NEW EMAIL</label>
                  <input
                    id="new-email"
                    type="email"
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    className={inputClass}
                    placeholder="new@example.com"
                  />
                </div>
                {emailError && (
                  <p className="text-xs font-mono text-[var(--destructive)]">{emailError}</p>
                )}
                <div className="flex gap-2">
                  <button onClick={handleEmailInitiate} disabled={emailSaving || !newEmail} className={btnPrimary}>
                    {emailSaving ? 'SENDING...' : 'SEND CODE'}
                  </button>
                  <button onClick={() => { setShowEmailChange(false); setEmailError(null); }} className={btnSecondary}>
                    CANCEL
                  </button>
                </div>
              </>
            )}

            {emailStep === 'verify' && (
              <>
                <p className="text-xs font-mono text-[var(--muted-foreground)]">
                  A verification code was sent to <span className="text-[var(--foreground)]">{newEmail}</span>
                </p>
                <div>
                  <label htmlFor="email-otp" className={labelClass}>VERIFICATION CODE</label>
                  <input
                    id="email-otp"
                    type="text"
                    value={emailOtp}
                    onChange={(e) => setEmailOtp(e.target.value)}
                    maxLength={6}
                    className={`${inputClass} tracking-[0.3em] text-center`}
                    placeholder="000000"
                  />
                </div>
                {emailError && (
                  <p className="text-xs font-mono text-[var(--destructive)]">{emailError}</p>
                )}
                <p className="text-[10px] font-mono text-[var(--muted-foreground)]">
                  Confirming will sign you out of all sessions
                </p>
                <div className="flex gap-2">
                  <button onClick={handleEmailConfirm} disabled={emailSaving || !emailOtp} className={btnPrimary}>
                    {emailSaving ? 'CONFIRMING...' : 'CONFIRM'}
                  </button>
                  <button onClick={() => { setEmailStep('input'); setEmailError(null); setEmailOtp(''); }} className={btnSecondary}>
                    BACK
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </section>

      {/* Appearance */}
      <section className="border border-[var(--border)] rounded-lg p-6 bg-[var(--card)]">
        <h2 className="text-sm font-bold text-[var(--foreground)] tracking-tight mb-1">Appearance</h2>
        <p className="text-xs font-mono text-[var(--muted-foreground)] mb-5">Choose your color theme</p>

        <div className="grid grid-cols-3 gap-3">
          {([
            { key: 'system', label: 'SYSTEM', icon: ComputerDesktopIcon },
            { key: 'light', label: 'LIGHT', icon: SunIcon },
            { key: 'dark', label: 'DARK', icon: MoonIcon },
          ] as const).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setThemeMode(key)}
              className={`flex flex-col items-center gap-2 px-3 py-4 rounded-lg border transition-all text-xs font-mono tracking-wider ${
                themeMode === key
                  ? 'border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]'
                  : 'border-[var(--border)] text-[var(--muted-foreground)] hover:border-[var(--accent)]/50 hover:text-[var(--foreground)]'
              }`}
            >
              <Icon className="w-5 h-5" />
              {label}
            </button>
          ))}
        </div>
      </section>

      {/* Organization */}
      <section className="border border-[var(--border)] rounded-lg p-6 bg-[var(--card)]">
        <h2 className="text-sm font-bold text-[var(--foreground)] tracking-tight mb-1">Organization</h2>
        <p className="text-xs font-mono text-[var(--muted-foreground)] mb-5">Manage your organization name</p>

        <div className="mb-4">
          <label htmlFor="org-name" className={labelClass}>ORGANIZATION NAME</label>
          <input
            id="org-name"
            type="text"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            className={inputClass}
          />
        </div>

        {orgError && (
          <p className="text-xs font-mono text-[var(--destructive)] mb-3">{orgError}</p>
        )}
        {orgSuccess && (
          <p className="text-xs font-mono text-[var(--accent)] mb-3">Organization updated</p>
        )}

        <button onClick={handleOrgSave} disabled={orgSaving} className={btnPrimary}>
          {orgSaving ? 'SAVING...' : 'SAVE'}
        </button>
      </section>
    </div>
  );
}
