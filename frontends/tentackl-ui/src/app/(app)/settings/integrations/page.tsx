'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  TrashIcon,
  ArrowPathIcon,
  PlusIcon,
  PencilIcon,
  LinkIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  ChevronUpDownIcon,
  CheckIcon,
} from '@heroicons/react/24/outline';
import * as Dialog from '@radix-ui/react-dialog';
import type {
  Integration,
  IntegrationProvider,
  IntegrationDirection,
  IntegrationStatus,
} from '../../../../types/integration';
import { PROVIDER_CONFIG, PROVIDER_OPTIONS, DIRECTION_CONFIG, STATUS_CONFIG } from '../../../../types/integration';
import { ProviderIcon } from '../../../../components/Integration';
import * as integrationApi from '../../../../services/integrationApi';

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editingIntegration, setEditingIntegration] = useState<Integration | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    loadIntegrations();
  }, []);

  const loadIntegrations = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await integrationApi.listIntegrations();
      setIntegrations(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load integrations');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDelete = async (integrationId: string) => {
    if (!confirm('Are you sure you want to delete this integration?')) return;

    setDeletingId(integrationId);
    try {
      await integrationApi.deleteIntegration(integrationId);
      setIntegrations(prev => prev.filter(i => i.id !== integrationId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete integration');
    } finally {
      setDeletingId(null);
    }
  };

  const handleCreated = (integration: Integration) => {
    setIntegrations(prev => [integration, ...prev]);
    setCreateDialogOpen(false);
  };

  const handleUpdated = (integration: Integration) => {
    setIntegrations(prev => prev.map(i => i.id === integration.id ? integration : i));
    setEditingIntegration(null);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">
            LOADING...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header with actions */}
      <div className="flex items-center justify-between mb-6">
        <p className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">
          EXTERNAL SERVICE CONNECTIONS
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={loadIntegrations}
            disabled={isLoading}
            className="p-2 rounded border border-[var(--border)] bg-[var(--background)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:border-[var(--accent)] transition-colors disabled:opacity-50"
          >
            <ArrowPathIcon className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setCreateDialogOpen(true)}
            className="flex items-center gap-2 px-3 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity"
          >
            <PlusIcon className="w-4 h-4" />
            CREATE
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 p-4 rounded border border-[var(--destructive)]/30 bg-[var(--card)] text-xs font-mono text-[var(--destructive)]">
          {error}
        </div>
      )}

      {/* Empty state */}
      {integrations.length === 0 && (
        <div className="text-center py-20">
          <div className="inline-block p-4 rounded border border-[var(--border)] mb-4">
            <LinkIcon className="w-8 h-8 text-[var(--muted-foreground)]" />
          </div>
          <p className="text-sm text-[var(--muted-foreground)] mb-1">
            No integrations configured
          </p>
          <p className="text-xs font-mono text-[var(--muted-foreground)]/60 max-w-sm mx-auto mb-6">
            Connect external services like Discord, Slack, or GitHub to enable
            notifications and webhook triggers.
          </p>
          <button
            onClick={() => setCreateDialogOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity"
          >
            <PlusIcon className="w-4 h-4" />
            CREATE
          </button>
        </div>
      )}

      {/* Integrations list */}
      {integrations.length > 0 && (
        <div className="space-y-2">
          {integrations.map((integration) => (
            <IntegrationRow
              key={integration.id}
              integration={integration}
              onEdit={() => setEditingIntegration(integration)}
              onDelete={() => handleDelete(integration.id)}
              isDeleting={deletingId === integration.id}
            />
          ))}
        </div>
      )}

      {/* Create Dialog */}
      <IntegrationFormDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onSuccess={handleCreated}
      />

      {/* Edit Dialog */}
      {editingIntegration && (
        <IntegrationFormDialog
          open={!!editingIntegration}
          onOpenChange={(open) => !open && setEditingIntegration(null)}
          integration={editingIntegration}
          onSuccess={handleUpdated}
        />
      )}
    </div>
  );
}

// ============================================
// Integration Row Component
// ============================================

