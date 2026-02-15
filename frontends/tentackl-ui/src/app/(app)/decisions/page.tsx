'use client';

import { DecisionsQueue } from '../../../components/Task/DecisionsQueue';

/**
 * Decisions page - pending checkpoints needing approval.
 * Quick inbox, not a workflow management page.
 */
export default function DecisionsPage() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[var(--foreground)]">
          Decisions
        </h1>
        <p className="text-sm text-[var(--muted-foreground)] mt-1">
          Items waiting for your approval
        </p>
      </div>

      {/* Queue */}
      <DecisionsQueue />
    </div>
  );
}
