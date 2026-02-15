/**
 * Workspace Service
 *
 * API client for workspace object queries (calendar events, contacts, etc.).
 * Used by workspace shortcuts (#calendar, #contacts) and other workspace features.
 */

import api from './api';
import type { StructuredDataContent, CalendarEvent, Contact } from '../types/structured-data';

/**
 * Query filter for workspace objects.
 */
export interface WorkspaceQuery {
  object_type?: string;
  where?: Record<string, unknown>;
  limit?: number;
}

/**
 * Search request for workspace objects.
 */
export interface WorkspaceSearchRequest {
  query: string;
  object_type?: string;
  limit?: number;
}

/**
 * Query workspace objects with filters.
 *
 * Uses the ultra-fast /shortcuts/query endpoint for instant results.
 * Returns wrapped response with timing metrics.
 */
export async function queryObjects(
  objectType?: string,
  where?: Record<string, unknown>,
  limit: number = 20,
  createdById?: string,
  createdByType?: string,
  offset: number = 0,
): Promise<StructuredDataContent> {
  const body: Record<string, unknown> = { limit, offset };
  if (objectType) body.object_type = objectType;
  if (where) body.where = where;
  if (createdById) body.created_by_id = createdById;
  if (createdByType) body.created_by_type = createdByType;

  const { data } = await api.post<StructuredDataContent>('/api/workspace/shortcuts/query', body);
  return data;
}

/**
 * Search workspace objects with natural language query.
 *
 * Uses the ultra-fast /shortcuts/search endpoint for instant results.
 * Returns wrapped response with timing metrics.
 */
export async function searchObjects(
  query: string,
  objectType?: string,
  limit: number = 20,
  offset: number = 0,
): Promise<StructuredDataContent> {
  const { data } = await api.post<StructuredDataContent>('/api/workspace/shortcuts/search', {
    query,
    object_type: objectType,
    limit,
    offset,
  });
  return data;
}

/**
 * Update a workspace object.
 */
export async function updateObject(
  objectId: string,
  data: Record<string, unknown>
): Promise<void> {
  await api.patch(`/api/workspace/objects/${objectId}`, { data });
}

// ============================================
// Date Helpers
// ============================================

/**
 * Get start of day in ISO format.
 */
function getStartOfDay(date: Date = new Date()): string {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

/**
 * Get end of day in ISO format.
 */
function getEndOfDay(date: Date = new Date()): string {
  const d = new Date(date);
  d.setHours(23, 59, 59, 999);
  return d.toISOString();
}

/**
 * Get start of week (Monday) in ISO format.
 */
function getStartOfWeek(date: Date = new Date()): string {
  const d = new Date(date);
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1); // Adjust to Monday
  d.setDate(diff);
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

/**
 * Get end of week (Sunday) in ISO format.
 */
function getEndOfWeek(date: Date = new Date()): string {
  const d = new Date(date);
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? 0 : 7); // Adjust to Sunday
  d.setDate(diff);
  d.setHours(23, 59, 59, 999);
  return d.toISOString();
}

/**
 * Add days to a date.
 */
function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

// ============================================
// Calendar Event Helpers
// ============================================

/**
 * Get calendar events for today.
 */
export async function getEventsToday(limit: number = 20, offset: number = 0): Promise<StructuredDataContent> {
  const today = new Date();
  return queryObjects('event', {
    start: { $gte: getStartOfDay(today) },
    end: { $lte: getEndOfDay(today) },
  }, limit, undefined, undefined, offset);
}

/**
 * Get calendar events for tomorrow.
 */
export async function getEventsTomorrow(limit: number = 20, offset: number = 0): Promise<StructuredDataContent> {
  const tomorrow = addDays(new Date(), 1);
  return queryObjects('event', {
    start: { $gte: getStartOfDay(tomorrow) },
    end: { $lte: getEndOfDay(tomorrow) },
  }, limit, undefined, undefined, offset);
}

/**
 * Get calendar events for this week.
 */
export async function getEventsThisWeek(limit: number = 20, offset: number = 0): Promise<StructuredDataContent> {
  const today = new Date();
  return queryObjects('event', {
    start: { $gte: getStartOfWeek(today) },
    end: { $lte: getEndOfWeek(today) },
  }, limit, undefined, undefined, offset);
}

/**
 * Get calendar events for next week.
 */
export async function getEventsNextWeek(limit: number = 20, offset: number = 0): Promise<StructuredDataContent> {
  const nextWeek = addDays(new Date(), 7);
  return queryObjects('event', {
    start: { $gte: getStartOfWeek(nextWeek) },
    end: { $lte: getEndOfWeek(nextWeek) },
  }, limit, undefined, undefined, offset);
}

/**
 * Get calendar events for a specific date range.
 */
export async function getEventsByDateRange(
  startDate: Date,
  endDate: Date,
  limit: number = 20,
  offset: number = 0,
): Promise<StructuredDataContent> {
  return queryObjects('event', {
    start: { $gte: startDate.toISOString() },
    end: { $lte: endDate.toISOString() },
  }, limit, undefined, undefined, offset);
}

// ============================================
// Contact Helpers
// ============================================

/**
 * Get all contacts.
 */
export async function getContacts(limit: number = 20, offset: number = 0): Promise<StructuredDataContent> {
  return queryObjects('contact', undefined, limit, undefined, undefined, offset);
}

/**
 * Get contacts by name search.
 */