interface IntegrationRowProps {
  integration: Integration;
  onEdit: () => void;
  onDelete: () => void;
  isDeleting: boolean;
}

function ConfigBadge({ configured, label }: { configured: boolean; label: string }) {
  if (configured) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-mono tracking-wider text-emerald-500">
        <CheckCircleIcon className="w-3 h-3" />
        {label}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-mono tracking-wider text-[var(--destructive)]">
      <ExclamationCircleIcon className="w-3 h-3" />
      {label}
    </span>
  );
}

function IntegrationRow({ integration, onEdit, onDelete, isDeleting }: IntegrationRowProps) {
  const router = useRouter();
  const provider = PROVIDER_CONFIG[integration.provider];
  const status = STATUS_CONFIG[integration.status];
  const direction = DIRECTION_CONFIG[integration.direction];

  const needsOutbound = integration.direction === 'outbound' || integration.direction === 'bidirectional';
  const needsInbound = integration.direction === 'inbound' || integration.direction === 'bidirectional';

  return (
    <div
      className="group flex items-center gap-4 p-4 rounded border border-[var(--border)] bg-[var(--card)] hover:border-[var(--accent)]/50 transition-colors cursor-pointer"
      onClick={() => router.push(`/settings/integrations/${integration.id}`)}
    >
      {/* Provider icon */}
      <div className="flex-shrink-0 w-10 h-10 rounded border border-[var(--border)] bg-[var(--muted)] flex items-center justify-center">
        <ProviderIcon provider={integration.provider} size={20} />
      </div>

      {/* Details */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-[var(--foreground)] truncate">
            {integration.name}
          </p>
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
          {integration.webhook_url && (
            <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)] flex items-center gap-1">
              <LinkIcon className="w-3 h-3" />
              WEBHOOK
            </span>
          )}
          {needsOutbound && (
            <ConfigBadge
              configured={!!integration.outbound_config}
              label={integration.outbound_config ? 'OUTBOUND READY' : 'OUTBOUND NOT CONFIGURED'}
            />
          )}
          {needsInbound && (
            <ConfigBadge
              configured={!!integration.inbound_config}
              label={integration.inbound_config ? 'INBOUND READY' : 'INBOUND NOT CONFIGURED'}
            />
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={(e) => { e.stopPropagation(); onEdit(); }}
          className="p-2 rounded border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:border-[var(--accent)] transition-colors"
          title="Edit integration"
        >
          <PencilIcon className="w-4 h-4" />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          disabled={isDeleting}
          className="p-2 rounded border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--destructive)] hover:border-[var(--destructive)]/50 transition-colors disabled:opacity-50"
          title="Delete integration"
        >
          {isDeleting ? (
            <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
          ) : (
            <TrashIcon className="w-4 h-4" />
          )}
        </button>
      </div>
    </div>
  );
}

// ============================================
// Integration Form Dialog
// ============================================

interface IntegrationFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  integration?: Integration;
  onSuccess: (integration: Integration) => void;
}

