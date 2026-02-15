'use client';

import { useState, useMemo, useCallback } from 'react';
import {
  TableCellsIcon,
  Squares2X2Icon,
  CodeBracketIcon,
  ClockIcon,
  CalendarIcon,
  CalendarDaysIcon,
  ArrowsPointingOutIcon,
} from '@heroicons/react/24/outline';
import { parseISO, isValid } from 'date-fns';
import type {
  ViewMode,
  StructuredDataContent,
  CalendarEvent,
  Contact,
} from '../../../types/structured-data';
import { updateObject } from '../../../services/workspaceService';
import { CalendarEventCard } from './CalendarEventCard';
import { ContactCard } from './ContactCard';
import { DataTable, inferColumns, formatCellValue, formatHeader } from './DataTable';
import { DataTableModal } from './DataTableModal';
import { CalendarDayView } from './CalendarDayView';
import { CalendarWeekView } from './CalendarWeekView';
import { EditEventModal } from './EditEventModal';

/**
 * Parse a date string safely.
 */
function parseDate(dateStr: string): Date | null {
  if (!dateStr) return null;
  const date = parseISO(dateStr);
  if (!isValid(date)) {
    const fallback = new Date(dateStr);
    return isValid(fallback) ? fallback : null;
  }
  return date;
}

interface StructuredDataRendererProps {
  content: StructuredDataContent;
  defaultView?: ViewMode;
  onDataChange?: () => void;
}

/**
 * View mode toggle button.
 */
function ViewToggle({
  mode,
  activeMode,
  icon: Icon,
  label,
  onClick,
  disabled = false,
}: {
  mode: ViewMode;
  activeMode: ViewMode;
  icon: typeof TableCellsIcon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  const isActive = mode === activeMode;

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={label}
      className={`
        p-1.5 rounded transition-colors
        ${
          isActive
            ? 'bg-[oklch(0.65_0.25_180/0.15)] text-[oklch(0.65_0.25_180)]'
            : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)]'
        }
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
      `}
    >
      <Icon className="w-4 h-4" />
    </button>
  );
}

/**
 * Check if object_type has a specialized card renderer.
 */
function hasCardRenderer(objectType: string | undefined): boolean {
  return objectType === 'event' || objectType === 'contact';
}

/**
 * Check if object_type supports calendar views (day/week).
 */
function supportsCalendarViews(objectType: string | undefined): boolean {
  return objectType === 'event';
}

/**
 * Inline table preview showing a few rows with an expand button.
 */
