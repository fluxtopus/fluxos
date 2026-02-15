'use client';

import { format, parseISO, isToday, isTomorrow, isThisWeek, isValid } from 'date-fns';
import {
  CalendarIcon,
  ClockIcon,
  MapPinIcon,
  UserGroupIcon,
  ArrowTopRightOnSquareIcon,
  PencilIcon,
} from '@heroicons/react/24/outline';
import type { CalendarEvent } from '../../../types/structured-data';

interface CalendarEventCardProps {
  event: CalendarEvent;
  objectId?: string;
  index?: number;
  compact?: boolean;
  onEdit?: (event: CalendarEvent, objectId: string) => void;
}

/**
 * Format date with smart relative text.
 * Handles invalid date strings gracefully.
 */
function formatEventDate(dateStr: string, allDay?: boolean): string {
  if (!dateStr) return 'Date not set';

  const date = parseISO(dateStr);

  // Handle invalid dates
  if (!isValid(date)) {
    // Try parsing as a simple date string if ISO parsing fails
    const fallbackDate = new Date(dateStr);
    if (!isValid(fallbackDate)) {
      return dateStr; // Return the raw string if we can't parse it
    }
    // Use the fallback date
    return formatValidDate(fallbackDate, allDay);
  }

  return formatValidDate(date, allDay);
}

/**
 * Format a valid Date object.
 */
function formatValidDate(date: Date, allDay?: boolean): string {
  let prefix = '';
  if (isToday(date)) prefix = 'Today';
  else if (isTomorrow(date)) prefix = 'Tomorrow';
  else if (isThisWeek(date)) prefix = format(date, 'EEEE'); // Day name
  else prefix = format(date, 'MMM d');

  if (allDay) return prefix;

  return `${prefix}, ${format(date, 'h:mm a')}`;
}

/**
 * Format duration between start and end.
 * Handles invalid date strings gracefully.
 */
function formatDuration(start: string, end: string, allDay?: boolean): string {
  if (allDay) return 'All day';
  if (!start || !end) return '';

  // Try parsing dates
  let startDate = parseISO(start);
  let endDate = parseISO(end);

  // Fallback to Date constructor if parseISO fails
  if (!isValid(startDate)) startDate = new Date(start);
  if (!isValid(endDate)) endDate = new Date(end);

  // Return empty if still invalid
  if (!isValid(startDate) || !isValid(endDate)) return '';

  const diffMs = endDate.getTime() - startDate.getTime();
  if (diffMs < 0) return ''; // Invalid duration

  const diffMins = Math.round(diffMs / 60000);

  if (diffMins < 60) return `${diffMins}m`;
  if (diffMins < 1440) {
    const hours = Math.floor(diffMins / 60);
    const mins = diffMins % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  }
  return `${Math.round(diffMins / 1440)}d`;
}

export function CalendarEventCard({
  event,
  objectId,
  index,
  compact = false,
  onEdit,
}: CalendarEventCardProps) {
  const title = event.summary || event.title || 'Untitled Event';
  const startFormatted = formatEventDate(event.start, event.all_day);
  const duration = formatDuration(event.start, event.end, event.all_day);
  const canEdit = onEdit && objectId;

  if (compact) {
    return (
      <div
        className={`flex items-center gap-3 p-3 rounded-lg bg-[var(--muted)]/50 border border-[var(--border)] hover:border-[oklch(0.6_0.2_260/0.3)] transition-colors ${canEdit ? 'cursor-pointer' : ''}`}
        onClick={canEdit ? () => onEdit(event, objectId) : undefined}
      >
        <div className="w-1.5 h-8 rounded-full bg-[oklch(0.6_0.2_260)]" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[var(--foreground)] truncate">
            {title}
          </p>
          <p className="text-xs text-[var(--muted-foreground)]">
            {startFormatted}
          </p>
        </div>
        <span className="text-xs text-[var(--muted-foreground)] bg-[var(--muted)] px-2 py-0.5 rounded">
          {duration}
        </span>
        {canEdit && (
          <PencilIcon className="w-4 h-4 text-[var(--muted-foreground)] opacity-0 group-hover:opacity-100 transition-opacity" />
        )}
      </div>
    );
  }

  return (
    <div
      className={`group p-4 rounded-lg bg-[var(--muted)]/50 border border-[var(--border)] hover:border-[oklch(0.6_0.2_260/0.3)] transition-colors ${canEdit ? 'cursor-pointer' : ''}`}
      onClick={canEdit ? () => onEdit(event, objectId) : undefined}
    >
      <div className="flex items-start gap-3">
        {/* Rank/index indicator */}
        {index !== undefined && (
          <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[oklch(0.6_0.2_260/0.15)] text-[oklch(0.6_0.2_260)] text-xs font-medium flex items-center justify-center">
            {index + 1}
          </span>
        )}

        <div className="flex-1 min-w-0">
          {/* Title with optional link */}
          <div className="flex items-start gap-2">
            {event.html_link && !canEdit ? (
              <a
                href={event.html_link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium text-[var(--foreground)] hover:text-[oklch(0.6_0.2_260)] transition-colors line-clamp-2"
                onClick={(e) => e.stopPropagation()}
              >
                {title}
                <ArrowTopRightOnSquareIcon className="inline-block w-3 h-3 ml-1 opacity-50" />
              </a>
            ) : (
              <span className="text-sm font-medium text-[var(--foreground)] line-clamp-2">
                {title}
              </span>
            )}
          </div>

          {/* Description */}
          {event.description && (
            <p className="mt-1 text-xs text-[var(--muted-foreground)] line-clamp-2">
              {event.description}
            </p>
          )}

          {/* Event metadata */}
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-[var(--muted-foreground)]">
            {/* Date/Time */}
            <span className="inline-flex items-center gap-1">
              <CalendarIcon className="w-3.5 h-3.5" />
              {startFormatted}
            </span>

            {/* Duration */}
            <span className="inline-flex items-center gap-1">
              <ClockIcon className="w-3.5 h-3.5" />
              {duration}
            </span>

            {/* Location */}
            {event.location && (
              <span className="inline-flex items-center gap-1">
                <MapPinIcon className="w-3.5 h-3.5" />
                <span className="truncate max-w-[120px]">{event.location}</span>
              </span>
            )}

            {/* Attendees count */}
            {event.attendees && event.attendees.length > 0 && (
              <span className="inline-flex items-center gap-1">
                <UserGroupIcon className="w-3.5 h-3.5" />
                {event.attendees.length}
              </span>
            )}
          </div>
        </div>

        {/* Edit indicator */}
        {canEdit && (
          <div className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
            <PencilIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
          </div>
        )}
      </div>
    </div>
  );
}