function IntegrationFormDialog({ open, onOpenChange, integration, onSuccess }: IntegrationFormDialogProps) {
  const isEditing = !!integration;
  const [provider, setProvider] = useState<IntegrationProvider>(integration?.provider || 'discord');
  const [name, setName] = useState(integration?.name || '');
  const [nameManuallyEdited, setNameManuallyEdited] = useState(false);
  const [direction, setDirection] = useState<IntegrationDirection>(integration?.direction || 'bidirectional');
  const [webhookUrl, setWebhookUrl] = useState(integration?.webhook_url || '');
  const [status, setStatus] = useState<IntegrationStatus>(integration?.status || 'active');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [providerDropdownOpen, setProviderDropdownOpen] = useState(false);

  // Get provider config
  const providerConfig = PROVIDER_CONFIG[provider];
  const supportedDirections = providerConfig.supportedDirections;

  // Show webhook URL field for outbound integrations or custom webhooks
  const showWebhookUrl = direction === 'outbound' || direction === 'bidirectional' || provider === 'custom_webhook';

  // Reset form when dialog opens/closes
  useEffect(() => {
    if (open) {
      const initialProvider = integration?.provider || 'discord';
      setProvider(initialProvider);
      setName(integration?.name || PROVIDER_CONFIG[initialProvider].defaultName);
      setNameManuallyEdited(!!integration);
      setDirection(integration?.direction || PROVIDER_CONFIG[initialProvider].defaultDirection);
      setWebhookUrl(integration?.webhook_url || '');
      setStatus(integration?.status || 'active');
      setError(null);
      setProviderDropdownOpen(false);
    }
  }, [open, integration]);

  // When provider changes (during create), update defaults
  const handleProviderChange = (newProvider: IntegrationProvider) => {
    setProvider(newProvider);
    setProviderDropdownOpen(false);

    const config = PROVIDER_CONFIG[newProvider];

    // Update name if user hasn't manually edited it
    if (!nameManuallyEdited) {
      setName(config.defaultName);
    }

    // Set default direction for this provider
    setDirection(config.defaultDirection);
  };

  const handleNameChange = (value: string) => {
    setName(value);
    setNameManuallyEdited(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Name is required');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      let result: Integration;
      if (isEditing && integration) {
        result = await integrationApi.updateIntegration(integration.id, {
          name: name.trim(),
          status,
          webhook_url: webhookUrl.trim() || undefined,
        });
      } else {
        result = await integrationApi.createIntegration({
          name: name.trim(),
          provider,
          direction,
          webhook_url: webhookUrl.trim() || undefined,
        });
      }
      onSuccess(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save integration');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-[50%] top-[50%] translate-x-[-50%] translate-y-[-50%] bg-[var(--card)] border border-[var(--border)] rounded-lg shadow-xl w-full max-w-md p-6 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <Dialog.Title className="text-lg font-bold text-[var(--foreground)] mb-1">
            {isEditing ? 'Edit Integration' : 'New Integration'}
          </Dialog.Title>
          <Dialog.Description className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider mb-6">
            {isEditing ? 'UPDATE INTEGRATION SETTINGS' : 'CONNECT AN EXTERNAL SERVICE'}
          </Dialog.Description>

          <form onSubmit={handleSubmit}>
            {/* Provider (only for create) - NOW FIRST */}
            {!isEditing && (
              <div className="mb-4">
                <label className="block text-xs font-mono tracking-wider text-[var(--muted-foreground)] mb-2">
                  PROVIDER
                </label>
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setProviderDropdownOpen(!providerDropdownOpen)}
                    className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-sm font-mono rounded border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] hover:border-[var(--accent)] focus:outline-none focus:border-[var(--accent)] transition-colors"
                  >
                    <span className="flex items-center gap-3">
                      <ProviderIcon provider={provider} size={20} />
                      <span>{providerConfig.label}</span>
                    </span>
                    <ChevronUpDownIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                  </button>

                  {/* Dropdown */}
                  {providerDropdownOpen && (
                    <div className="absolute z-50 w-full mt-1 py-1 rounded border border-[var(--border)] bg-[var(--card)] shadow-lg max-h-64 overflow-auto">
                      {PROVIDER_OPTIONS.map((p) => {
                        const config = PROVIDER_CONFIG[p];
                        const isSelected = p === provider;
                        return (
                          <button
                            key={p}
                            type="button"
                            onClick={() => handleProviderChange(p)}
                            className={`w-full flex items-center gap-3 px-3 py-2.5 text-sm font-mono text-left hover:bg-[var(--muted)] transition-colors ${
                              isSelected ? 'bg-[var(--accent)]/10' : ''
                            }`}
                          >
                            <ProviderIcon provider={p} size={20} />
                            <span className="flex-1">{config.label}</span>
                            {isSelected && (
                              <CheckIcon className="w-4 h-4 text-[var(--accent)]" />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Name - NOW SECOND */}
            <div className="mb-4">
              <label className="block text-xs font-mono tracking-wider text-[var(--muted-foreground)] mb-2">
                NAME
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder={providerConfig.defaultName}
                className="w-full px-3 py-2 text-sm font-mono rounded border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]/50 focus:outline-none focus:border-[var(--accent)]"
              />
            </div>

            {/* Direction (only for create) - NOW THIRD, filtered by provider */}
            {!isEditing && supportedDirections.length > 1 && (
              <div className="mb-4">
                <label className="block text-xs font-mono tracking-wider text-[var(--muted-foreground)] mb-2">
                  DIRECTION
                </label>
                <div className={`grid gap-2 ${supportedDirections.length === 2 ? 'grid-cols-2' : 'grid-cols-3'}`}>
                  {supportedDirections.map((d) => {
                    const dirConfig = DIRECTION_CONFIG[d];
                    return (
                      <button
                        key={d}
                        type="button"
                        onClick={() => setDirection(d)}
                        className={`flex flex-col items-center gap-1 p-3 rounded border transition-colors ${
                          direction === d
                            ? 'border-[var(--accent)] bg-[var(--accent)]/10'
                            : 'border-[var(--border)] hover:border-[var(--accent)]/50'
                        }`}
                      >
                        <span className="text-xs font-mono tracking-wider">{dirConfig.label.toUpperCase()}</span>
                        <span className="text-[9px] font-mono text-[var(--muted-foreground)]">
                          {dirConfig.description}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Single direction notice */}
            {!isEditing && supportedDirections.length === 1 && (
              <div className="mb-4">
                <label className="block text-xs font-mono tracking-wider text-[var(--muted-foreground)] mb-2">
                  DIRECTION
                </label>
                <div className="px-3 py-2.5 text-sm font-mono rounded border border-[var(--border)] bg-[var(--muted)]/50 text-[var(--muted-foreground)]">
                  {DIRECTION_CONFIG[supportedDirections[0]].label} — {DIRECTION_CONFIG[supportedDirections[0]].description}
                </div>
              </div>
            )}

            {/* Webhook URL */}
            {showWebhookUrl && (
              <div className="mb-4">
                <label className="block text-xs font-mono tracking-wider text-[var(--muted-foreground)] mb-2">
                  WEBHOOK URL
                </label>
                <input
                  type="url"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  placeholder="https://..."
                  className="w-full px-3 py-2 text-sm font-mono rounded border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]/50 focus:outline-none focus:border-[var(--accent)]"
                />
                {providerConfig.webhookHint && (
                  <p className="mt-1 text-[10px] font-mono text-[var(--muted-foreground)]">
                    {providerConfig.webhookHint}
                  </p>
                )}
              </div>
            )}

            {/* Status (only for edit) */}
            {isEditing && (
              <div className="mb-4">
                <label className="block text-xs font-mono tracking-wider text-[var(--muted-foreground)] mb-2">
                  STATUS
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {(['active', 'paused', 'error'] as IntegrationStatus[]).map((s) => {
                    const config = STATUS_CONFIG[s];
                    return (
                      <button
                        key={s}
                        type="button"
                        onClick={() => setStatus(s)}
                        className={`flex items-center justify-center gap-2 p-3 rounded border transition-colors ${
                          status === s
                            ? 'border-[var(--accent)] bg-[var(--accent)]/10'
                            : 'border-[var(--border)] hover:border-[var(--accent)]/50'
                        }`}
                      >
                        <span className={`w-2 h-2 rounded-full ${config.dotColor}`} />
                        <span className="text-xs font-mono tracking-wider">{config.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="mb-4 p-3 rounded border border-[var(--destructive)]/30 bg-[var(--destructive)]/5 text-xs font-mono text-[var(--destructive)] flex items-center gap-2">
                <ExclamationTriangleIcon className="w-4 h-4 flex-shrink-0" />
                {error}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 mt-6">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="px-4 py-2 text-xs font-mono tracking-wider text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
                >
                  CANCEL
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider text-white rounded border bg-[var(--accent)] border-[var(--accent)] hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {saving && <ArrowPathIcon className="w-3.5 h-3.5 animate-spin" />}
                {isEditing ? 'SAVE' : 'CREATE'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