export async function getContactsByName(name: string, limit: number = 20, offset: number = 0): Promise<StructuredDataContent> {
  return searchObjects(name, 'contact', limit, offset);
}

// ============================================
// Shortcut Command Parser
// ============================================

export type ShortcutType = 'calendar' | 'contacts' | 'agent';

export interface ParsedShortcut {
  type: ShortcutType;
  query: string;
  raw: string;
}

/**
 * Shortcut patterns for workspace queries.
 */
const SHORTCUT_PATTERNS: Record<ShortcutType, RegExp> = {
  calendar: /^\/calendar\s*(events?)?\s*(.*)$/i,
  contacts: /^\/contacts?\s*(.*)$/i,
  agent: /^\/(?:agent|task)\s+(\S+)\s*(?:data)?$/i,
};

/**
 * Parse a shortcut command from input text.
 * Returns null if no shortcut found.
 */
export function parseShortcut(text: string): ParsedShortcut | null {
  const trimmed = text.trim();

  // Check calendar shortcut
  const calendarMatch = trimmed.match(SHORTCUT_PATTERNS.calendar);
  if (calendarMatch) {
    return {
      type: 'calendar',
      query: calendarMatch[2]?.trim() || '',
      raw: trimmed,
    };
  }

  // Check contacts shortcut
  const contactsMatch = trimmed.match(SHORTCUT_PATTERNS.contacts);
  if (contactsMatch) {
    return {
      type: 'contacts',
      query: contactsMatch[1]?.trim() || '',
      raw: trimmed,
    };
  }

  // Check agent shortcut
  const agentMatch = trimmed.match(SHORTCUT_PATTERNS.agent);
  if (agentMatch) {
    return {
      type: 'agent',
      query: agentMatch[1],
      raw: trimmed,
    };
  }

  return null;
}

/**
 * Check if text starts with a shortcut character (/).
 */
export function isShortcutStart(text: string): boolean {
  return text.trimStart().startsWith('/');
}

/**
 * Get available shortcut suggestions based on partial input.
 */
export function getShortcutSuggestions(partialInput: string): Array<{
  type: ShortcutType;
  label: string;
  example: string;
  description: string;
}> {
  const input = partialInput.toLowerCase().trim();

  const allSuggestions = [
    {
      type: 'calendar' as ShortcutType,
      label: '/calendar',
      example: '/calendar events today',
      description: 'Query calendar events',
    },
    {
      type: 'contacts' as ShortcutType,
      label: '/contacts',
      example: '/contacts Jorge',
      description: 'Search contacts',
    },
    {
      type: 'agent' as ShortcutType,
      label: '/task',
      example: '/task <task-id>',
      description: 'Get workspace data created by a task',
    },
  ];

  // Filter based on partial input
  if (input === '/') {
    return allSuggestions;
  }

  return allSuggestions.filter(
    (s) => s.label.toLowerCase().startsWith(input) || s.example.toLowerCase().includes(input)
  );
}

/**
 * Execute a parsed shortcut command.
 */
export async function executeShortcut(
  shortcut: ParsedShortcut,
  limit: number = 20,
  offset: number = 0,
): Promise<StructuredDataContent> {
  switch (shortcut.type) {
    case 'calendar':
      return executeCalendarShortcut(shortcut.query, limit, offset);

    case 'contacts':
      if (shortcut.query) {
        return getContactsByName(shortcut.query, limit, offset);
      }
      return getContacts(limit, offset);

    case 'agent':
      // Query workspace objects created by a specific task
      return queryObjects(undefined, undefined, limit, shortcut.query, 'task', offset);

    default:
      throw new Error(`Unknown shortcut type: ${shortcut.type}`);
  }
}

/**
 * Execute a calendar shortcut with query parsing.
 */
async function executeCalendarShortcut(query: string, limit: number = 20, offset: number = 0): Promise<StructuredDataContent> {
  const normalizedQuery = query.toLowerCase().trim();

  // Today
  if (!normalizedQuery || normalizedQuery === 'today' || normalizedQuery === 'events today') {
    return getEventsToday(limit, offset);
  }

  // Tomorrow
  if (normalizedQuery === 'tomorrow' || normalizedQuery === 'events tomorrow') {
    return getEventsTomorrow(limit, offset);
  }

  // This week
  if (
    normalizedQuery === 'this week' ||
    normalizedQuery === 'events this week' ||
    normalizedQuery === 'week'
  ) {
    return getEventsThisWeek(limit, offset);
  }

  // Next week
  if (normalizedQuery === 'next week' || normalizedQuery === 'events next week') {
    return getEventsNextWeek(limit, offset);
  }

  // Day names (next occurrence)
  const dayNames = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
  const nextMatch = normalizedQuery.match(/^next\s+(\w+)$/);
  if (nextMatch) {
    const targetDay = nextMatch[1].toLowerCase();
    const dayIndex = dayNames.indexOf(targetDay);
    if (dayIndex !== -1) {
      const today = new Date();
      const currentDay = today.getDay();
      let daysUntil = dayIndex - currentDay;
      if (daysUntil <= 0) daysUntil += 7; // Get next occurrence
      const targetDate = addDays(today, daysUntil);
      return getEventsByDateRange(
        new Date(getStartOfDay(targetDate)),
        new Date(getEndOfDay(targetDate)),
        limit,
        offset,
      );
    }
  }

  // Fallback: search calendar events with the query
  return searchObjects(query, 'event', limit, offset);
}
