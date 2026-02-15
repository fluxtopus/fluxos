/**
 * Structured Data Display Types
 *
 * Type definitions for workspace objects and specialized renderers.
 * The backend provides `object_type` to indicate how data should be rendered.
 */

export type ViewMode = 'card' | 'table' | 'json' | 'day' | 'week';

/**
 * Calendar event from workspace or Google Calendar.
 */
export interface CalendarEvent {
  id?: string;
  title?: string;
  summary?: string; // Google Calendar uses "summary" as title
  description?: string;
  location?: string;
  start: string; // ISO datetime
  end: string;
  all_day?: boolean;
  attendees?: string[];
  organizer?: string;
  status?: string;
  html_link?: string;
}

/**
 * Contact from workspace.
 */
export interface Contact {
  id?: string;
  name: string;
  email?: string;
  phone?: string;
  company?: string;
  title?: string; // Job title
  notes?: string;
  tags?: string[];
  [key: string]: unknown; // Allow custom fields
}

/**
 * Structured data content from backend.
 * Contains object_type for rendering hints.
 */
export interface StructuredDataContent {
  object_type?: string;
  data?: unknown[];
  total_count?: number;
  query_time_ms?: number;
  intent_time_ms?: number;
  total_time_ms?: number;
  success?: boolean;
  error?: string;
  has_more?: boolean;
}

/**
 * Check if content is structured data with object_type.
 */
export function isStructuredDataContent(
  content: unknown
): content is StructuredDataContent {
  if (typeof content !== 'object' || content === null) {
    return false;
  }
  const obj = content as Record<string, unknown>;
  return typeof obj.object_type === 'string' && Array.isArray(obj.data);
}
