import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DecisionsQueue } from '../DecisionsQueue';
import { useTaskStore } from '../../../store/taskStore';
import {
  createCheckpoint,
  createMultipleCheckpoints,
} from '../../../test/fixtures/checkpoints';
import type { Checkpoint } from '../../../types/task';

// Mock the store
vi.mock('../../../store/taskStore');

// Mock Next.js Link component
vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

const mockUseTaskStore = useTaskStore as unknown as ReturnType<typeof vi.fn>;

describe('DecisionsQueue', () => {
  const defaultStore = {
    pendingCheckpoints: [] as Checkpoint[],
    loading: false,
    errorMessage: null as string | null,
    loadPendingCheckpoints: vi.fn(),
    approveCheckpoint: vi.fn(),
    rejectCheckpoint: vi.fn(),
  };

  beforeEach(() => {
    mockUseTaskStore.mockReturnValue(defaultStore);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // DQ-001: Loads pending checkpoints on mount
  it('loads pending checkpoints on mount', () => {
    render(<DecisionsQueue />);

    expect(defaultStore.loadPendingCheckpoints).toHaveBeenCalledTimes(1);
  });

  // DQ-002: Renders DecisionCard for each checkpoint
  it('renders DecisionCard for each checkpoint', () => {
    const checkpoints = createMultipleCheckpoints(3);
    mockUseTaskStore.mockReturnValue({
      ...defaultStore,
      pendingCheckpoints: checkpoints,
    });

    render(<DecisionsQueue />);

    // Each checkpoint should render its name
    checkpoints.forEach((checkpoint) => {
      expect(screen.getByText(checkpoint.checkpoint_name)).toBeInTheDocument();
    });
  });

  // DQ-003: Each card links to task detail page
  it('each card links to task detail page', () => {
    const checkpoints = [
      createCheckpoint({ task_id: 'task-abc', step_id: 'step-1' }),
      createCheckpoint({ task_id: 'task-xyz', step_id: 'step-2' }),
    ];
    mockUseTaskStore.mockReturnValue({
      ...defaultStore,
      pendingCheckpoints: checkpoints,
    });

    render(<DecisionsQueue />);

    const links = screen.getAllByRole('link', { name: /view full task/i });
    expect(links[0]).toHaveAttribute('href', '/tasks/task-abc');
    expect(links[1]).toHaveAttribute('href', '/tasks/task-xyz');
  });

  // DQ-004: Approve propagates to store action
  it('approve propagates to store action', async () => {
    const checkpoint = createCheckpoint({ task_id: 'task-1', step_id: 'step-1' });
    mockUseTaskStore.mockReturnValue({
      ...defaultStore,
      pendingCheckpoints: [checkpoint],
    });

    render(<DecisionsQueue />);

    await userEvent.click(screen.getByRole('button', { name: /approve/i }));

    expect(defaultStore.approveCheckpoint).toHaveBeenCalledTimes(1);
  });

  // DQ-005: Reject propagates to store action
  it('reject propagates to store action', async () => {
    const checkpoint = createCheckpoint({ task_id: 'task-1', step_id: 'step-1' });
    mockUseTaskStore.mockReturnValue({
      ...defaultStore,
      pendingCheckpoints: [checkpoint],
    });

    render(<DecisionsQueue />);

    // Click reject to show input
    await userEvent.click(screen.getByRole('button', { name: /reject/i }));

    // Enter reason and submit
    await userEvent.type(screen.getByPlaceholderText(/briefly explain/i), 'Not ready');
    await userEvent.click(screen.getByRole('button', { name: /^reject$/i }));

    expect(defaultStore.rejectCheckpoint).toHaveBeenCalledTimes(1);
  });

  // DQ-006: Loading state shows spinner
  it('loading state shows spinner when no checkpoints', () => {
    mockUseTaskStore.mockReturnValue({
      ...defaultStore,
      loading: true,
      pendingCheckpoints: [],
    });

    render(<DecisionsQueue />);

    expect(screen.getByText('Loading decisions...')).toBeInTheDocument();
    // Spinner has animate-spin class
    const spinner = document.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();
  });

  // DQ-007: Empty state shows inbox icon and message
  it('empty state shows inbox icon and message', () => {
    mockUseTaskStore.mockReturnValue({
      ...defaultStore,
      loading: false,
      pendingCheckpoints: [],
    });

    render(<DecisionsQueue />);

    expect(screen.getByText('No pending decisions')).toBeInTheDocument();
    expect(
      screen.getByText(/when tasks need your approval/i)
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /view all tasks/i })).toHaveAttribute(
      'href',
      '/tasks'
    );
  });

  // DQ-008: Error state shows error and retry button
  it('error state shows error and retry button', () => {
    mockUseTaskStore.mockReturnValue({
      ...defaultStore,
      loading: false,
      errorMessage: 'Failed to load checkpoints',
    });

    render(<DecisionsQueue />);

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Failed to load checkpoints')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  // DQ-009: Retry button reloads checkpoints
  it('retry button reloads checkpoints', async () => {
    mockUseTaskStore.mockReturnValue({
      ...defaultStore,
      loading: false,
      errorMessage: 'Failed to load checkpoints',
    });

    render(<DecisionsQueue />);

    // Clear the initial call counter
    defaultStore.loadPendingCheckpoints.mockClear();

    await userEvent.click(screen.getByRole('button', { name: /try again/i }));

    expect(defaultStore.loadPendingCheckpoints).toHaveBeenCalledTimes(1);
  });
});
