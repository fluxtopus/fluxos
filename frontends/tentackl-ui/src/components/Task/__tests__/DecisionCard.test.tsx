import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DecisionCard } from '../DecisionCard';
import {
  createCheckpoint,
  createCheckpointWithExpiry,
  createCheckpointWithPreview,
} from '../../../test/fixtures/checkpoints';

describe('DecisionCard', () => {
  const mockOnApprove = vi.fn();
  const mockOnReject = vi.fn();

  beforeEach(() => {
    mockOnApprove.mockClear();
    mockOnReject.mockClear();
  });

  // DC-001: Renders checkpoint name and description
  it('renders checkpoint name and description', () => {
    const checkpoint = createCheckpoint({
      checkpoint_name: 'Send Email',
      description: 'About to send 50 marketing emails',
    });

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    expect(screen.getByText('Send Email')).toBeInTheDocument();
    expect(screen.getByText('About to send 50 marketing emails')).toBeInTheDocument();
  });

  // DC-002: Shows preview toggle when preview_data exists
  it('shows preview toggle when preview_data exists', () => {
    const checkpoint = createCheckpointWithPreview({ recipients: 50, subject: 'Newsletter' });

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    expect(screen.getByText('Show preview')).toBeInTheDocument();
  });

  // DC-003: Toggles preview data visibility on click
  it('toggles preview data visibility on click', async () => {
    const checkpoint = createCheckpointWithPreview({ action: 'delete', count: 10 });

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    // Initially hidden
    expect(screen.queryByText(/"action": "delete"/)).not.toBeInTheDocument();

    // Click to show
    await userEvent.click(screen.getByText('Show preview'));
    expect(screen.getByText(/"action": "delete"/)).toBeInTheDocument();
    expect(screen.getByText('Hide preview')).toBeInTheDocument();

    // Click to hide
    await userEvent.click(screen.getByText('Hide preview'));
    expect(screen.queryByText(/"action": "delete"/)).not.toBeInTheDocument();
    expect(screen.getByText('Show preview')).toBeInTheDocument();
  });

  // DC-004: Approve button calls onApprove callback
  it('approve button calls onApprove callback', async () => {
    const checkpoint = createCheckpoint();

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    await userEvent.click(screen.getByRole('button', { name: /approve/i }));

    expect(mockOnApprove).toHaveBeenCalledTimes(1);
    expect(mockOnApprove).toHaveBeenCalledWith(undefined, false);
  });

  // DC-005: Approve with learn preference enabled
  it('approve with learn preference enabled calls onApprove with learnPreference=true', async () => {
    const checkpoint = createCheckpoint();

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    // Check the "Remember this choice" checkbox
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: /approve/i }));

    expect(mockOnApprove).toHaveBeenCalledWith(undefined, true);
  });

  // DC-006: Reject button reveals reason input field
  it('reject button reveals reason input field', async () => {
    const checkpoint = createCheckpoint();

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    // Initially no textarea
    expect(screen.queryByPlaceholderText(/briefly explain/i)).not.toBeInTheDocument();

    // Click reject
    await userEvent.click(screen.getByRole('button', { name: /reject/i }));

    // Textarea appears
    expect(screen.getByPlaceholderText(/briefly explain/i)).toBeInTheDocument();
    expect(screen.getByText('Why are you rejecting this?')).toBeInTheDocument();
  });

  // DC-007: Cancel reject hides input and clears state
  it('cancel reject hides input and clears state', async () => {
    const checkpoint = createCheckpoint();

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    // Show reject input
    await userEvent.click(screen.getByRole('button', { name: /reject/i }));

    // Type some reason
    const textarea = screen.getByPlaceholderText(/briefly explain/i);
    await userEvent.type(textarea, 'Not appropriate');

    // Cancel
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }));

    // Input should be hidden
    expect(screen.queryByPlaceholderText(/briefly explain/i)).not.toBeInTheDocument();

    // Show again - should be empty
    await userEvent.click(screen.getByRole('button', { name: /reject/i }));
    expect(screen.getByPlaceholderText(/briefly explain/i)).toHaveValue('');
  });

  // DC-008: Submit reject with reason text
  it('submit reject with reason text calls onReject with reason', async () => {
    const checkpoint = createCheckpoint();

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    // Show reject input
    await userEvent.click(screen.getByRole('button', { name: /reject/i }));

    // Type reason and submit
    await userEvent.type(screen.getByPlaceholderText(/briefly explain/i), 'Wrong recipients');
    await userEvent.click(screen.getByRole('button', { name: /^reject$/i }));

    expect(mockOnReject).toHaveBeenCalledWith('Wrong recipients', false);
  });

  // DC-009: Shows expiry warning when expires_at set
  it('shows expiry warning when expires_at is set', () => {
    const checkpoint = createCheckpointWithExpiry(30); // 30 minutes from now

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    expect(screen.getByText(/expires/i)).toBeInTheDocument();
  });

  // DC-010: Empty preview_data hides toggle button
  it('empty preview_data hides toggle button', () => {
    const checkpoint = createCheckpoint({ preview_data: {} });

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    expect(screen.queryByText('Show preview')).not.toBeInTheDocument();
  });

  // DC-011: Whitespace-only reason disables submit
  it('whitespace-only reason disables submit button', async () => {
    const checkpoint = createCheckpoint();

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    // Show reject input
    await userEvent.click(screen.getByRole('button', { name: /reject/i }));

    // Type whitespace only
    await userEvent.type(screen.getByPlaceholderText(/briefly explain/i), '   ');

    // Submit button should be disabled
    const submitButton = screen.getByRole('button', { name: /^reject$/i });
    expect(submitButton).toBeDisabled();

    // Clicking should not call onReject
    await userEvent.click(submitButton);
    expect(mockOnReject).not.toHaveBeenCalled();
  });

  // DC-012: Very long checkpoint name handles overflow
  it('very long checkpoint name handles overflow via CSS', () => {
    const longName = 'A'.repeat(200);
    const checkpoint = createCheckpoint({ checkpoint_name: longName });

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    const nameElement = screen.getByText(longName);
    expect(nameElement).toBeInTheDocument();
    // The parent container has min-w-0 for truncation handling
    expect(nameElement.parentElement).toHaveClass('min-w-0');
  });

  // DC-013: Large preview_data enables scrolling
  it('large preview_data displays in scrollable container', async () => {
    const largePreview = {
      items: Array.from({ length: 100 }, (_, i) => ({ id: i, name: `Item ${i}` })),
    };
    const checkpoint = createCheckpointWithPreview(largePreview);

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
      />
    );

    await userEvent.click(screen.getByText('Show preview'));

    // The pre element should have overflow-x-auto
    const preElement = screen.getByText(/Item 0/).closest('pre');
    expect(preElement).toHaveClass('overflow-x-auto');
  });

  // DC-014: isProcessing disables approve button
  it('isProcessing disables approve button', () => {
    const checkpoint = createCheckpoint();

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
        isProcessing={true}
      />
    );

    expect(screen.getByRole('button', { name: /approve/i })).toBeDisabled();
  });

  // DC-015: isProcessing disables reject button
  it('isProcessing disables reject button', () => {
    const checkpoint = createCheckpoint();

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
        isProcessing={true}
      />
    );

    expect(screen.getByRole('button', { name: /reject/i })).toBeDisabled();
  });

  // DC-016: isProcessing shows loading spinner
  it('isProcessing shows loading spinner on approve button', () => {
    const checkpoint = createCheckpoint();

    render(
      <DecisionCard
        checkpoint={checkpoint}
        onApprove={mockOnApprove}
        onReject={mockOnReject}
        isProcessing={true}
      />
    );

    // The spinner is a div with animate-spin class
    const approveButton = screen.getByRole('button', { name: /approve/i });
    const spinner = approveButton.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();
  });
});
