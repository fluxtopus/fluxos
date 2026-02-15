'use client';

import React, { useState, useMemo } from 'react';
import * as Select from '@radix-ui/react-select';
import {
  ChevronDownIcon,
  CheckIcon,
  LinkIcon,
  ArrowPathIcon,
  FunnelIcon,
} from '@heroicons/react/24/outline';
import { useIntegrations } from '../../hooks/useIntegrations';
import { ProviderIcon } from './ProviderIcon';
import type {
  Integration,
  IntegrationProvider,
  IntegrationDirection,
  IntegrationStatus,
} from '../../types/integration';

interface IntegrationSelectProps {
  value?: string;
  onChange: (integrationId: string | null, integration: Integration | null) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Filter by direction capability */
  direction?: IntegrationDirection;
  /** Filter by provider */
  provider?: IntegrationProvider;
  /** Only show active integrations */
  activeOnly?: boolean;
  /** Show filter dropdown */
  showFilters?: boolean;
  /** Label displayed above the select */
  label?: string;
  /** Helper text displayed below */
  helperText?: string;
  /** Error message */
  error?: string;
}

const PROVIDER_LABELS: Record<IntegrationProvider, string> = {
  discord: 'Discord',
  slack: 'Slack',
  github: 'GitHub',
  stripe: 'Stripe',
  twitter: 'Twitter',
  custom_webhook: 'Webhook',
};

const DIRECTION_LABELS: Record<IntegrationDirection, string> = {
  inbound: 'Inbound',
  outbound: 'Outbound',
  bidirectional: 'Both',
};

const STATUS_COLORS: Record<IntegrationStatus, { dot: string; text: string }> = {
  active: { dot: 'bg-emerald-500', text: 'text-emerald-500' },
  paused: { dot: 'bg-[var(--muted-foreground)]', text: 'text-[var(--muted-foreground)]' },
  error: { dot: 'bg-[var(--destructive)]', text: 'text-[var(--destructive)]' },
};

/**
 * IntegrationSelect - Dropdown for selecting an integration from the user's configured integrations.
 *
 * Features:
 * - Fetches integrations from API
 * - Displays provider icons and status indicators
 * - Supports filtering by provider, direction, and status
 * - Shows integration status (active/paused/error)
 */
