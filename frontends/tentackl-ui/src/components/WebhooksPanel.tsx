import React, { useEffect, useMemo, useState } from 'react';
import { registerSource, emitWebhook, replayEvents, fetchMockSink } from '../services/webhooks';

export default function WebhooksPanel() {
  // Helper to generate a short random name
  const getRandomName = () => {
    try {
      const uuid = (window.crypto && 'randomUUID' in window.crypto)
        ? window.crypto.randomUUID()
        : Math.random().toString(36).slice(2);
      return `webhook-${uuid.slice(0, 8)}`;
    } catch {
      return `webhook-${Math.random().toString(36).slice(2, 10)}`;
    }
  };

  const initialName = useMemo(() => getRandomName(), []);
  const [name, setName] = useState(initialName);
  const [endpoint, setEndpoint] = useState(`/webhooks/${initialName}`);
  const [sourceId, setSourceId] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [eventType, setEventType] = useState('weather.update');
  const [dataText, setDataText] = useState(JSON.stringify({ precipitation_probability: 85, severity: 'high', affected_hours: [18, 19], location: 'Porto' }, null, 2));
  const [events, setEvents] = useState<any[]>([]);
  const [mockSink, setMockSink] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [endpointTouched, setEndpointTouched] = useState(false);

  const parsedData = useMemo(() => {
    try { return JSON.parse(dataText); } catch { return null; }
  }, [dataText]);

  const doRegister = async () => {
    setError(null);
    try {
      const res = await registerSource({
        name,
        source_type: 'webhook',
        endpoint,
        authentication_type: 'api_key',
        rate_limit_requests: 100,
        rate_limit_window_seconds: 60,
        required_fields: [],
        active: true,
      });
      setSourceId(res.source_id);
      if (res.api_key) setApiKey(res.api_key);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message);
    }
  };

  const doEmit = async () => {
    setError(null);
    if (!sourceId || !apiKey || !parsedData) {
      setError('source_id, api_key and valid JSON data are required');
      return;
    }
    try {
      await emitWebhook({ source_id: sourceId, api_key: apiKey, event_type: eventType, data: parsedData });
      await refresh();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message);
    }
  };

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const [ev, sink] = await Promise.all([
        replayEvents({ event_types: 'weather.update', limit: 50 }),
        fetchMockSink(50)
      ]);
      setEvents(ev.events || []);
      setMockSink(sink.items || []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  return (
    <div className="p-4 space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg p-4 rounded-lg">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Register Webhook Source</h3>
          <div className="space-y-3">
            <div className="flex gap-2">
              <input className="flex-1 border border-gray-300 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-300 rounded focus:outline-none focus:border-blue-500 dark:focus:border-blue-400" placeholder="name" value={name} onChange={e => setName(e.target.value)} />
              <button
                type="button"
                className="px-3 py-2 bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-800 dark:text-gray-300 text-sm rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-all"
                onClick={() => {
                  const rnd = getRandomName();
                  setName(rnd);
                  if (!endpointTouched) {
                    setEndpoint(`/webhooks/${rnd}`);
                  }
                }}
                title="Generate a random unique name"
              >
                Randomize
              </button>
            </div>
            <input
              className="w-full border border-gray-300 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-300 rounded focus:outline-none focus:border-blue-500 dark:focus:border-blue-400"
              placeholder="endpoint"
              value={endpoint}
              onChange={e => { setEndpoint(e.target.value); setEndpointTouched(true); }}
            />
            <button onClick={doRegister} className="px-3 py-2 bg-blue-50 dark:bg-blue-900/30 border border-blue-500 dark:border-blue-500 text-blue-700 dark:text-blue-400 rounded hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-all">Register</button>
            {sourceId && (
              <div className="text-xs text-gray-600 dark:text-gray-300 space-y-1">
                <div>source_id: <code className="bg-gray-100 dark:bg-gray-700 px-1 py-0.5 rounded">{sourceId}</code></div>
                {apiKey && <div>api_key: <code className="bg-gray-100 dark:bg-gray-700 px-1 py-0.5 rounded">{apiKey}</code></div>}
                {!apiKey && <div className="text-amber-600 dark:text-yellow-400">Note: existing sources don't return api_key; reuse a stored key or register a new name.</div>}
              </div>
            )}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg p-4 rounded-lg">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Emit Webhook</h3>
          <div className="space-y-3">
            <input className="w-full border border-gray-300 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-300 rounded focus:outline-none focus:border-blue-500 dark:focus:border-blue-400" placeholder="source_id" value={sourceId} onChange={e => setSourceId(e.target.value)} />
            <input className="w-full border border-gray-300 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-300 rounded focus:outline-none focus:border-blue-500 dark:focus:border-blue-400" placeholder="api_key" value={apiKey} onChange={e => setApiKey(e.target.value)} />
            <input className="w-full border border-gray-300 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-300 rounded focus:outline-none focus:border-blue-500 dark:focus:border-blue-400" placeholder="event_type" value={eventType} onChange={e => setEventType(e.target.value)} />
            <textarea className="w-full border border-gray-300 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-300 font-mono text-sm h-40 rounded focus:outline-none focus:border-blue-500 dark:focus:border-blue-400" value={dataText} onChange={e => setDataText(e.target.value)} />
            <button onClick={doEmit} className="px-3 py-2 bg-green-50 dark:bg-green-900/30 border border-green-500 dark:border-green-500 text-green-700 dark:text-green-400 rounded hover:bg-green-100 dark:hover:bg-green-900/40 transition-all">Send Webhook</button>
          </div>
        </div>
      </div>

      {error && <div className="bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-700 text-red-700 dark:text-red-200 p-3 rounded">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg p-4 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-gray-900 dark:text-white">Recent Events (replay)</h3>
            <button onClick={refresh} className="px-2 py-1 bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-sm rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-all">Refresh</button>
          </div>
          {loading ? <div className="text-gray-500 dark:text-gray-400">Loading…</div> : (
            <div className="space-y-2 max-h-80 overflow-auto">
              {events.map((e, idx) => (
                <div key={e.id || idx} className="border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 p-2 text-sm rounded">
                  <div className="text-gray-800 dark:text-gray-100"><strong className="text-blue-600 dark:text-blue-400">{e.event_type}</strong> <span className="text-xs text-gray-500 dark:text-gray-400">{e.timestamp}</span></div>
                  <div className="text-xs text-gray-600 dark:text-gray-300">source: {e.source}</div>
                  <pre className="text-xs whitespace-pre-wrap text-gray-700 dark:text-gray-200">{JSON.stringify(e.data, null, 2)}</pre>
                </div>
              ))}
              {events.length === 0 && <div className="text-sm text-gray-500 dark:text-gray-400">No events found.</div>}
            </div>
          )}
        </div>

        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg p-4 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-gray-900 dark:text-white">Mock Sink (/sink/received)</h3>
            <button onClick={refresh} className="px-2 py-1 bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-sm rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-all">Refresh</button>
          </div>
          {loading ? <div className="text-gray-500 dark:text-gray-400">Loading…</div> : (
            <div className="space-y-2 max-h-80 overflow-auto">
              {mockSink.map((item, idx) => (
                <div key={idx} className="border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 p-2 text-sm rounded">
                  <div className="text-xs text-gray-500 dark:text-gray-400">{item.timestamp}</div>
                  <pre className="text-xs whitespace-pre-wrap text-gray-700 dark:text-gray-200">{JSON.stringify(item.body, null, 2)}</pre>
                </div>
              ))}
              {mockSink.length === 0 && <div className="text-sm text-gray-500 dark:text-gray-400">No sink items.</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
