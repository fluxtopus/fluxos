'use client';

import { useCallback } from 'react';
import { CpuChipIcon } from '@heroicons/react/24/outline';
import { ChatInput } from './ChatInput';
import type { FileReference } from '@/services/fileService';

interface WelcomeScreenProps {
  onSendMessage: (text: string, fileReferences?: FileReference[]) => Promise<void>;
  isStreaming: boolean;
  userName?: string;
  onSkip: () => void;
}

const STARTER_CHIPS = [
  {
    label: 'Automate a workflow',
    message: 'I want to automate a workflow in my business.',
  },
  {
    label: 'Monitor data sources',
    message: 'I want to monitor data sources and get alerts.',
  },
  {
    label: 'Generate reports',
    message: 'I want to generate reports from my data.',
  },
  {
    label: 'Just explore',
    message: 'I just want to explore what Flux can do.',
  },
] as const;

export function WelcomeScreen({
  onSendMessage,
  isStreaming,
  userName,
  onSkip,
}: WelcomeScreenProps) {
  const handleChipClick = useCallback(
    (message: string) => {
      onSendMessage(message);
    },
    [onSendMessage],
  );

  const greeting = userName ? `Hey ${userName}! I'm Flux.` : "Hey! I'm Flux.";

  return (
    <div className="flex flex-col h-full">
      {/* Centered content area */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 text-center">
        {/* Pulsing icon */}
        <div className="relative mb-4">
          <div className="absolute inset-0 rounded-full bg-[var(--accent)] opacity-20 animate-ping" />
          <div className="relative h-14 w-14 rounded-full bg-[var(--accent)]/10 flex items-center justify-center">
            <CpuChipIcon className="h-7 w-7 text-[var(--accent)]" />
          </div>
        </div>

        <h1 className="text-xl font-semibold text-[var(--foreground)] mb-1">
          {greeting}
        </h1>
        <p className="text-sm text-[var(--muted-foreground)] max-w-xs mb-6">
          Tell me about your business and I&apos;ll find the right first task for you.
        </p>

        {/* 2x2 Starter chips */}
        <div className="grid grid-cols-2 gap-2.5 w-full max-w-sm mb-5">
          {STARTER_CHIPS.map((chip) => (
            <button
              key={chip.label}
              type="button"
              onClick={() => handleChipClick(chip.message)}
              disabled={isStreaming}
              className="px-3 py-2.5 rounded-xl border border-[var(--border)] bg-[var(--card)] text-sm text-[var(--foreground)] hover:border-[var(--accent)] hover:bg-[var(--accent)]/5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {chip.label}
            </button>
          ))}
        </div>

        {/* Skip link */}
        <button
          type="button"
          onClick={onSkip}
          className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors underline underline-offset-2"
        >
          Skip
        </button>
      </div>

      {/* Pinned bottom input */}
      <div className="px-3 pb-3">
        <ChatInput
          onSubmit={onSendMessage}
          disabled={isStreaming}
          placeholder="Tell Flux about your work..."
        />
      </div>
    </div>
  );
}
