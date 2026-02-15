import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ErrorCard } from '../ErrorCard';
import { createTaskError, createPermanentError } from '../../../test/fixtures/checkpoints';

describe('ErrorCard', () => {
  const mockOnRetry = vi.fn();
  const mockOnDismiss = vi.fn();
  const mockOnTryDifferent = vi.fn();

  beforeEach(() => {
    mockOnRetry.mockClear();
    mockOnDismiss.mockClear();
    mockOnTryDifferent.mockClear();
  });

  // EC-001: String error converts to friendly format
  it('string error converts to friendly format', () => {
    render(
      <ErrorCard
        error="Request timeout - service unavailable"
        onRetry={mockOnRetry}
      />
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText(/taking longer than expected/i)).toBeInTheDocument();
  });

  // EC-002: DelegationError object displays all fields
  it('DelegationError object displays friendly message and suggestions', () => {
    const error = createTaskError({
      friendlyMessage: 'Database connection lost',
      whatToDoNext: ['Check network', 'Retry in a moment'],
    });

    render(
      <ErrorCard
        error={error}
        onRetry={mockOnRetry}
      />
    );

    expect(screen.getByText('Database connection lost')).toBeInTheDocument();
    expect(screen.getByText('• Check network')).toBeInTheDocument();
    expect(screen.getByText('• Retry in a moment')).toBeInTheDocument();
  });

  // EC-003: Suggestions list renders correctly
  it('suggestions list renders all items', () => {
    const error = createTaskError({
      whatToDoNext: ['Try again', 'Wait a moment', 'Contact support'],
    });

    render(
      <ErrorCard
        error={error}
        onRetry={mockOnRetry}
      />
    );

    expect(screen.getByText('• Try again')).toBeInTheDocument();
    expect(screen.getByText('• Wait a moment')).toBeInTheDocument();
    expect(screen.getByText('• Contact support')).toBeInTheDocument();
  });

  // EC-004: Retry button shown when canRetry=true
  it('retry button shown when canRetry is true', () => {
    const error = createTaskError({ canRetry: true });

    render(
      <ErrorCard
        error={error}
        onRetry={mockOnRetry}
      />
    );

    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('retry button hidden when canRetry is false', () => {
    const error = createPermanentError(); // canRetry: false

    render(
      <ErrorCard
        error={error}
        onRetry={mockOnRetry}
      />
    );

    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
  });

  // EC-005: Alternative button when hasAlternative
  it('alternative button shown when hasAlternative is true', () => {
    const error = createTaskError({ hasAlternative: true });

    render(
      <ErrorCard
        error={error}
        onTryDifferent={mockOnTryDifferent}
      />
    );

    expect(screen.getByRole('button', { name: /try a different approach/i })).toBeInTheDocument();
  });

  it('alternative button hidden when hasAlternative is false', () => {
    const error = createTaskError({ hasAlternative: false });

    render(
      <ErrorCard
        error={error}
        onTryDifferent={mockOnTryDifferent}
      />
    );

    expect(screen.queryByRole('button', { name: /try a different approach/i })).not.toBeInTheDocument();
  });

  // EC-006: Technical details are collapsible
  it('technical details are collapsible', async () => {

    const error = createTaskError({
      technicalDetails: 'Error code: CONN_REFUSED at line 42',
    });

    render(
      <ErrorCard
        error={error}
        onRetry={mockOnRetry}
      />
    );

    // Details should be in a collapsible
    const details = screen.getByText('Technical details');
    expect(details).toBeInTheDocument();

    // Click to expand
    await userEvent.click(details);

    // Technical details should be visible
    expect(screen.getByText(/Error code: CONN_REFUSED/)).toBeInTheDocument();
  });

  // EC-007: Dismiss button removes card
  it('dismiss button calls onDismiss callback', async () => {

    const error = createTaskError();

    render(
      <ErrorCard
        error={error}
        onDismiss={mockOnDismiss}
      />
    );

    // Find dismiss button (X icon button)
    const dismissButton = screen.getByRole('button', { name: '' }); // X button has no text
    await userEvent.click(dismissButton);

    expect(mockOnDismiss).toHaveBeenCalledTimes(1);
  });

  // Additional test: retry button click calls onRetry
  it('retry button click calls onRetry', async () => {

    const error = createTaskError({ canRetry: true });

    render(
      <ErrorCard
        error={error}
        onRetry={mockOnRetry}
      />
    );

    await userEvent.click(screen.getByRole('button', { name: /try again/i }));

    expect(mockOnRetry).toHaveBeenCalledTimes(1);
  });

  // Additional test: isRetrying shows loading state
  it('isRetrying shows loading spinner', () => {
    const error = createTaskError({ canRetry: true });

    render(
      <ErrorCard
        error={error}
        onRetry={mockOnRetry}
        isRetrying={true}
      />
    );

    expect(screen.getByText('Retrying...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retrying/i })).toBeDisabled();
  });
});
