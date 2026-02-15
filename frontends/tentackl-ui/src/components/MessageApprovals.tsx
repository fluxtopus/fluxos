import React, { useEffect, useState } from 'react';
import api from '../services/api';
import { generateMessages, sendMessage, rejectMessage } from '../services/messages';
import { useWorkflowStore } from '../store/workflowStore';

export default function MessageApprovals() {
  const { currentWorkflow } = useWorkflowStore();
  const [state, setState] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [channel, setChannel] = useState<'sms' | 'email'>('sms');

  const load = async () => {
    if (!currentWorkflow?.id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/api/workflows/${currentWorkflow.id}/state`);
      setState(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [currentWorkflow?.id]);

  const onGenerate = async () => {
    if (!currentWorkflow?.id) return;
    setLoading(true);
    setError(null);
    try {
      await generateMessages(currentWorkflow.id, channel, true);
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  const onApprove = async (index: number) => {
    if (!currentWorkflow?.id) return;
    setLoading(true);
    setError(null);
    try {
      await sendMessage(currentWorkflow.id, index);
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  const onReject = async (index: number) => {
    if (!currentWorkflow?.id) return;
    setLoading(true);
    setError(null);
    try {
      await rejectMessage(currentWorkflow.id, index, 'User rejected');
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  const messages = state?.state_data?.messages || {};
  const pending: any[] = messages?.pending || [];
  const sent: any[] = messages?.sent || [];
  const rejected: any[] = messages?.rejected || [];

  return (
    <div className="p-4 space-y-6">
      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg p-4 rounded-lg">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900 dark:text-white">Message Approvals</h3>
          <button onClick={load} className="px-2 py-1 bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-sm hover:bg-gray-200 dark:hover:bg-gray-600 transition-all rounded">Refresh</button>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">Generate messages, then approve or reject before sending.</p>
        {currentWorkflow ? (
          <div className="mt-3 flex items-center space-x-2">
            <select value={channel} onChange={(e) => setChannel(e.target.value as any)} className="px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500 dark:focus:border-blue-400 transition-all rounded-md">
              <option value="sms">SMS</option>
              <option value="email">Email</option>
            </select>
            <button onClick={onGenerate} className="px-3 py-2 bg-green-50 dark:bg-green-900/30 border border-green-500 dark:border-green-500 text-green-700 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/40 transition-all rounded-md">Generate Messages</button>
          </div>
        ) : (
          <div className="text-sm text-gray-500 dark:text-gray-400">Select a workflow to manage approvals.</div>
        )}
        {error && <div className="mt-3 bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-700 text-red-700 dark:text-red-200 p-2 rounded">{error}</div>}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg p-4 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-semibold text-gray-900 dark:text-yellow-400">Pending</h4>
            <span className="text-xs text-gray-500 dark:text-gray-400">{pending.length}</span>
          </div>
          {loading ? <div className="text-gray-500 dark:text-gray-400">Loading…</div> : (
            <div className="space-y-2 max-h-96 overflow-auto">
              {pending.map((m, idx) => (
                <div key={idx} className="border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 p-2 text-sm rounded">
                  <div className="text-xs text-gray-500 dark:text-gray-400">{m.channel?.toUpperCase()}</div>
                  <div className="text-xs text-gray-700 dark:text-gray-200">To: {m.to?.name} {m.to?.phone || m.to?.email}</div>
                  <pre className="text-xs whitespace-pre-wrap text-gray-800 dark:text-gray-100">{m.content}</pre>
                  <div className="mt-2 flex space-x-2">
                    <button onClick={() => onApprove(idx)} className="px-2 py-1 bg-green-600 dark:bg-green-700 text-white text-xs border border-green-700 dark:border-green-600 hover:bg-green-700 dark:hover:bg-green-600 transition-all rounded">Approve</button>
                    <button onClick={() => onReject(idx)} className="px-2 py-1 bg-red-600 dark:bg-red-700 text-white text-xs border border-red-700 dark:border-red-600 hover:bg-red-700 dark:hover:bg-red-600 transition-all rounded">Reject</button>
                  </div>
                </div>
              ))}
              {pending.length === 0 && <div className="text-sm text-gray-500 dark:text-gray-400">No pending messages.</div>}
            </div>
          )}
        </div>

        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg p-4 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-semibold text-gray-900 dark:text-green-400">Sent</h4>
            <span className="text-xs text-gray-500 dark:text-gray-400">{sent.length}</span>
          </div>
          <div className="space-y-2 max-h-96 overflow-auto">
            {sent.map((s, idx) => (
              <div key={idx} className="border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 p-2 text-sm rounded">
                <div className="text-xs text-gray-500 dark:text-gray-400">{s.sent_at}</div>
                <div className="text-xs text-gray-700 dark:text-gray-200">To: {s.message?.to?.name} {s.message?.to?.phone || s.message?.to?.email}</div>
                <pre className="text-xs whitespace-pre-wrap text-gray-800 dark:text-gray-100">{s.message?.content}</pre>
              </div>
            ))}
            {sent.length === 0 && <div className="text-sm text-gray-500 dark:text-gray-400">No messages sent yet.</div>}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg p-4 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-semibold text-gray-900 dark:text-red-400">Rejected</h4>
            <span className="text-xs text-gray-500 dark:text-gray-400">{rejected.length}</span>
          </div>
          <div className="space-y-2 max-h-96 overflow-auto">
            {rejected.map((r, idx) => (
              <div key={idx} className="border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 p-2 text-sm rounded">
                <div className="text-xs text-gray-500 dark:text-gray-400">{r.rejected_at}</div>
                <div className="text-xs text-gray-700 dark:text-gray-200">To: {r.message?.to?.name} {r.message?.to?.phone || r.message?.to?.email}</div>
                <pre className="text-xs whitespace-pre-wrap text-gray-800 dark:text-gray-100">{r.message?.content}</pre>
                {r.reason && <div className="text-xs text-gray-500 dark:text-gray-400">Reason: {r.reason}</div>}
              </div>
            ))}
            {rejected.length === 0 && <div className="text-sm text-gray-500 dark:text-gray-400">No rejected messages.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

