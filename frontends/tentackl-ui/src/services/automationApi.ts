/**
 * Automation API Service
 *
 * Handles all communication with the automations backend.
 */

import api from './api';
import type {
  AutomationSummary,
  AutomationDetail,
  AutomationListResponse,
  CreateAutomationRequest,
} from '../types/automation';

// ============================================
// Automation Management
// ============================================

/**
 * List user's automations
 */
export async function listAutomations(
  includePaused: boolean = true
): Promise<AutomationListResponse> {
  const { data } = await api.get<AutomationListResponse>('/api/automations', {
    params: { include_paused: includePaused },
  });
  return data;
}

/**
 * Get a specific automation by ID
 */
export async function getAutomation(automationId: string): Promise<AutomationDetail> {
  const { data } = await api.get<AutomationDetail>(`/api/automations/${automationId}`);
  return data;
}

/**
 * Pause an automation
 */
export async function pauseAutomation(automationId: string): Promise<void> {
  await api.post(`/api/automations/${automationId}/pause`);
}

/**
 * Resume a paused automation
 */
export async function resumeAutomation(automationId: string): Promise<void> {
  await api.post(`/api/automations/${automationId}/resume`);
}

/**
 * Trigger immediate execution of an automation
 */
export async function runAutomationNow(automationId: string): Promise<{ task_id: string }> {
  const { data } = await api.post<{ ok: boolean; message: string; task_id: string }>(
    `/api/automations/${automationId}/run`
  );
  return data;
}

/**
 * Delete an automation
 */
export async function deleteAutomation(automationId: string): Promise<void> {
  await api.delete(`/api/automations/${automationId}`);
}

/**
 * Create an automation from a completed task
 */
export async function createAutomationFromTask(
  taskId: string,
  request: CreateAutomationRequest
): Promise<AutomationDetail> {
  const { data } = await api.post<AutomationDetail>(
    `/api/automations/from-task/${taskId}`,
    request
  );
  return data;
}
