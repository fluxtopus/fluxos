import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RecoveryCard } from '../RecoveryCard';
import {
  createRetryProposal,
  createFallbackProposal,
  createSkipProposal,
  createAbortProposal,
  createReplanProposal,
  createAutoAppliedRecovery,
} from '../../../test/fixtures/checkpoints';

describe('RecoveryCard', () => {
  const mockOnAccept = vi.fn();
  const mockOnReject = vi.fn();

  beforeEach(() => {
    mockOnAccept.mockClear();
    mockOnReject.mockClear();
  });

  // RC-001: RETRY proposal shows correct icon/text
  it('RETRY proposal shows retry icon and title', () => {
    render(
      <RecoveryCard
        proposal={createRetryProposal()}
        onAccept={mockOnAccept}
        onReject={mockOnReject}
      />
    );

    expect(screen.getByText('Retry this step')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  // RC-002: FALLBACK proposal shows correct icon/text
  it('FALLBACK proposal shows alternative title', () => {
    render(
      <RecoveryCard
        proposal={createFallbackProposal()}
        onAccept={mockOnAccept}
        onReject={mockOnReject}
      />
    );

    expect(screen.getByText('Use alternative')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /use alternative/i })).toBeInTheDocument();
  });

  // RC-003: SKIP proposal shows correct icon/text
  it('SKIP proposal shows skip title', () => {
    render(
      <RecoveryCard
        proposal={createSkipProposal()}
        onAccept={mockOnAccept}
        onReject={mockOnReject}
      />
    );

    expect(screen.getByText('Skip this step')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /skip/i })).toBeInTheDocument();
  });

  // RC-004: ABORT proposal shows correct icon/text
  it('ABORT proposal shows stop title', () => {
    render(
      <RecoveryCard
        proposal={createAbortProposal()}
        onAccept={mockOnAccept}
        onReject={mockOnReject}
      />
    );

    expect(screen.getByText('Stop execution')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument();
  });

  // RC-005: REPLAN proposal shows correct icon/text
  it('REPLAN proposal shows adjust plan title', () => {
    render(
      <RecoveryCard
        proposal={createReplanProposal()}
        onAccept={mockOnAccept}
        onReject={mockOnReject}
      />
    );

    expect(screen.getByText('Adjust the plan')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /adjust plan/i })).toBeInTheDocument();
  });

  // RC-006: Auto-applied shows info-only (no buttons)
  it('auto-applied recovery shows info without action buttons', () => {
    render(
      <RecoveryCard
        proposal={createAutoAppliedRecovery()}
        onAccept={mockOnAccept}
        onReject={mockOnReject}
      />
    );

    expect(screen.getByText(/auto-recovered/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /dismiss/i })).not.toBeInTheDocument();
  });

  // RC-007: Non-auto shows accept/dismiss buttons
  it('non-auto proposal shows accept and dismiss buttons', () => {
    render(
      <RecoveryCard
        proposal={createRetryProposal()}
        onAccept={mockOnAccept}
        onReject={mockOnReject}
      />
    );

    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /dismiss/i })).toBeInTheDocument();
  });

  // RC-008: Accept button calls onAccept callback
  it('accept button calls onAccept callback', async () => {

    render(
      <RecoveryCard
        proposal={createRetryProposal()}
        onAccept={mockOnAccept}
        onReject={mockOnReject}
      />
    );

    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    expect(mockOnAccept).toHaveBeenCalledTimes(1);
  });

  // RC-009: Dismiss button calls onReject callback
  it('dismiss button calls onReject callback', async () => {

    render(
      <RecoveryCard
        proposal={createRetryProposal()}
        onAccept={mockOnAccept}
        onReject={mockOnReject}
      />
    );

    await userEvent.click(screen.getByRole('button', { name: /dismiss/i }));

    expect(mockOnReject).toHaveBeenCalledTimes(1);
  });

  // RC-010: isProcessing shows spinner on accept
  it('isProcessing shows spinner and disables buttons', () => {
    render(
      <RecoveryCard
        proposal={createRetryProposal()}
        onAccept={mockOnAccept}
        onReject={mockOnReject}
        isProcessing={true}
      />
    );

    expect(screen.getByText('Processing...')).toBeInTheDocument();
    // Buttons should be disabled
    expect(screen.getByRole('button', { name: /processing/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /dismiss/i })).toBeDisabled();
  });

  // Additional test: stepName is displayed when provided
  it('displays stepName when provided', () => {
    render(
      <RecoveryCard
        proposal={createRetryProposal()}
        stepName="Fetch User Data"
        onAccept={mockOnAccept}
        onReject={mockOnReject}
      />
    );

    expect(screen.getByText('For: Fetch User Data')).toBeInTheDocument();
  });

  // Additional test: proposal reason is displayed
  it('displays the proposal reason', () => {
    const proposal = createRetryProposal();
    render(
      <RecoveryCard
        proposal={proposal}
        onAccept={mockOnAccept}
        onReject={mockOnReject}
      />
    );

    expect(screen.getByText(proposal.reason)).toBeInTheDocument();
  });
});
