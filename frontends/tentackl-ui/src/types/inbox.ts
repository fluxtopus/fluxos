/**
 * Agent Inbox Types
 *
 * Types for the inbox communication layer where agents report
 * their work as inbox messages. Users read, triage, and act.
 */

import type { TaskStatus, TaskStep } from './task';

// === Inbox Enums ===

export type InboxReadStatus = 'unread' | 'read' | 'archived';

export type InboxPriority = 'normal' | 'attention';

export type InboxFilter = 'all' | 'unread' | 'attention' | 'archived';

// === Core Data Models ===

export interface InboxItem {
  conversation_id: string;
  read_status: InboxReadStatus;
  priority: InboxPriority;
  source?: 'task' | 'inbox';
  last_message_text: string;
  last_message_at: string;
  task_goal: string | null;
  task_status: TaskStatus | null;
  task_id: string | null;
  title?: string | null;
}

export interface InboxMessage {
  id: string;
  role: string;
  content_text: string | null;
  content_data: Record<string, unknown> | null;
  message_type: string;
  timestamp: string;
  agent_id?: string;
}

export interface InboxTask {
  id: string;
  goal: string;
  status: TaskStatus;
  steps: TaskStep[];
  accumulated_findings: unknown[];
}

export interface InboxThread {
  conversation_id: string;
  read_status: InboxReadStatus;
  priority: InboxPriority;
  task: InboxTask | null;
  tasks?: InboxTask[];
  source?: 'task' | 'inbox';
  messages: InboxMessage[];
}

// === Response Types ===

export interface InboxListResponse {
  items: InboxItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface UnreadCountResponse {
  count: number;
}

// === Request Types ===

export interface FollowUpRequest {
  text: string;
}

export interface StatusUpdateRequest {
  read_status: InboxReadStatus;
}

export interface BulkStatusUpdateRequest {
  conversation_ids: string[];
  read_status: InboxReadStatus;
}

// === Chat Types ===

export interface InboxChatRequest {
  message: string;
  conversation_id?: string;
}

export interface InboxChatSSECallbacks {
  onStatus?: (status: string, detail?: Record<string, unknown>) => void;
  onContent?: (content: string) => void;
  onConversationId?: (id: string) => void;
  onDone?: () => void;
  onError?: (error: string) => void;
}

// === Query Params ===

export interface InboxQueryParams {
  read_status?: string;
  priority?: string;
  q?: string;
  limit?: number;
  offset?: number;
}
