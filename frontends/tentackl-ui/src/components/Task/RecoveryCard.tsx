'use client';

import {
  ArrowPathIcon,
  ArrowUturnLeftIcon,
  ForwardIcon,
  XCircleIcon,
  BoltIcon,
} from '@heroicons/react/24/outline';
import type { ObserverProposal } from '../../types/task';

interface RecoveryCardProps {
  proposal: ObserverProposal;
  stepName?: string;
  onAccept: () => void;
  onReject: () => void;
  isProcessing?: boolean;
}

const proposalConfig: Record<ObserverProposal['proposal_type'], {
  icon: typeof ArrowPathIcon;
  title: string;
  description: string;
  acceptLabel: string;
  className: string;
}> = {
  RETRY: {
    icon: ArrowPathIcon,
    title: 'Retry this step',
    description: 'Try running the same step again',
    acceptLabel: 'Retry',
    className: 'text-[oklch(0.65_0.25_180)] bg-[oklch(0.65_0.25_180/0.1)]',
  },
  FALLBACK: {
    icon: ArrowUturnLeftIcon,
    title: 'Use alternative',
    description: 'Try a different approach to accomplish this step',
    acceptLabel: 'Use alternative',
    className: 'text-[oklch(0.7_0.2_60)] bg-[oklch(0.7_0.2_60/0.1)]',
  },
  SKIP: {
    icon: ForwardIcon,
    title: 'Skip this step',
    description: 'Continue without completing this step',
    acceptLabel: 'Skip',
    className: 'text-[var(--muted-foreground)] bg-[var(--muted)]',
  },
  ABORT: {
    icon: XCircleIcon,
    title: 'Stop execution',
    description: 'This cannot be recovered from',
    acceptLabel: 'Stop',
    className: 'text-[oklch(0.65_0.25_27)] bg-[oklch(0.65_0.25_27/0.1)]',
  },
  REPLAN: {
    icon: BoltIcon,
    title: 'Adjust the plan',
    description: 'Modify the remaining steps to work around this issue',
    acceptLabel: 'Adjust plan',
    className: 'text-[oklch(0.65_0.25_180)] bg-[oklch(0.65_0.25_180/0.1)]',
  },
};

/**
 * RecoveryCard - Shows recovery options when a step fails.
 * Observer proposes, user decides.
 */
export function RecoveryCard({
  proposal,
  stepName,
  onAccept,
  onReject,
  isProcessing = false,
}: RecoveryCardProps) {
  const config = proposalConfig[proposal.proposal_type];
  const Icon = config.icon;

  // If auto-applied, show as info only
  if (proposal.auto_applied) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
        <div className="flex items-start gap-3">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${config.className}`}>
            <Icon className="w-4 h-4" />
          </div>
          <div>
            <p className="text-sm font-medium text-[var(--foreground)]">
              Auto-recovered: {config.title.toLowerCase()}
            </p>
            <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
              {proposal.reason}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[oklch(0.7_0.2_60/0.5)] bg-[var(--card)] overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 bg-[oklch(0.7_0.2_60/0.05)] border-b border-[oklch(0.7_0.2_60/0.2)]">
        <div className="flex items-start gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${config.className}`}>
            <Icon className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-[var(--foreground)]">
              {config.title}
            </h3>
            <p className="text-sm text-[var(--muted-foreground)] mt-0.5">
              {stepName ? `For: ${stepName}` : config.description}
            </p>
          </div>
        </div>
      </div>

      {/* Reason */}
      <div className="px-5 py-4 border-b border-[var(--border)]">
        <p className="text-sm text-[var(--foreground)]">
          {proposal.reason}
        </p>
      </div>

      {/* Actions */}
      <div className="px-5 py-4 flex items-center justify-end gap-3">
        <button
          onClick={onReject}
          disabled={isProcessing}
          className="px-4 py-2 text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors disabled:opacity-50"
        >
          Dismiss
        </button>
        <button
          onClick={onAccept}
          disabled={isProcessing}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white rounded-lg delegation-cta disabled:opacity-50"
        >
          {isProcessing ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Processing...
            </>
          ) : (
            config.acceptLabel
          )}
        </button>
      </div>
    </div>
  );
}
