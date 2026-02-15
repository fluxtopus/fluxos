import axios from 'axios';

const API_BASE = (import.meta as any).env?.VITE_API_URL || (typeof process !== 'undefined' ? (process.env.REACT_APP_API_URL || 'http://localhost:8000') : 'http://localhost:8000');

export interface RegisterSourceRequest {
  name: string;
  source_type?: 'webhook' | 'websocket' | 'message_queue';
  endpoint?: string;
  authentication_type?: 'api_key' | 'bearer_token' | 'hmac' | 'oauth2';
  rate_limit_requests?: number;
  rate_limit_window_seconds?: number;
  required_fields?: string[];
  active?: boolean;
}

export interface RegisterSourceResponse {
  success: boolean;
  source_id: string;
  api_key?: string;
}

export async function registerSource(req: RegisterSourceRequest): Promise<RegisterSourceResponse> {
  const res = await axios.post(`${API_BASE}/api/events/sources/register`, req, {
    headers: { Authorization: 'Bearer admin-secret-key' },
  });
  return res.data;
}

export interface EmitWebhookRequest {
  source_id: string;
  api_key: string;
  event_type: string;
  data: unknown;
  workflow_id?: string;
  agent_id?: string;
}

export async function emitWebhook(req: EmitWebhookRequest): Promise<any> {
  const res = await axios.post(`${API_BASE}/api/events/webhook/${req.source_id}`,
    { event_type: req.event_type, data: req.data, workflow_id: req.workflow_id, agent_id: req.agent_id },
    { headers: { 'X-API-Key': req.api_key } }
  );
  return res.data;
}

export async function replayEvents(params: { event_types?: string; limit?: number }): Promise<{ events: any[]; total: number }> {
  const res = await axios.get(`${API_BASE}/api/events/replay`, {
    params,
    headers: { Authorization: 'Bearer admin-secret-key' },
  });
  return res.data;
}

export async function fetchMockSink(limit = 50): Promise<{ items: any[]; total: number }> {
  // Mock runs on 9000 with CORS enabled in the mock app
  const url = (typeof window !== 'undefined' ? `${window.location.protocol}//${window.location.hostname}:9000` : 'http://localhost:9000');
  const res = await axios.get(`${url}/sink/received`, { params: { limit } });
  return res.data;
}

