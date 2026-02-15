'use client';

import { useState, useMemo } from 'react';
import { format, parseISO, isValid, isSameDay, addDays, isToday } from 'date-fns';
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  MapPinIcon,
} from '@heroicons/react/24/outline';
import type { CalendarEvent } from '../../../types/structured-data';

interface CalendarDayViewProps {
  events: CalendarEvent[];
  initialDate?: Date;
}

/**
 * Working hours for the day view (6 AM to 10 PM).
 */
const WORKING_HOURS_START = 6;
const WORKING_HOURS_END = 22;
const HOUR_HEIGHT = 48; // pixels per hour

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

/**
 * Get the hour (0-23) from a date.
 */
function getHour(date: Date): number {
  return date.getHours() + date.getMinutes() / 60;
}

/**
 * Calculate event position and height for the timeline.
 */
function getEventStyle(event: CalendarEvent): { top: number; height: number } | null {
  const startDate = parseDate(event.start);
  const endDate = parseDate(event.end);

  if (!startDate || !endDate) return null;
  if (event.all_day) return null;

  const startHour = getHour(startDate);
  const endHour = getHour(endDate);

  // Clamp to working hours
  const clampedStart = Math.max(startHour, WORKING_HOURS_START);
  const clampedEnd = Math.min(endHour, WORKING_HOURS_END);

  if (clampedEnd <= clampedStart) return null;

  const top = (clampedStart - WORKING_HOURS_START) * HOUR_HEIGHT;
  const height = (clampedEnd - clampedStart) * HOUR_HEIGHT;

  return { top, height: Math.max(height, 24) }; // Minimum height of 24px
}

/**
 * Format event time range.
 */
function formatTimeRange(event: CalendarEvent): string {
  if (event.all_day) return 'All day';

  const startDate = parseDate(event.start);
  const endDate = parseDate(event.end);

  if (!startDate || !endDate) return '';

  return `${format(startDate, 'h:mm a')} - ${format(endDate, 'h:mm a')}`;
}

/**
 * CalendarDayView - Day timeline view for calendar events.
 *
 * Shows events positioned by time on a vertical timeline.
 */
export function CalendarDayView({ events, initialDate }: CalendarDayViewProps) {
  const [currentDate, setCurrentDate] = useState<Date>(initialDate || new Date());

  // Filter events for the current day
  const dayEvents = useMemo(() => {
    return events.filter((event) => {
      const eventDate = parseDate(event.start);
      return eventDate && isSameDay(eventDate, currentDate);
    });
  }, [events, currentDate]);

  // Separate all-day events from timed events
  const allDayEvents = dayEvents.filter((e) => e.all_day);
  const timedEvents = dayEvents.filter((e) => !e.all_day);

  // Navigation
  const goToPreviousDay = () => setCurrentDate((d) => addDays(d, -1));
  const goToNextDay = () => setCurrentDate((d) => addDays(d, 1));
  const goToToday = () => setCurrentDate(new Date());

  // Generate hour labels
  const hours = [];
  for (let h = WORKING_HOURS_START; h <= WORKING_HOURS_END; h++) {
    hours.push(h);
  }

  // Format date display
  const isCurrentDateToday = isToday(currentDate);
  const dateLabel = isCurrentDateToday
    ? `${format(currentDate, 'EEEE, MMMM d, yyyy')} (Today)`
    : format(currentDate, 'EEEE, MMMM d, yyyy');

  return (
    <div className="space-y-4">
      {/* Header with navigation */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={goToPreviousDay}
            className="p-1.5 rounded-lg hover:bg-[var(--muted)] transition-colors"
            aria-label="Previous day"
          >
            <ChevronLeftIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
          </button>
          <button
            onClick={goToToday}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              isCurrentDateToday
                ? 'bg-[oklch(0.6_0.2_260/0.1)] text-[oklch(0.6_0.2_260)]'
                : 'hover:bg-[var(--muted)] text-[var(--foreground)]'
            }`}
          >
            Today
          </button>
          <button
            onClick={goToNextDay}
            className="p-1.5 rounded-lg hover:bg-[var(--muted)] transition-colors"
            aria-label="Next day"
          >
            <ChevronRightIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
          </button>
        </div>
        <h3 className="text-sm font-medium text-[var(--foreground)]">{dateLabel}</h3>
      </div>

      {/* All-day events section */}
      {allDayEvents.length > 0 && (
        <div className="border border-[var(--border)] rounded-lg p-3 bg-[var(--muted)]/30">
          <p className="text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wide mb-2">
            All Day
          </p>
          <div className="space-y-2">
            {allDayEvents.map((event, i) => (
              <div
                key={event.id || i}
                className="flex items-center gap-2 p-2 rounded-lg bg-[oklch(0.6_0.2_260/0.1)] border border-[oklch(0.6_0.2_260/0.2)]"
              >
                <div className="w-1.5 h-5 rounded-full bg-[oklch(0.6_0.2_260)]" />
                <span className="text-sm font-medium text-[var(--foreground)]">
                  {event.summary || event.title || 'Untitled Event'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="relative border border-[var(--border)] rounded-lg overflow-hidden">
        <div className="flex">
          {/* Hour labels column */}
          <div className="flex-shrink-0 w-16 border-r border-[var(--border)] bg-[var(--muted)]/30">
            {hours.map((hour) => (
              <div
                key={hour}
                className="relative"
                style={{ height: HOUR_HEIGHT }}
              >
                <span className="absolute top-0 right-2 -translate-y-1/2 text-xs text-[var(--muted-foreground)]">
                  {format(new Date().setHours(hour, 0), 'h a')}
                </span>
              </div>
            ))}
          </div>

          {/* Events column */}
          <div className="flex-1 relative">
            {/* Hour lines */}
            {hours.map((hour) => (
              <div
                key={hour}
                className="border-b border-[var(--border)]"
                style={{ height: HOUR_HEIGHT }}
              />
            ))}

            {/* Event blocks */}
            {timedEvents.map((event, i) => {
              const style = getEventStyle(event);
              if (!style) return null;

              const title = event.summary || event.title || 'Untitled Event';
              const timeRange = formatTimeRange(event);

              return (
                <div
                  key={event.id || i}
                  className="absolute left-1 right-1 rounded-lg bg-[oklch(0.6_0.2_260/0.15)] border border-[oklch(0.6_0.2_260/0.3)] hover:bg-[oklch(0.6_0.2_260/0.2)] transition-colors overflow-hidden"
                  style={{
                    top: style.top,
                    height: style.height,
                  }}
                >
                  <div className="p-2 h-full flex flex-col">
                    <div className="flex items-start gap-2">
                      <div className="w-1 h-full min-h-[16px] rounded-full bg-[oklch(0.6_0.2_260)] flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-[var(--foreground)] truncate">
                          {title}
                        </p>
                        <p className="text-xs text-[var(--muted-foreground)]">
                          {timeRange}
                        </p>
                        {event.location && style.height > 60 && (
                          <p className="text-xs text-[var(--muted-foreground)] flex items-center gap-1 mt-1">
                            <MapPinIcon className="w-3 h-3" />
                            <span className="truncate">{event.location}</span>
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}

            {/* Empty state */}
            {timedEvents.length === 0 && allDayEvents.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center">
                <p className="text-sm text-[var(--muted-foreground)]">
                  No events for this day
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
