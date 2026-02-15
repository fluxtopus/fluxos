import axios from 'axios';

const API_BASE = (import.meta as any).env?.VITE_API_URL || (typeof process !== 'undefined' ? (process.env.REACT_APP_API_URL || 'http://localhost:8000') : 'http://localhost:8000');

export async function generateMessages(workflowId: string, channel: 'sms' | 'email' = 'sms', overwrite = true) {
  const res = await axios.post(`${API_BASE}/api/workflows/${workflowId}/actions/generate_messages`, { channel, overwrite });
  return res.data;
}

export async function sendMessage(workflowId: string, index: number) {
  const res = await axios.post(`${API_BASE}/api/workflows/${workflowId}/actions/send_message`, { index });
  return res.data;
}

export async function rejectMessage(workflowId: string, index: number, reason?: string) {
  const res = await axios.post(`${API_BASE}/api/workflows/${workflowId}/actions/reject_message`, { index, reason });
  return res.data;
}

