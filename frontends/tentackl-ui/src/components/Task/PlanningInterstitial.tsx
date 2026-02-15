'use client';

import { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  CheckCircleIcon,
  XCircleIcon,
  ChevronDownIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import type { PlanningProgress, PlanningPhaseStatus } from '../../types/task';

interface PlanningInterstitialProps {
  progress: PlanningProgress;
  onCancel?: () => void;
  isExpanded: boolean;
  onToggleExpand: () => void;
}

function PhaseIcon({ status }: { status: PlanningPhaseStatus }) {
  switch (status) {
    case 'done':
      return <CheckCircleIcon className="w-4 h-4 text-[oklch(0.65_0.25_150)]" />;
    case 'failed':
      return <XCircleIcon className="w-4 h-4 text-red-500" />;
    case 'active':
      return (
        <motion.div
          className="w-4 h-4 rounded-full border-2 border-[oklch(0.65_0.25_180)] border-t-transparent"
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
        />
      );
    default:
      return <div className="w-4 h-4 rounded-full border border-[var(--border)]" />;
  }
}

function PhaseRow({ phase }: { phase: { type: string; label: string; status: PlanningPhaseStatus; detail?: string } }) {
  return (
    <div
      className={`flex items-center gap-3 ${
        phase.status === 'active'
          ? 'text-[oklch(0.65_0.25_180)]'
          : phase.status === 'done'
            ? 'text-[var(--foreground)]'
            : phase.status === 'failed'
              ? 'text-red-500'
              : 'text-[var(--muted-foreground)]'
      }`}
    >
      <PhaseIcon status={phase.status} />
      <span className={`text-sm ${phase.status === 'active' ? 'font-medium' : ''}`}>
        {phase.label}
      </span>
      {phase.detail && (
        <span className="text-xs text-[var(--muted-foreground)] ml-auto">
          {phase.detail}
        </span>
      )}
    </div>
  );
}

/**
 * PlanningInterstitial - Shows real-time backend progress while a task is being planned.
 *
 * Two modes:
 * - Expanded: Centered visor showing prev/current/next phase with a compact spinner
 * - Collapsed: Single-line progress bar with current phase label + spinner + expand chevron
 */
export function PlanningInterstitial({
  progress,
  onCancel,
  isExpanded,
  onToggleExpand,
}: PlanningInterstitialProps) {
  const activePhase = progress.phases.find((p) => p.status === 'active');
  const completedCount = progress.phases.filter((p) => p.status === 'done').length;
  const totalPhases = progress.phases.length;
  const progressPercent = Math.round((completedCount / totalPhases) * 100);

  // Visor: show previous, current, and next phase
  const activeIdx = progress.phases.findIndex((p) => p.status === 'active');
  const visorPhases = useMemo(() => {
    if (progress.isComplete || progress.isFailed) return null;
    const idx = activeIdx >= 0 ? activeIdx : completedCount - 1;
    if (idx < 0) return null;

    const prev = idx > 0 ? progress.phases[idx - 1] : null;
    const current = progress.phases[idx];
    const next = idx < progress.phases.length - 1 ? progress.phases[idx + 1] : null;
    return { prev, current, next };
  }, [activeIdx, completedCount, progress.phases, progress.isComplete, progress.isFailed]);

  // Collapsed view
  if (!isExpanded) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-3">
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              {!progress.isComplete && !progress.isFailed && (
                <motion.div
                  className="w-3.5 h-3.5 rounded-full border-2 border-[oklch(0.65_0.25_180)] border-t-transparent flex-shrink-0"
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                />
              )}
              {progress.isComplete && (
                <CheckCircleIcon className="w-3.5 h-3.5 text-[oklch(0.65_0.25_150)] flex-shrink-0" />
              )}
              {progress.isFailed && (
                <XCircleIcon className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />
              )}
              <span className="text-sm text-[var(--foreground)] truncate">
                {progress.isFailed
                  ? 'Something went wrong'
                  : progress.isComplete
                    ? 'Ready to go'
                    : activePhase?.label || 'Planning...'}
              </span>
            </div>
            <div className="h-1 bg-[var(--border)] rounded-full overflow-hidden">
              <motion.div
                className={`h-full rounded-full ${
                  progress.isFailed
                    ? 'bg-red-500'
                    : 'bg-[oklch(0.65_0.25_180)]'
                }`}
                initial={{ width: 0 }}
                animate={{ width: `${progressPercent}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
          </div>
          <button
            onClick={onToggleExpand}
            className="p-1 rounded hover:bg-[var(--accent)] transition-colors flex-shrink-0"
          >
            <ChevronDownIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
          </button>
        </div>
      </div>
    );
  }

  // Expanded view — centered visor
  return (
    <div className="flex flex-col items-center justify-center px-4 py-16">
      <div className="w-full max-w-sm text-center">
        {/* Visor — sliding window of phases */}
        {visorPhases ? (
          <div className="space-y-2 mb-6">
            {/* Previous phase — faded */}
            <div className="h-6 overflow-hidden">
              <AnimatePresence mode="popLayout">
                {visorPhases.prev && (
                  <motion.div
                    key={visorPhases.prev.type}
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 0.35, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.3 }}
                    className="flex items-center justify-center gap-2"
                  >
                    <PhaseRow phase={visorPhases.prev} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Current phase — full opacity */}
            <AnimatePresence mode="popLayout">
              <motion.div
                key={visorPhases.current.type}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.3 }}
                className="flex items-center justify-center gap-2 py-1"
              >
                <PhaseRow phase={visorPhases.current} />
              </motion.div>
            </AnimatePresence>

            {/* Next phase — faded */}
            <div className="h-6 overflow-hidden">
              <AnimatePresence mode="popLayout">
                {visorPhases.next && (
                  <motion.div
                    key={visorPhases.next.type}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 0.35, y: 0 }}
                    exit={{ opacity: 0, y: 8 }}
                    transition={{ duration: 0.3 }}
                    className="flex items-center justify-center gap-2"
                  >
                    <PhaseRow phase={visorPhases.next} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        ) : (
          /* Terminal state — complete or failed */
          <div className="mb-6">
            <p className="text-base font-medium text-[var(--foreground)]">
              {progress.isFailed ? 'Something went wrong' : 'Ready to go'}
            </p>
          </div>
        )}

        {/* Progress dots */}
        <div className="flex items-center justify-center gap-1.5 mb-6">
          {progress.phases.map((phase, i) => (
            <div
              key={i}
              className={`rounded-full transition-all duration-300 ${
                phase.status === 'active'
                  ? 'w-4 h-1.5 bg-[oklch(0.65_0.25_180)]'
                  : phase.status === 'done'
                    ? 'w-1.5 h-1.5 bg-[oklch(0.65_0.25_150)]'
                    : phase.status === 'failed'
                      ? 'w-1.5 h-1.5 bg-red-500'
                      : 'w-1.5 h-1.5 bg-[var(--border)]'
              }`}
            />
          ))}
        </div>

        {/* Error Message */}
        {progress.error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 mb-4 text-left">
            <p className="text-sm text-red-500">{progress.error}</p>
          </div>
        )}

        {/* Step Names Preview */}
        {progress.stepNames && progress.stepNames.length > 0 && (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-3 mb-4 text-left">
            <p className="text-xs text-[var(--muted-foreground)] uppercase tracking-wide mb-2">
              {progress.stepCount} steps planned
            </p>
            <ul className="space-y-1">
              {progress.stepNames.map((name, i) => (
                <li key={i} className="text-sm text-[var(--foreground)] flex items-center gap-2">
                  <span className="text-xs text-[var(--muted-foreground)]">{i + 1}.</span>
                  {name}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Cancel */}
        {onCancel && !progress.isComplete && !progress.isFailed && (
          <button
            onClick={onCancel}
            className="inline-flex items-center gap-1 text-sm text-[var(--muted-foreground)] hover:text-red-500 transition-colors"
          >
            <XMarkIcon className="w-4 h-4" />
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
