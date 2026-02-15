'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';
import type {
  Integration,
  OutboundConfigRequest,
  InboundConfigRequest,
  CredentialRequest,
} from '../../../../../types/integration';
import { PROVIDER_CONFIG, DIRECTION_CONFIG, STATUS_CONFIG } from '../../../../../types/integration';
import { ProviderIcon } from '../../../../../components/Integration';
import { IncomingEventsSection } from '../../../../../components/IncomingEventsSection';
import * as integrationApi from '../../../../../services/integrationApi';

export default function IntegrationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const integrationId = params.id as string;

  const [integration, setIntegration] = useState<Integration | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadIntegration = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await integrationApi.getIntegration(integrationId);
      setIntegration(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load integration');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadIntegration();
  }, [integrationId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">LOADING...</p>
        </div>
      </div>
    );
  }

  if (error || !integration) {
    return (
      <div className="py-10">
        <button
          onClick={() => router.push('/settings/integrations')}
          className="flex items-center gap-2 text-xs font-mono tracking-wider text-[var(--muted-foreground)] hover:text-[var(--foreground)] mb-6"
        >
          <ArrowLeftIcon className="w-4 h-4" />
          BACK TO INTEGRATIONS
        </button>
        <div className="p-4 rounded border border-[var(--destructive)]/30 bg-[var(--card)] text-xs font-mono text-[var(--destructive)]">
          {error || 'Integration not found'}
        </div>
      </div>
    );
  }

  const provider = PROVIDER_CONFIG[integration.provider];
  const direction = DIRECTION_CONFIG[integration.direction];
  const status = STATUS_CONFIG[integration.status];
  const needsOutbound = integration.direction === 'outbound' || integration.direction === 'bidirectional';
  const needsInbound = integration.direction === 'inbound' || integration.direction === 'bidirectional';

  return (
    <div>
      {/* Back link */}
      <button
        onClick={() => router.push('/settings/integrations')}
        className="flex items-center gap-2 text-xs font-mono tracking-wider text-[var(--muted-foreground)] hover:text-[var(--foreground)] mb-6"
      >
        <ArrowLeftIcon className="w-4 h-4" />
        BACK TO INTEGRATIONS
      </button>

      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <div className="flex-shrink-0 w-12 h-12 rounded border border-[var(--border)] bg-[var(--muted)] flex items-center justify-center">
          <ProviderIcon provider={integration.provider} size={24} />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold text-[var(--foreground)]">{integration.name}</h2>
            <span className={`inline-flex items-center gap-1 text-[10px] font-mono tracking-wider ${status.color}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${status.dotColor}`} />
              {status.label}
            </span>
          </div>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
              {provider.label}
            </span>
            <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
              {direction.label}
            </span>
            {integration.created_at && (
              <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
                CREATED {new Date(integration.created_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={loadIntegration}
          className="p-2 rounded border border-[var(--border)] bg-[var(--background)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:border-[var(--accent)] transition-colors"
        >
          <ArrowPathIcon className="w-4 h-4" />
        </button>
      </div>

      <div className="space-y-6">
        {/* Outbound Config Section */}
        {needsOutbound && (
          <OutboundConfigSection
            integrationId={integration.id}
            config={integration.outbound_config ?? null}
            onUpdated={loadIntegration}
          />
        )}

        {/* Inbound Config Section */}
        {needsInbound && (
          <InboundConfigSection
            integrationId={integration.id}
            config={integration.inbound_config ?? null}
            onUpdated={loadIntegration}
          />
        )}

        {/* Credentials Section */}
        <CredentialsSection
          integrationId={integration.id}
          webhookUrl={integration.webhook_url}
          onUpdated={loadIntegration}
        />

        {/* Incoming Events Section */}
        <IncomingEventsSection
          integrationId={integration.id}
          direction={integration.direction}
        />
      </div>
    </div>
  );
}

// ============================================
// Outbound Config Section
// ============================================

interface OutboundConfigSectionProps {
  integrationId: string;
  config: Integration['outbound_config'];
  onUpdated: () => void;
}

function OutboundConfigSection({ integrationId, config, onUpdated }: OutboundConfigSectionProps) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionType, setActionType] = useState(config?.action_type || 'send_message');
  const [rateLimitRequests, setRateLimitRequests] = useState(String(config?.rate_limit_requests ?? 30));
  const [rateLimitWindow, setRateLimitWindow] = useState(String(config?.rate_limit_window_seconds ?? 60));

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await integrationApi.setOutboundConfig(integrationId, {
        action_type: actionType,
        rate_limit_requests: parseInt(rateLimitRequests) || undefined,
        rate_limit_window_seconds: parseInt(rateLimitWindow) || undefined,
      });
      setEditing(false);
      onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save outbound config');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded border border-[var(--border)] bg-[var(--card)]">
      <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <p className="text-xs font-mono tracking-wider text-[var(--foreground)]">OUTBOUND CONFIG</p>
          {config ? (
            <span className="inline-flex items-center gap-1 text-[10px] font-mono tracking-wider text-emerald-500">
              <CheckCircleIcon className="w-3 h-3" />
              READY
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[10px] font-mono tracking-wider text-[var(--destructive)]">
              <ExclamationCircleIcon className="w-3 h-3" />
              NOT CONFIGURED
            </span>
          )}
        </div>
        <button
          onClick={() => setEditing(!editing)}
          className="text-[10px] font-mono tracking-wider text-[var(--accent)] hover:underline"
        >
          {editing ? 'CANCEL' : config ? 'EDIT' : 'CONFIGURE'}
        </button>
      </div>

      {config && !editing && (
        <div className="p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">ACTION TYPE</span>
            <span className="text-xs font-mono text-[var(--foreground)]">{config.action_type}</span>
          </div>
          {config.rate_limit_requests && (
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">RATE LIMIT</span>
              <span className="text-xs font-mono text-[var(--foreground)]">
                {config.rate_limit_requests} req / {config.rate_limit_window_seconds}s
              </span>
            </div>
          )}
        </div>
      )}

      {editing && (
        <div className="p-4 space-y-4">
          <div>
            <label className="block text-[10px] font-mono tracking-wider text-[var(--muted-foreground)] mb-1">ACTION TYPE</label>
            <select
              value={actionType}
              onChange={(e) => setActionType(e.target.value)}
              className="w-full px-3 py-2 text-sm font-mono rounded border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]"
            >
              <option value="send_message">send_message</option>
              <option value="send_embed">send_embed</option>
              <option value="send_blocks">send_blocks</option>
              <option value="create_issue">create_issue</option>
              <option value="post">post</option>
              <option value="put">put</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-mono tracking-wider text-[var(--muted-foreground)] mb-1">RATE LIMIT (REQUESTS)</label>
              <input
                type="number"
                value={rateLimitRequests}
                onChange={(e) => setRateLimitRequests(e.target.value)}
                className="w-full px-3 py-2 text-sm font-mono rounded border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono tracking-wider text-[var(--muted-foreground)] mb-1">WINDOW (SECONDS)</label>
              <input
                type="number"
                value={rateLimitWindow}
                onChange={(e) => setRateLimitWindow(e.target.value)}
                className="w-full px-3 py-2 text-sm font-mono rounded border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>
          </div>
          {error && (
            <div className="p-3 rounded border border-[var(--destructive)]/30 bg-[var(--destructive)]/5 text-xs font-mono text-[var(--destructive)] flex items-center gap-2">
              <ExclamationTriangleIcon className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {saving && <ArrowPathIcon className="w-3.5 h-3.5 animate-spin" />}
            SAVE
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================
// Inbound Config Section
// ============================================

interface InboundConfigSectionProps {
  integrationId: string;
  config: Integration['inbound_config'];
  onUpdated: () => void;
}

function InboundConfigSection({ integrationId, config, onUpdated }: InboundConfigSectionProps) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; checks: Array<{ name: string; passed: boolean }> } | null>(null);
  const [authMethod, setAuthMethod] = useState<'none' | 'api_key' | 'signature' | 'ed25519' | 'bearer'>(config?.auth_method || 'none');
  const [signatureSecret, setSignatureSecret] = useState('');
  const [destinationService, setDestinationService] = useState<'tentackl' | 'custom'>(config?.destination_service || 'tentackl');

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setTestResult(null);
    try {
      const payload: InboundConfigRequest = {
        auth_method: authMethod as InboundConfigRequest['auth_method'],
        destination_service: destinationService as InboundConfigRequest['destination_service'],
      };
      if ((authMethod === 'signature' || authMethod === 'ed25519') && signatureSecret) {
        payload.signature_secret = signatureSecret;
      }
      await integrationApi.setInboundConfig(integrationId, payload);
      setEditing(false);
      setSignatureSecret('');
      onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save inbound config');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setError(null);
    setTestResult(null);
    try {
      const result = await integrationApi.testInboundConfig(integrationId);
      setTestResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to test inbound config');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="rounded border border-[var(--border)] bg-[var(--card)]">
      <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <p className="text-xs font-mono tracking-wider text-[var(--foreground)]">INBOUND CONFIG</p>
          {config ? (
            <span className="inline-flex items-center gap-1 text-[10px] font-mono tracking-wider text-emerald-500">
              <CheckCircleIcon className="w-3 h-3" />
              READY
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[10px] font-mono tracking-wider text-[var(--destructive)]">
              <ExclamationCircleIcon className="w-3 h-3" />
              NOT CONFIGURED
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {config && !editing && (
            <button
              onClick={handleTest}
              disabled={testing}
              className="inline-flex items-center gap-1.5 text-[10px] font-mono tracking-wider text-[var(--accent)] hover:underline disabled:opacity-50"
            >
              {testing && <ArrowPathIcon className="w-3 h-3 animate-spin" />}
              TEST
            </button>
          )}
          <button
            onClick={() => { setEditing(!editing); setTestResult(null); setError(null); }}
            className="text-[10px] font-mono tracking-wider text-[var(--accent)] hover:underline"
          >
            {editing ? 'CANCEL' : config ? 'EDIT' : 'CONFIGURE'}
          </button>
        </div>
      </div>

      {config && !editing && (
        <div className="p-4 space-y-2">
          {config.webhook_url && (
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">WEBHOOK URL</span>
              <span className="text-xs font-mono text-[var(--foreground)] truncate max-w-xs">{config.webhook_url}</span>
            </div>
          )}
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">AUTH METHOD</span>
            <span className="text-xs font-mono text-[var(--foreground)]">{config.auth_method}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">DESTINATION</span>
            <span className="text-xs font-mono text-[var(--foreground)]">{config.destination_service}</span>
          </div>
          {testResult && (
            <div className={`mt-3 p-3 rounded border text-xs font-mono ${testResult.success ? 'border-emerald-500/30 bg-emerald-500/5 text-emerald-500' : 'border-[var(--destructive)]/30 bg-[var(--destructive)]/5 text-[var(--destructive)]'}`}>
              <p className="font-semibold mb-1">{testResult.success ? 'PASSED' : 'FAILED'}: {testResult.message}</p>
              {testResult.checks.map((check, i) => (
                <p key={i} className="ml-2">
                  {check.passed ? '\u2713' : '\u2717'} {check.name}
                </p>
              ))}
            </div>
          )}
          {error && (
            <div className="p-3 rounded border border-[var(--destructive)]/30 bg-[var(--destructive)]/5 text-xs font-mono text-[var(--destructive)] flex items-center gap-2">
              <ExclamationTriangleIcon className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}
        </div>
      )}

      {editing && (
        <div className="p-4 space-y-4">
          <div>
            <label className="block text-[10px] font-mono tracking-wider text-[var(--muted-foreground)] mb-1">AUTH METHOD</label>
            <select
              value={authMethod}
              onChange={(e) => setAuthMethod(e.target.value as typeof authMethod)}
              className="w-full px-3 py-2 text-sm font-mono rounded border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]"
            >
              <option value="none">none</option>
              <option value="api_key">api_key</option>
              <option value="signature">signature</option>
              <option value="ed25519">ed25519 (Discord)</option>
              <option value="bearer">bearer</option>
            </select>
          </div>
          {(authMethod === 'signature' || authMethod === 'ed25519') && (
            <div>
              <label className="block text-[10px] font-mono tracking-wider text-[var(--muted-foreground)] mb-1">
                {authMethod === 'ed25519' ? 'DISCORD PUBLIC KEY' : 'SIGNATURE SECRET'}
              </label>
              <input
                type="text"
                value={signatureSecret}
                onChange={(e) => setSignatureSecret(e.target.value)}
                placeholder={authMethod === 'ed25519' ? 'Hex public key from Discord Developer Portal' : 'HMAC secret for signature verification'}
                className="w-full px-3 py-2 text-sm font-mono rounded border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)] placeholder:text-[var(--muted-foreground)]/50"
              />
              {authMethod === 'ed25519' && (
                <p className="mt-1 text-[10px] font-mono text-[var(--muted-foreground)]">
                  Found in Discord Developer Portal → General Information → Public Key
                </p>
              )}
            </div>
          )}
          <div>
            <label className="block text-[10px] font-mono tracking-wider text-[var(--muted-foreground)] mb-1">DESTINATION SERVICE</label>
            <select
              value={destinationService}
              onChange={(e) => setDestinationService(e.target.value as typeof destinationService)}
              className="w-full px-3 py-2 text-sm font-mono rounded border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]"
            >
              <option value="tentackl">tentackl</option>
              <option value="custom">custom</option>
            </select>
          </div>
          {error && (
            <div className="p-3 rounded border border-[var(--destructive)]/30 bg-[var(--destructive)]/5 text-xs font-mono text-[var(--destructive)] flex items-center gap-2">
              <ExclamationTriangleIcon className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {saving && <ArrowPathIcon className="w-3.5 h-3.5 animate-spin" />}
            SAVE
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================
// Credentials Section
// ============================================

interface CredentialsSectionProps {
  integrationId: string;
  webhookUrl?: string | null;
  onUpdated: () => void;
}

function CredentialsSection({ integrationId, webhookUrl, onUpdated }: CredentialsSectionProps) {
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [credType, setCredType] = useState<CredentialRequest['credential_type']>('webhook_url');
  const [credValue, setCredValue] = useState('');

  const handleAdd = async () => {
    if (!credValue.trim()) {
      setError('Value is required');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await integrationApi.addCredential(integrationId, {
        credential_type: credType,
        value: credValue.trim(),
      });
      setAdding(false);
      setCredValue('');
      onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add credential');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded border border-[var(--border)] bg-[var(--card)]">
      <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
        <p className="text-xs font-mono tracking-wider text-[var(--foreground)]">CREDENTIALS</p>
        <button
          onClick={() => setAdding(!adding)}
          className="text-[10px] font-mono tracking-wider text-[var(--accent)] hover:underline"
        >
          {adding ? 'CANCEL' : 'ADD'}
        </button>
      </div>

      <div className="p-4 space-y-2">
        {webhookUrl && (
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">WEBHOOK URL</span>
            <span className="text-xs font-mono text-[var(--foreground)]">{webhookUrl}</span>
          </div>
        )}
        {!webhookUrl && !adding && (
          <p className="text-[10px] font-mono text-[var(--muted-foreground)]">No credentials configured</p>
        )}
      </div>

      {adding && (
        <div className="p-4 pt-0 space-y-4">
          <div>
            <label className="block text-[10px] font-mono tracking-wider text-[var(--muted-foreground)] mb-1">TYPE</label>
            <select
              value={credType}
              onChange={(e) => setCredType(e.target.value as CredentialRequest['credential_type'])}
              className="w-full px-3 py-2 text-sm font-mono rounded border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)]"
            >
              <option value="webhook_url">webhook_url</option>
              <option value="api_key">api_key</option>
              <option value="bot_token">bot_token</option>
              <option value="oauth_token">oauth_token</option>
              <option value="webhook_secret">webhook_secret</option>
            </select>
          </div>
          <div>
            <label className="block text-[10px] font-mono tracking-wider text-[var(--muted-foreground)] mb-1">VALUE</label>
            <input
              type="password"
              value={credValue}
              onChange={(e) => setCredValue(e.target.value)}
              placeholder="Enter credential value..."
              className="w-full px-3 py-2 text-sm font-mono rounded border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]/50 focus:outline-none focus:border-[var(--accent)]"
            />
          </div>
          {error && (
            <div className="p-3 rounded border border-[var(--destructive)]/30 bg-[var(--destructive)]/5 text-xs font-mono text-[var(--destructive)] flex items-center gap-2">
              <ExclamationTriangleIcon className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}
          <button
            onClick={handleAdd}
            disabled={saving}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {saving && <ArrowPathIcon className="w-3.5 h-3.5 animate-spin" />}
            ADD CREDENTIAL
          </button>
        </div>
      )}
    </div>
  );
}