function TablePreview({
  data,
  onExpand,
}: {
  data: Record<string, unknown>[];
  onExpand: () => void;
}) {
  const PREVIEW_ROWS = 3;
  const columns = useMemo(() => inferColumns(data, 4), [data]);
  const previewData = data.slice(0, PREVIEW_ROWS);

  return (
    <div className="rounded-lg border border-[var(--border)]">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--muted)]/50 border-b border-[var(--border)]">
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-3 py-2 text-left font-medium text-[var(--muted-foreground)] text-xs"
                >
                  {formatHeader(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {previewData.map((row, idx) => (
              <tr
                key={(row.id as string) || idx}
                className="border-b border-[var(--border)] last:border-0"
              >
                {columns.map((col) => (
                  <td
                    key={col}
                    className="px-3 py-1.5 text-[var(--foreground)] text-xs max-w-[160px] truncate"
                  >
                    {formatCellValue(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        onClick={onExpand}
        className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] bg-[var(--muted)]/30 hover:bg-[var(--muted)]/50 border-t border-[var(--border)] transition-colors"
      >
        <ArrowsPointingOutIcon className="w-3.5 h-3.5" />
        View all {data.length} rows
      </button>
    </div>
  );
}

/**
 * StructuredDataRenderer - Main component for displaying structured data.
 *
 * Reads object_type from backend and renders the appropriate view.
 */
export function StructuredDataRenderer({
  content,
  defaultView = 'card',
  onDataChange,
}: StructuredDataRendererProps) {
  const objectType = content.object_type;
  const data = (content.data || []) as Record<string, unknown>[];

  // Determine initial view mode based on object_type
  const getInitialView = (): ViewMode => {
    if (hasCardRenderer(objectType)) {
      return defaultView;
    }
    // Default to table for generic types
    return data.length > 0 ? 'table' : 'json';
  };

  const [viewMode, setViewMode] = useState<ViewMode>(getInitialView);

  // Table modal state
  const [isTableModalOpen, setIsTableModalOpen] = useState(false);

  // Edit modal state
  const [editingEvent, setEditingEvent] = useState<CalendarEvent | null>(null);
  const [editingObjectId, setEditingObjectId] = useState<string | null>(null);

  // Handle edit click
  const handleEditEvent = useCallback((event: CalendarEvent, objectId: string) => {
    setEditingEvent(event);
    setEditingObjectId(objectId);
  }, []);

  // Handle save
  const handleSaveEvent = useCallback(async (objectId: string, eventData: Partial<CalendarEvent>) => {
    await updateObject(objectId, eventData);
    setEditingEvent(null);
    setEditingObjectId(null);
    // Notify parent to refresh data
    onDataChange?.();
  }, [onDataChange]);

  // Empty state
  if (data.length === 0) {
    return (
      <div className="p-4 text-center text-sm text-[var(--muted-foreground)]">
        No data to display
      </div>
    );
  }

  // Helper to extract events from data
  const getEvents = (): CalendarEvent[] => {
    return data.map((item) => {
      // Workspace objects have event data nested in 'data' field
      // Unwrap if present, otherwise use the item directly
      return (item.data && typeof item.data === 'object')
        ? { ...item.data as CalendarEvent, id: item.id as string }
        : item as unknown as CalendarEvent;
    });
  };

  // Find the earliest event date to initialize calendar views
  // This ensures the calendar starts where the first event is, not at today
  const firstEventDate = useMemo((): Date | undefined => {
    if (objectType !== 'event' || data.length === 0) return undefined;

    let earliest: Date | null = null;
    for (const item of data) {
      const eventData = (item.data && typeof item.data === 'object')
        ? item.data as CalendarEvent
        : item as unknown as CalendarEvent;

      const startStr = eventData.start;
      if (startStr) {
        const startDate = parseDate(startStr);
        if (startDate && (!earliest || startDate < earliest)) {
          earliest = startDate;
        }
      }
    }
    return earliest || undefined;
  }, [data, objectType]);

  const renderContent = () => {
    // JSON view - always available
    if (viewMode === 'json') {
      const contentStr = JSON.stringify(data, null, 2);
      if (contentStr.length > 5000) {
        return (
          <div className="p-4 text-sm text-[var(--muted-foreground)]">
            Data too large to display as JSON ({data.length} items)
          </div>
        );
      }
      return (
        <pre className="text-xs overflow-x-auto bg-[var(--muted)] p-3 rounded-lg text-[var(--foreground)]">
          {contentStr}
        </pre>
      );
    }

    // Table view - show inline preview with expand button
    if (viewMode === 'table') {
      return (
        <TablePreview data={data} onExpand={() => setIsTableModalOpen(true)} />
      );
    }

    // Calendar day view (only for events)
    if (viewMode === 'day' && objectType === 'event') {
      return <CalendarDayView events={getEvents()} initialDate={firstEventDate} />;
    }

    // Calendar week view (only for events)
    if (viewMode === 'week' && objectType === 'event') {
      return <CalendarWeekView events={getEvents()} initialDate={firstEventDate} />;
    }

    // Card view - use type-specific renderer based on object_type
    switch (objectType) {
      case 'event':
        return (
          <div className="space-y-3">
            {data.map((item, i) => {
              // Workspace objects have event data nested in 'data' field
              // Unwrap if present, otherwise use the item directly
              const eventData = (item.data && typeof item.data === 'object')
                ? { ...item.data as CalendarEvent, id: item.id as string }
                : item as unknown as CalendarEvent;
              const objectId = item.id as string;
              return (
                <CalendarEventCard
                  key={eventData.id || i}
                  event={eventData}
                  objectId={objectId}
                  index={i}
                  onEdit={handleEditEvent}
                />
              );
            })}
          </div>
        );

      case 'contact':
        return (
          <div className="space-y-3">
            {data.map((item, i) => {
              // Workspace objects have contact data nested in 'data' field
              // Unwrap if present, otherwise use the item directly
              const contactData = (item.data && typeof item.data === 'object')
                ? { ...item.data as Contact, id: item.id as string }
                : item as unknown as Contact;
              return (
                <ContactCard key={contactData.id || i} contact={contactData} index={i} />
              );
            })}
          </div>
        );

      default:
        // Generic types fall back to table preview
        return (
          <TablePreview data={data} onExpand={() => setIsTableModalOpen(true)} />
        );
    }
  };

  return (
    <div className="space-y-3">
      {/* Header with metadata and view toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
          {content.total_count !== undefined && (
            <span>{content.total_count} items</span>
          )}
          {content.total_time_ms !== undefined && (
            <span className="inline-flex items-center gap-1">
              <ClockIcon className="w-3 h-3" />
              {content.total_time_ms}ms
            </span>
          )}
          {objectType && (
            <span className="px-1.5 py-0.5 bg-[var(--muted)] rounded text-[10px]">
              {objectType}
            </span>
          )}
        </div>

        {/* View mode toggle */}
        <div className="flex items-center gap-1 p-1 bg-[var(--muted)]/50 rounded-lg">
          <ViewToggle
            mode="card"
            activeMode={viewMode}
            icon={Squares2X2Icon}
            label="Card view"
            onClick={() => setViewMode('card')}
            disabled={!hasCardRenderer(objectType)}
          />
          <ViewToggle
            mode="day"
            activeMode={viewMode}
            icon={CalendarIcon}
            label="Day view"
            onClick={() => setViewMode('day')}
            disabled={!supportsCalendarViews(objectType)}
          />
          <ViewToggle
            mode="week"
            activeMode={viewMode}
            icon={CalendarDaysIcon}
            label="Week view"
            onClick={() => setViewMode('week')}
            disabled={!supportsCalendarViews(objectType)}
          />
          <ViewToggle
            mode="table"
            activeMode={viewMode}
            icon={TableCellsIcon}
            label="Table view"
            onClick={() => setViewMode('table')}
          />
          <ViewToggle
            mode="json"
            activeMode={viewMode}
            icon={CodeBracketIcon}
            label="JSON view"
            onClick={() => setViewMode('json')}
          />
        </div>
      </div>

      {/* Content */}
      {renderContent()}

      {/* Table Modal */}
      <DataTableModal
        data={data}
        isOpen={isTableModalOpen}
        onClose={() => setIsTableModalOpen(false)}
        title={objectType ? `${objectType.charAt(0).toUpperCase() + objectType.slice(1)}s` : undefined}
        itemCount={data.length}
      />

      {/* Edit Event Modal */}
      {editingEvent && editingObjectId && (
        <EditEventModal
          event={editingEvent}
          objectId={editingObjectId}
          isOpen={true}
          onClose={() => {
            setEditingEvent(null);
            setEditingObjectId(null);
          }}
          onSave={handleSaveEvent}
        />
      )}
    </div>
  );
}
