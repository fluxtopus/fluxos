import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StructuredDataRenderer } from '../StructuredDataRenderer';
import type { StructuredDataContent } from '../../../../types/structured-data';

describe('StructuredDataRenderer', () => {
  // Test fixtures
  const eventData: StructuredDataContent = {
    object_type: 'event',
    data: [
      {
        id: '1',
        title: 'Team Standup',
        start: '2026-01-22T09:00:00Z',
        end: '2026-01-22T09:30:00Z',
        location: 'Room 101',
        attendees: ['alice@example.com', 'bob@example.com'],
      },
      {
        id: '2',
        title: 'Product Review',
        start: '2026-01-22T14:00:00Z',
        end: '2026-01-22T15:00:00Z',
      },
    ],
    total_count: 2,
    total_time_ms: 150,
  };

  const contactData: StructuredDataContent = {
    object_type: 'contact',
    data: [
      {
        id: '1',
        name: 'Alice Johnson',
        email: 'alice@example.com',
        phone: '+1-555-0100',
        company: 'Acme Corp',
      },
      {
        id: '2',
        name: 'Bob Smith',
        email: 'bob@example.com',
      },
    ],
    total_count: 2,
    total_time_ms: 100,
  };

  const genericData: StructuredDataContent = {
    object_type: 'custom_type',
    data: [
      { id: '1', field_a: 'Value A', field_b: 123 },
      { id: '2', field_a: 'Value B', field_b: 456 },
    ],
    total_count: 2,
  };

  // SDR-001: Renders event data with CalendarEventCards
  it('renders event data with CalendarEventCards', () => {
    render(<StructuredDataRenderer content={eventData} />);

    expect(screen.getByText('Team Standup')).toBeInTheDocument();
    expect(screen.getByText('Product Review')).toBeInTheDocument();
    expect(screen.getByText('Room 101')).toBeInTheDocument();
  });

  // SDR-002: Renders contact data with ContactCards
  it('renders contact data with ContactCards', () => {
    render(<StructuredDataRenderer content={contactData} />);

    expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
    expect(screen.getByText('Bob Smith')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    // Company appears in the contact card
    expect(screen.getAllByText('Acme Corp').length).toBeGreaterThan(0);
  });

  // SDR-003: Renders generic data with DataTable
  it('renders generic data with DataTable', () => {
    render(<StructuredDataRenderer content={genericData} />);

    // Table should show column headers (formatHeader converts field_a to "Field a")
    expect(screen.getByText('Field a')).toBeInTheDocument();
    expect(screen.getByText('Field b')).toBeInTheDocument();

    // Table should show values
    expect(screen.getByText('Value A')).toBeInTheDocument();
    expect(screen.getByText('123')).toBeInTheDocument();
  });

  // SDR-004: Shows metadata header with item count and time
  it('shows metadata header with item count and time', () => {
    render(<StructuredDataRenderer content={eventData} />);

    expect(screen.getByText('2 items')).toBeInTheDocument();
    expect(screen.getByText('150ms')).toBeInTheDocument();
    expect(screen.getByText('event')).toBeInTheDocument();
  });

  // SDR-005: Shows view toggle buttons
  it('shows view toggle buttons', () => {
    render(<StructuredDataRenderer content={eventData} />);

    expect(screen.getByTitle('Card view')).toBeInTheDocument();
    expect(screen.getByTitle('Table view')).toBeInTheDocument();
    expect(screen.getByTitle('JSON view')).toBeInTheDocument();
  });

  // SDR-006: Switches to table view when button clicked
  it('switches to table view when button clicked', () => {
    render(<StructuredDataRenderer content={eventData} />);

    // Initially in card view
    expect(screen.getByText('Team Standup')).toBeInTheDocument();

    // Click table view
    fireEvent.click(screen.getByTitle('Table view'));

    // Should show table with headers
    expect(screen.getByText('Title')).toBeInTheDocument();
    expect(screen.getByText('Start')).toBeInTheDocument();
  });

  // SDR-007: Switches to JSON view when button clicked
  it('switches to JSON view when button clicked', () => {
    render(<StructuredDataRenderer content={eventData} />);

    // Click JSON view
    fireEvent.click(screen.getByTitle('JSON view'));

    // Should show JSON content
    expect(screen.getByText(/"id": "1"/)).toBeInTheDocument();
    expect(screen.getByText(/"title": "Team Standup"/)).toBeInTheDocument();
  });

  // SDR-008: Shows empty state for empty data
  it('shows empty state for empty data', () => {
    const emptyData: StructuredDataContent = {
      object_type: 'event',
      data: [],
      total_count: 0,
    };

    render(<StructuredDataRenderer content={emptyData} />);

    expect(screen.getByText('No data to display')).toBeInTheDocument();
  });

  // SDR-009: Card view disabled for generic types
  it('disables card view for generic types', () => {
    render(<StructuredDataRenderer content={genericData} />);

    const cardButton = screen.getByTitle('Card view');
    expect(cardButton).toBeDisabled();
  });

  // SDR-010: Defaults to card view for events
  it('defaults to card view for events', () => {
    render(<StructuredDataRenderer content={eventData} />);

    // Card content should be visible (not table headers)
    expect(screen.getByText('Team Standup')).toBeInTheDocument();
    // Table-specific headers should not be present
    expect(screen.queryByRole('columnheader')).not.toBeInTheDocument();
  });

  // SDR-011: Defaults to table view for generic types
  it('defaults to table view for generic types', () => {
    render(<StructuredDataRenderer content={genericData} />);

    // Table headers should be visible (formatHeader converts field_a to "Field a")
    expect(screen.getByText('Field a')).toBeInTheDocument();
    expect(screen.getByText('Field b')).toBeInTheDocument();
  });
});

describe('isStructuredDataContent', () => {
  it('returns true for valid structured data', async () => {
    const { isStructuredDataContent } = await import(
      '../../../../types/structured-data'
    );

    const content = {
      object_type: 'event',
      data: [{ id: '1' }],
    };

    expect(isStructuredDataContent(content)).toBe(true);
  });

  it('returns false for content without object_type', async () => {
    const { isStructuredDataContent } = await import(
      '../../../../types/structured-data'
    );

    const content = {
      data: [{ id: '1' }],
    };

    expect(isStructuredDataContent(content)).toBe(false);
  });

  it('returns false for content without data array', async () => {
    const { isStructuredDataContent } = await import(
      '../../../../types/structured-data'
    );

    const content = {
      object_type: 'event',
    };

    expect(isStructuredDataContent(content)).toBe(false);
  });

  it('returns false for null', async () => {
    const { isStructuredDataContent } = await import(
      '../../../../types/structured-data'
    );

    expect(isStructuredDataContent(null)).toBe(false);
  });

  it('returns false for primitive values', async () => {
    const { isStructuredDataContent } = await import(
      '../../../../types/structured-data'
    );

    expect(isStructuredDataContent('string')).toBe(false);
    expect(isStructuredDataContent(123)).toBe(false);
  });
});