export function IntegrationSelect({
  value,
  onChange,
  placeholder = 'Select an integration...',
  disabled = false,
  direction,
  provider: filterProvider,
  activeOnly = false,
  showFilters = false,
  label,
  helperText,
  error,
}: IntegrationSelectProps) {
  const [providerFilter, setProviderFilter] = useState<IntegrationProvider | undefined>(filterProvider);
  const [directionFilter, setDirectionFilter] = useState<IntegrationDirection | undefined>(direction);

  const {
    integrations,
    isLoading,
    error: fetchError,
    refetch,
  } = useIntegrations(providerFilter, directionFilter, activeOnly ? 'active' : undefined);

  // Apply direction filter if provided (to filter bidirectional by capability)
  const filteredIntegrations = useMemo(() => {
    if (!direction) return integrations;

    return integrations.filter((integration) => {
      if (direction === 'inbound') {
        return integration.direction === 'inbound' || integration.direction === 'bidirectional';
      }
      if (direction === 'outbound') {
        return integration.direction === 'outbound' || integration.direction === 'bidirectional';
      }
      return true;
    });
  }, [integrations, direction]);

  // Find selected integration
  const selectedIntegration = useMemo(() => {
    if (!value) return null;
    return filteredIntegrations.find((i) => i.id === value) || null;
  }, [value, filteredIntegrations]);

  const handleValueChange = (newValue: string) => {
    if (newValue === '__none__') {
      onChange(null, null);
    } else {
      const integration = filteredIntegrations.find((i) => i.id === newValue) || null;
      onChange(newValue, integration);
    }
  };

  const hasError = !!error || !!fetchError;

  return (
    <div className="w-full">
      {/* Label */}
      {label && (
        <label className="block text-xs font-mono tracking-wider text-[var(--muted-foreground)] mb-2">
          {label.toUpperCase()}
        </label>
      )}

      {/* Filters Row */}
      {showFilters && (
        <div className="flex items-center gap-2 mb-2">
          <FunnelIcon className="w-3.5 h-3.5 text-[var(--muted-foreground)]" />

          {/* Provider filter */}
          <Select.Root value={providerFilter || 'all'} onValueChange={(v) => setProviderFilter(v === 'all' ? undefined : v as IntegrationProvider)}>
            <Select.Trigger className="inline-flex items-center gap-1.5 px-2 py-1 text-[10px] font-mono tracking-wider rounded border border-[var(--border)] bg-[var(--card)] hover:border-[var(--accent)]/50 transition-colors">
              <Select.Value placeholder="Provider" />
              <ChevronDownIcon className="w-3 h-3" />
            </Select.Trigger>
            <Select.Portal>
              <Select.Content className="overflow-hidden bg-[var(--card)] rounded border border-[var(--border)] shadow-lg z-50">
                <Select.Viewport className="p-1">
                  <Select.Item value="all" className="relative flex items-center px-6 py-1.5 text-xs font-mono rounded hover:bg-[var(--muted)] data-[highlighted]:bg-[var(--muted)] cursor-pointer">
                    <Select.ItemText>All providers</Select.ItemText>
                  </Select.Item>
                  {(Object.keys(PROVIDER_LABELS) as IntegrationProvider[]).map((p) => (
                    <Select.Item
                      key={p}
                      value={p}
                      className="relative flex items-center px-6 py-1.5 text-xs font-mono rounded hover:bg-[var(--muted)] data-[highlighted]:bg-[var(--muted)] cursor-pointer"
                    >
                      <Select.ItemText>
                        <span className="flex items-center gap-1.5">
                          <ProviderIcon provider={p} size={14} />
                          {PROVIDER_LABELS[p]}
                        </span>
                      </Select.ItemText>
                    </Select.Item>
                  ))}
                </Select.Viewport>
              </Select.Content>
            </Select.Portal>
          </Select.Root>

          {/* Direction filter */}
          {!direction && (
            <Select.Root value={directionFilter || 'all'} onValueChange={(v) => setDirectionFilter(v === 'all' ? undefined : v as IntegrationDirection)}>
              <Select.Trigger className="inline-flex items-center gap-1.5 px-2 py-1 text-[10px] font-mono tracking-wider rounded border border-[var(--border)] bg-[var(--card)] hover:border-[var(--accent)]/50 transition-colors">
                <Select.Value placeholder="Direction" />
                <ChevronDownIcon className="w-3 h-3" />
              </Select.Trigger>
              <Select.Portal>
                <Select.Content className="overflow-hidden bg-[var(--card)] rounded border border-[var(--border)] shadow-lg z-50">
                  <Select.Viewport className="p-1">
                    <Select.Item value="all" className="relative flex items-center px-6 py-1.5 text-xs font-mono rounded hover:bg-[var(--muted)] data-[highlighted]:bg-[var(--muted)] cursor-pointer">
                      <Select.ItemText>All directions</Select.ItemText>
                    </Select.Item>
                    {(Object.keys(DIRECTION_LABELS) as IntegrationDirection[]).map((d) => (
                      <Select.Item
                        key={d}
                        value={d}
                        className="relative flex items-center px-6 py-1.5 text-xs font-mono rounded hover:bg-[var(--muted)] data-[highlighted]:bg-[var(--muted)] cursor-pointer"
                      >
                        <Select.ItemText>{DIRECTION_LABELS[d]}</Select.ItemText>
                      </Select.Item>
                    ))}
                  </Select.Viewport>
                </Select.Content>
              </Select.Portal>
            </Select.Root>
          )}

          {/* Refresh button */}
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isLoading}
            className="p-1 rounded hover:bg-[var(--muted)] transition-colors"
            title="Refresh integrations"
          >
            <ArrowPathIcon className={`w-3.5 h-3.5 text-[var(--muted-foreground)] ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      )}

      {/* Main Select */}
      <Select.Root
        value={value || '__none__'}
        onValueChange={handleValueChange}
        disabled={disabled || isLoading}
      >
        <Select.Trigger
          className={`
            inline-flex w-full items-center justify-between gap-2 px-3 py-2.5
            text-sm font-mono rounded border transition-colors
            ${hasError
              ? 'border-[var(--destructive)] focus:border-[var(--destructive)]'
              : 'border-[var(--border)] focus:border-[var(--accent)]'
            }
            bg-[var(--card)] hover:bg-[var(--muted)]
            disabled:opacity-50 disabled:cursor-not-allowed
          `}
        >
          <Select.Value placeholder={placeholder}>
            {selectedIntegration ? (
              <span className="flex items-center gap-2">
                <ProviderIcon provider={selectedIntegration.provider} size={16} />
                <span className="truncate">{selectedIntegration.name}</span>
                <span className={`w-1.5 h-1.5 rounded-full ${STATUS_COLORS[selectedIntegration.status].dot}`} />
              </span>
            ) : (
              <span className="text-[var(--muted-foreground)]">{placeholder}</span>
            )}
          </Select.Value>
          <Select.Icon>
            {isLoading ? (
              <ArrowPathIcon className="w-4 h-4 animate-spin text-[var(--muted-foreground)]" />
            ) : (
              <ChevronDownIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
            )}
          </Select.Icon>
        </Select.Trigger>

        <Select.Portal>
          <Select.Content className="overflow-hidden bg-[var(--card)] rounded border border-[var(--border)] shadow-lg z-50 min-w-[200px]">
            <Select.Viewport className="p-1">
              {/* None option */}
              <Select.Item
                value="__none__"
                className="relative flex items-center px-3 py-2 text-sm font-mono rounded hover:bg-[var(--muted)] data-[highlighted]:bg-[var(--muted)] cursor-pointer text-[var(--muted-foreground)]"
              >
                <Select.ItemIndicator className="absolute left-1">
                  <CheckIcon className="w-3 h-3" />
                </Select.ItemIndicator>
                <Select.ItemText>
                  <span className="pl-4">No integration</span>
                </Select.ItemText>
              </Select.Item>

              <Select.Separator className="h-px my-1 bg-[var(--border)]" />

              {/* Integrations */}
              {filteredIntegrations.length === 0 && !isLoading ? (
                <div className="px-3 py-4 text-center">
                  <LinkIcon className="w-5 h-5 mx-auto mb-2 text-[var(--muted-foreground)]" />
                  <p className="text-xs font-mono text-[var(--muted-foreground)]">
                    No integrations found
                  </p>
                  <p className="text-[10px] font-mono text-[var(--muted-foreground)]/60 mt-1">
                    Set up integrations in settings
                  </p>
                </div>
              ) : (
                filteredIntegrations.map((integration) => (
                  <Select.Item
                    key={integration.id}
                    value={integration.id}
                    disabled={integration.status === 'error'}
                    className="relative flex items-center px-3 py-2 text-sm font-mono rounded hover:bg-[var(--muted)] data-[highlighted]:bg-[var(--muted)] cursor-pointer data-[disabled]:opacity-50 data-[disabled]:cursor-not-allowed"
                  >
                    <Select.ItemIndicator className="absolute left-1">
                      <CheckIcon className="w-3 h-3 text-[var(--accent)]" />
                    </Select.ItemIndicator>
                    <Select.ItemText>
                      <span className="flex items-center gap-2 pl-4">
                        <span className="flex-shrink-0">
                          <ProviderIcon provider={integration.provider} size={16} />
                        </span>
                        <span className="truncate flex-1">{integration.name}</span>
                        <span className="flex items-center gap-1.5 flex-shrink-0">
                          <span className={`w-1.5 h-1.5 rounded-full ${STATUS_COLORS[integration.status].dot}`} />
                          <span className={`text-[10px] tracking-wider ${STATUS_COLORS[integration.status].text}`}>
                            {integration.status.toUpperCase()}
                          </span>
                        </span>
                      </span>
                    </Select.ItemText>
                  </Select.Item>
                ))
              )}
            </Select.Viewport>

            {/* Footer hint */}
            <div className="px-3 py-2 border-t border-[var(--border)] bg-[var(--muted)]">
              <p className="text-[10px] font-mono text-[var(--muted-foreground)] tracking-wider">
                <kbd className="px-1 py-0.5 bg-[var(--card)] rounded border border-[var(--border)] text-[10px]">↑↓</kbd> NAVIGATE
                {' '}
                <kbd className="px-1 py-0.5 bg-[var(--card)] rounded border border-[var(--border)] text-[10px]">ENTER</kbd> SELECT
              </p>
            </div>
          </Select.Content>
        </Select.Portal>
      </Select.Root>

      {/* Helper text / Error */}
      {(helperText || error || fetchError) && (
        <p className={`mt-1.5 text-[10px] font-mono tracking-wider ${hasError ? 'text-[var(--destructive)]' : 'text-[var(--muted-foreground)]'}`}>
          {error || (fetchError && 'Failed to load integrations') || helperText}
        </p>
      )}
    </div>
  );
}

/**
 * IntegrationDisplay - Read-only display of a selected integration
 */
export function IntegrationDisplay({ integration }: { integration: Integration }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded border border-[var(--border)] bg-[var(--card)]">
      <span className="flex-shrink-0">
        <ProviderIcon provider={integration.provider} size={16} />
      </span>
      <span className="flex-1 text-sm font-mono truncate">{integration.name}</span>
      <span className="flex items-center gap-1.5 flex-shrink-0">
        <span className={`w-1.5 h-1.5 rounded-full ${STATUS_COLORS[integration.status].dot}`} />
        <span className={`text-[10px] font-mono tracking-wider ${STATUS_COLORS[integration.status].text}`}>
          {integration.status.toUpperCase()}
        </span>
      </span>
    </div>
  );
}
