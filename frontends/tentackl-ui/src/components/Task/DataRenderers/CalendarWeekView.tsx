'use client';

import { useState, useMemo } from 'react';
import {
  format,
  parseISO,
  isValid,
  isSameDay,
  addDays,
  addWeeks,
  startOfWeek,
  endOfWeek,
  eachDayOfInterval,
  isToday,
} from 'date-fns';
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import type { CalendarEvent } from '../../../types/structured-data';
import { useIsMobile } from '../../../hooks/useMediaQuery';

interface CalendarWeekViewProps {
  events: CalendarEvent[];
  initialDate?: Date;
}

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
 * Format event time for compact display.
 */
function formatEventTime(event: CalendarEvent): string {
  if (event.all_day) return '';
  const startDate = parseDate(event.start);
  if (!startDate) return '';
  return format(startDate, 'h:mm a');
}

/**
 * CalendarWeekView - Week grid view for calendar events.
 *
 * Shows a 7-day grid with events displayed as compact cards.
 */
export function CalendarWeekView({ events, initialDate }: CalendarWeekViewProps) {
  const isMobile = useIsMobile();
  const [currentDate, setCurrentDate] = useState<Date>(initialDate || new Date());

  // Get the week's start and end (Monday to Sunday)
  const weekStart = startOfWeek(currentDate, { weekStartsOn: 1 });
  const weekEnd = endOfWeek(currentDate, { weekStartsOn: 1 });
  const weekDays = eachDayOfInterval({ start: weekStart, end: weekEnd });

  // Group events by day
  const eventsByDay = useMemo(() => {
    const grouped: Map<string, CalendarEvent[]> = new Map();

    weekDays.forEach((day) => {
      const dayKey = format(day, 'yyyy-MM-dd');
      grouped.set(dayKey, []);
    });

    events.forEach((event) => {
      const eventDate = parseDate(event.start);
      if (eventDate) {
        const dayKey = format(eventDate, 'yyyy-MM-dd');
        if (grouped.has(dayKey)) {
          grouped.get(dayKey)!.push(event);
        }
      }
    });

    // Sort events by start time within each day
    grouped.forEach((dayEvents, key) => {
      dayEvents.sort((a, b) => {
        if (a.all_day && !b.all_day) return -1;
        if (!a.all_day && b.all_day) return 1;
        const aDate = parseDate(a.start);
        const bDate = parseDate(b.start);
        if (!aDate || !bDate) return 0;
        return aDate.getTime() - bDate.getTime();
      });
    });

    return grouped;
  }, [events, weekDays]);

  // Navigation — day-level on mobile, week-level on desktop
  const goToPrevious = () => setCurrentDate((d) => isMobile ? addDays(d, -1) : addWeeks(d, -1));
  const goToNext = () => setCurrentDate((d) => isMobile ? addDays(d, 1) : addWeeks(d, 1));
  const goToToday = () => setCurrentDate(new Date());

  // Legacy aliases for desktop
  const goToPreviousWeek = goToPrevious;
  const goToNextWeek = goToNext;
  const goToThisWeek = goToToday;

  // Format date range for header
  const dateRangeLabel = `${format(weekStart, 'MMM d')} - ${format(weekEnd, 'MMM d, yyyy')}`;
  const isCurrentWeek = weekDays.some((d) => isToday(d));

  return (
    <div className="space-y-4">
      {/* Header with navigation — hidden on mobile (day view has its own nav) */}
      {!isMobile && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={goToPreviousWeek}
              className="p-1.5 rounded-lg hover:bg-[var(--muted)] transition-colors"
              aria-label="Previous week"
            >
              <ChevronLeftIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
            </button>
            <button
              onClick={goToThisWeek}
              className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                isCurrentWeek
                  ? 'bg-[oklch(0.6_0.2_260/0.1)] text-[oklch(0.6_0.2_260)]'
                  : 'hover:bg-[var(--muted)] text-[var(--foreground)]'
              }`}
            >
              This Week
            </button>
            <button
              onClick={goToNextWeek}
              className="p-1.5 rounded-lg hover:bg-[var(--muted)] transition-colors"
              aria-label="Next week"
            >
              <ChevronRightIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
            </button>
          </div>
          <h3 className="text-sm font-medium text-[var(--foreground)]">{dateRangeLabel}</h3>
        </div>
      )}

      {/* Mobile: single day view */}
      {isMobile ? (
        <div className="border border-[var(--border)] rounded-lg overflow-hidden">
          {/* Day header */}
          <div className="flex items-center justify-between px-3 py-2 bg-[var(--muted)]/30 border-b border-[var(--border)]">
            <button onClick={goToPrevious} className="p-2 rounded-lg hover:bg-[var(--muted)] transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center">
              <ChevronLeftIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
            </button>
            <div className="text-center">
              <p className="text-xs text-[var(--muted-foreground)] uppercase">
                {format(currentDate, 'EEEE')}
              </p>
              <p className={`text-lg font-medium ${isToday(currentDate) ? 'text-[oklch(0.6_0.2_260)]' : 'text-[var(--foreground)]'}`}>
                {format(currentDate, 'MMMM d')}
              </p>
            </div>
            <button onClick={goToNext} className="p-2 rounded-lg hover:bg-[var(--muted)] transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center">
              <ChevronRightIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
            </button>
          </div>

          {/* Day events */}
          <div className="p-3 space-y-2 min-h-[150px]">
            {(() => {
              const dayKey = format(currentDate, 'yyyy-MM-dd');
              const dayEvents = eventsByDay.get(dayKey) || [];

              if (dayEvents.length === 0) {
                return (
                  <div className="text-center py-8 text-sm text-[var(--muted-foreground)]">
                    No events
                  </div>
                );
              }

              return dayEvents.map((event, i) => {
                const title = event.summary || event.title || 'Untitled';
                const time = formatEventTime(event);

                return (
                  <div
                    key={event.id || i}
                    className="p-3 rounded-lg bg-[oklch(0.6_0.2_260/0.1)] border border-[oklch(0.6_0.2_260/0.2)]"
                  >
                    <div className="flex items-start gap-2">
                      <div className="w-1 h-full min-h-[20px] rounded-full bg-[oklch(0.6_0.2_260)] flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-[var(--foreground)]">{title}</p>
                        {time && <p className="text-xs text-[var(--muted-foreground)] mt-0.5">{time}</p>}
                        {event.all_day && <p className="text-xs text-[var(--muted-foreground)] mt-0.5">All day</p>}
                        {event.location && <p className="text-xs text-[var(--muted-foreground)] mt-0.5 truncate">📍 {event.location}</p>}
                      </div>
                    </div>
                  </div>
                );
              });
            })()}
          </div>
        </div>
      ) : (
      /* Desktop: Week grid */
      <div className="border border-[var(--border)] rounded-lg overflow-hidden">
        {/* Day headers */}
        <div className="grid grid-cols-7 border-b border-[var(--border)] bg-[var(--muted)]/30">
          {weekDays.map((day) => {
            const isDayToday = isToday(day);
            return (
              <div
                key={day.toISOString()}
                className={`px-2 py-2 text-center border-r border-[var(--border)] last:border-r-0 ${
                  isDayToday ? 'bg-[oklch(0.6_0.2_260/0.1)]' : ''
                }`}
              >
                <p className="text-xs text-[var(--muted-foreground)] uppercase">
                  {format(day, 'EEE')}
                </p>
                <p
                  className={`text-sm font-medium ${
                    isDayToday ? 'text-[oklch(0.6_0.2_260)]' : 'text-[var(--foreground)]'
                  }`}
                >
                  {format(day, 'd')}
                </p>
              </div>
            );
          })}
        </div>

        {/* Event cells */}
        <div className="grid grid-cols-7 min-h-[200px]">
          {weekDays.map((day) => {
            const dayKey = format(day, 'yyyy-MM-dd');
            const dayEvents = eventsByDay.get(dayKey) || [];
            const isDayToday = isToday(day);

            return (
              <div
                key={day.toISOString()}
                className={`p-1.5 border-r border-[var(--border)] last:border-r-0 min-h-[200px] ${
                  isDayToday ? 'bg-[oklch(0.6_0.2_260/0.03)]' : ''
                }`}
              >
                <div className="space-y-1">
                  {dayEvents.slice(0, 5).map((event, i) => {
                    const title = event.summary || event.title || 'Untitled';
                    const time = formatEventTime(event);

                    return (
                      <div
                        key={event.id || i}
                        className="group relative p-1.5 rounded bg-[oklch(0.6_0.2_260/0.1)] border border-[oklch(0.6_0.2_260/0.2)] hover:bg-[oklch(0.6_0.2_260/0.15)] transition-colors cursor-pointer"
                      >
                        <div className="flex items-start gap-1">
                          <div className="w-0.5 h-4 rounded-full bg-[oklch(0.6_0.2_260)] flex-shrink-0 mt-0.5" />
                          <div className="flex-1 min-w-0">
                            <p className="text-[11px] font-medium text-[var(--foreground)] truncate leading-tight">
                              {title}
                            </p>
                            {time && (
                              <p className="text-[10px] text-[var(--muted-foreground)]">
                                {time}
                              </p>
                            )}
                          </div>
                        </div>

                        {/* Tooltip on hover */}
                        <div className="absolute left-full top-0 ml-2 z-50 hidden group-hover:block">
                          <div className="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)] shadow-lg min-w-[150px]">
                            <p className="text-sm font-medium text-[var(--foreground)]">
                              {event.summary || event.title || 'Untitled Event'}
                            </p>
                            {time && (
                              <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
                                {time}
                              </p>
                            )}
                            {event.all_day && (
                              <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
                                All day
                              </p>
                            )}
                            {event.location && (
                              <p className="text-xs text-[var(--muted-foreground)] mt-0.5 truncate">
                                📍 {event.location}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}

                  {/* Overflow indicator */}
                  {dayEvents.length > 5 && (
                    <p className="text-[10px] text-[var(--muted-foreground)] text-center">
                      +{dayEvents.length - 5} more
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      )}

      {/* Empty state */}
      {events.length === 0 && (
        <div className="text-center py-8 text-sm text-[var(--muted-foreground)]">
          No events for this week
        </div>
      )}
    </div>
  );
}
