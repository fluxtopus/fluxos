'use client';

import { useState, useMemo } from 'react';
import {
  ArrowPathIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  EyeIcon,
  PencilSquareIcon,
  TrashIcon,
  LockClosedIcon,
  CheckCircleIcon,
  TagIcon,
  CubeIcon,
  ChartBarIcon,
  FunnelIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { Dialog, DialogPanel, DialogTitle, Transition, TransitionChild } from '@headlessui/react';
import { Fragment } from 'react';
import Link from 'next/link';
import {
  useCapabilities,
  useCapabilitySearch,
  useDeleteCapability,
} from '../../../hooks/useCapabilities';
import { getUniqueDomains, calculateSuccessRate } from '../../../services/capabilityApi';
import type { Capability } from '../../../types/capability';

export default function CapabilitiesPage() {
  // State for filters
  const [domainFilter, setDomainFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [includeSystem, setIncludeSystem] = useState(true);
  const [activeOnly, setActiveOnly] = useState(true);

  // Hooks
  const { capabilities, total, isLoading, error, refetch } = useCapabilities({
    domain: domainFilter || undefined,
    include_system: includeSystem,
    active_only: activeOnly,
    limit: 500,
  });
  const { search, results: searchResults, isLoading: isSearching } = useCapabilitySearch();
  const { deleteCapability, isLoading: isDeleting, error: deleteError } = useDeleteCapability();

  // Dialog states
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showDetailsDialog, setShowDetailsDialog] = useState(false);
  const [selectedCapability, setSelectedCapability] = useState<Capability | null>(null);

  // Get unique domains for the filter dropdown
  const domains = useMemo(() => getUniqueDomains(capabilities), [capabilities]);

  // Filter capabilities by search query (client-side filtering)
  const displayedCapabilities = useMemo(() => {
    if (!searchQuery.trim()) {
      return capabilities;
    }
    const query = searchQuery.toLowerCase();
    return capabilities.filter((cap) => {
      return (
        cap.name.toLowerCase().includes(query) ||
        cap.description?.toLowerCase().includes(query) ||
        cap.agent_type.toLowerCase().includes(query) ||
        cap.domain?.toLowerCase().includes(query) ||
        cap.tags?.some((tag) => tag.toLowerCase().includes(query))
      );
    });
  }, [capabilities, searchQuery]);

  // Stats
  const stats = useMemo(() => ({
    total: capabilities.length,
    system: capabilities.filter((c) => c.is_system).length,
    custom: capabilities.filter((c) => !c.is_system).length,
    active: capabilities.filter((c) => c.is_active).length,
  }), [capabilities]);

  // Handlers
  const handleDelete = async () => {
    if (!selectedCapability) return;
    try {
      await deleteCapability(selectedCapability.id);
      setShowDeleteDialog(false);
      setSelectedCapability(null);
      refetch();
    } catch {
      // Error handled by hook
    }
  };

  const openDeleteDialog = (cap: Capability) => {
    setSelectedCapability(cap);
    setShowDeleteDialog(true);
  };

  const openDetailsDialog = (cap: Capability) => {
    setSelectedCapability(cap);
    setShowDetailsDialog(true);
  };

  const clearFilters = () => {
    setDomainFilter('');
    setIncludeSystem(true);
    setActiveOnly(true);
  };

  const hasActiveFilters = domainFilter || !includeSystem || !activeOnly;

  return (
    <div className="min-h-screen bg-[var(--background)]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-mono font-bold tracking-wider text-[var(--foreground)]">
              CAPABILITIES
            </h1>
            <p className="text-sm font-mono text-[var(--muted-foreground)] mt-1">
              AI agent capabilities and configurations
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Search */}
            <div className="relative">
              <MagnifyingGlassIcon className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" />
              <input
                type="text"
                placeholder="Search capabilities..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-4 py-2 w-48 text-sm font-mono bg-[var(--card)] border border-[var(--border)] rounded-md text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              />
            </div>
            {/* Filter button */}
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-2 px-3 py-2 text-xs font-mono tracking-wider border rounded-md transition-colors ${
                hasActiveFilters
                  ? 'border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10'
                  : 'border-[var(--border)] text-[var(--muted-foreground)] hover:bg-[var(--muted)]'
              }`}
            >
              <FunnelIcon className="w-4 h-4" />
              FILTER
              {hasActiveFilters && (
                <span className="ml-1 w-2 h-2 rounded-full bg-[var(--accent)]" />
              )}
            </button>
            {/* Refresh */}
            <button
              onClick={() => refetch()}
              className="flex items-center gap-2 px-3 py-2 text-xs font-mono tracking-wider border border-[var(--border)] rounded-md text-[var(--muted-foreground)] hover:bg-[var(--muted)] transition-colors"
            >
              <ArrowPathIcon className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              REFRESH
            </button>
            {/* Create - Link to future create page */}
            <Link
              href="/capabilities/new"
              className="flex items-center gap-2 px-3 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity"
            >
              <PlusIcon className="w-4 h-4" />
              CREATE
            </Link>
          </div>
        </div>

        {/* Filter panel */}
        {showFilters && (
          <div className="mb-6 p-4 bg-[var(--card)] border border-[var(--border)] rounded-lg">
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">
                FILTERS
              </span>
              {hasActiveFilters && (
                <button
                  onClick={clearFilters}
                  className="text-xs font-mono text-[var(--accent)] hover:underline"
                >
                  Clear all
                </button>
              )}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Domain filter */}
              <div>
                <label className="block text-xs font-mono text-[var(--muted-foreground)] mb-1">
                  DOMAIN
                </label>
                <select
                  value={domainFilter}
                  onChange={(e) => setDomainFilter(e.target.value)}
                  className="w-full px-3 py-2 text-sm font-mono bg-[var(--background)] border border-[var(--border)] rounded-md text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                >
                  <option value="">All domains</option>
                  {domains.map((domain) => (
                    <option key={domain} value={domain}>
                      {domain}
                    </option>
                  ))}
                </select>
              </div>
              {/* Include system toggle */}
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeSystem}
                    onChange={(e) => setIncludeSystem(e.target.checked)}
                    className="w-4 h-4 rounded border-[var(--border)] text-[var(--accent)] focus:ring-[var(--accent)]"
                  />
                  <span className="text-sm font-mono text-[var(--foreground)]">
                    Include system
                  </span>
                </label>
              </div>
              {/* Active only toggle */}
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={activeOnly}
                    onChange={(e) => setActiveOnly(e.target.checked)}
                    className="w-4 h-4 rounded border-[var(--border)] text-[var(--accent)] focus:ring-[var(--accent)]"
                  />
                  <span className="text-sm font-mono text-[var(--foreground)]">
                    Active only
                  </span>
                </label>
              </div>
            </div>
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-8">
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
            <p className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">TOTAL</p>
            <p className="text-2xl font-mono font-bold text-[var(--foreground)] mt-1">{stats.total}</p>
          </div>
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
            <p className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">SYSTEM</p>
            <p className="text-2xl font-mono font-bold text-purple-500 mt-1">{stats.system}</p>
          </div>
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
            <p className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">CUSTOM</p>
            <p className="text-2xl font-mono font-bold text-green-500 mt-1">{stats.custom}</p>
          </div>
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
            <p className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">ACTIVE</p>
            <p className="text-2xl font-mono font-bold text-blue-500 mt-1">{stats.active}</p>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/50 rounded-lg">
            <p className="text-sm font-mono text-red-500">{error.message}</p>
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-8">
            <div className="flex flex-col items-center gap-4">
              <ArrowPathIcon className="w-8 h-8 text-[var(--accent)] animate-spin" />
              <p className="text-sm font-mono text-[var(--muted-foreground)]">Loading capabilities...</p>
            </div>
          </div>
        )}

        {/* Capabilities Table */}
        {!isLoading && displayedCapabilities.length > 0 && (
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">NAME</th>
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">DOMAIN</th>
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">TYPE</th>
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">USAGE</th>
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">STATUS</th>
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">ACTIONS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {displayedCapabilities.map((cap) => {
                  const successRate = calculateSuccessRate(cap);
                  return (
                    <tr key={cap.id} className="hover:bg-[var(--muted)]/50 transition-colors">
                      <td className="px-4 py-3">
                        <div>
                          <Link
                            href={`/capabilities/${cap.id}`}
                            className="text-sm font-mono font-medium text-[var(--foreground)] hover:text-[var(--accent)] transition-colors"
                          >
                            {cap.name}
                          </Link>
                          {cap.description && (
                            <p className="text-xs font-mono text-[var(--muted-foreground)] line-clamp-1 max-w-[250px]">
                              {cap.description}
                            </p>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {cap.domain ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono bg-[var(--muted)] rounded">
                            <CubeIcon className="w-3 h-3" />
                            {cap.domain}
                          </span>
                        ) : (
                          <span className="text-xs font-mono text-[var(--muted-foreground)]">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {cap.is_system ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono bg-purple-500/10 text-purple-500 border border-purple-500/30 rounded">
                            <LockClosedIcon className="w-3 h-3" />
                            System
                          </span>
                        ) : cap.can_edit ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono bg-green-500/10 text-green-500 border border-green-500/30 rounded">
                            <CheckCircleIcon className="w-3 h-3" />
                            Custom
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 text-xs font-mono border border-[var(--border)] rounded">
                            Shared
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-mono text-[var(--foreground)]">
                            {cap.usage_count}
                          </span>
                          {successRate !== null && (
                            <span className={`text-xs font-mono ${successRate >= 80 ? 'text-green-500' : successRate >= 50 ? 'text-yellow-500' : 'text-red-500'}`}>
                              ({successRate.toFixed(0)}%)
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {cap.is_active ? (
                          <span className="inline-flex items-center px-2 py-0.5 text-xs font-mono bg-green-500 text-white rounded">
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 text-xs font-mono bg-[var(--muted)] text-[var(--muted-foreground)] rounded">
                            Inactive
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Link
                            href={`/capabilities/${cap.id}`}
                            className="p-1.5 rounded border border-[var(--border)] hover:bg-[var(--muted)] transition-colors"
                            title="View details"
                          >
                            <EyeIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                          </Link>
                          {cap.can_edit && !cap.is_system && (
                            <>
                              <Link
                                href={`/capabilities/${cap.id}/edit`}
                                className="p-1.5 rounded border border-[var(--border)] hover:bg-[var(--muted)] transition-colors"
                                title="Edit capability"
                              >
                                <PencilSquareIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                              </Link>
                              <button
                                onClick={() => openDeleteDialog(cap)}
                                className="p-1.5 rounded hover:bg-red-500/10 transition-colors"
                                title="Delete capability"
                              >
                                <TrashIcon className="w-4 h-4 text-[var(--muted-foreground)] hover:text-red-500" />
                              </button>
                            </>
                          )}
                          {cap.is_system && (
                            <span className="text-xs font-mono text-[var(--muted-foreground)] flex items-center gap-1">
                              <LockClosedIcon className="w-3 h-3" />
                              Read-only
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && displayedCapabilities.length === 0 && (
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-12 text-center">
            <p className="text-lg font-mono text-[var(--muted-foreground)] mb-2">No capabilities found</p>
            <p className="text-sm font-mono text-[var(--muted-foreground)] mb-4">
              {searchQuery || hasActiveFilters
                ? 'Try adjusting your filters or search query'
                : 'Create your first custom capability'}
            </p>
            {!searchQuery && !hasActiveFilters && (
              <Link
                href="/capabilities/new"
                className="inline-flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity"
              >
                <PlusIcon className="w-4 h-4" />
                CREATE CAPABILITY
              </Link>
            )}
          </div>
        )}

        {/* Delete Dialog */}
        <Transition appear show={showDeleteDialog} as={Fragment}>
          <Dialog as="div" className="relative z-50" onClose={() => setShowDeleteDialog(false)}>
            <TransitionChild
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0"
              enterTo="opacity-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100"
              leaveTo="opacity-0"
            >
              <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
            </TransitionChild>

            <div className="fixed inset-0 overflow-y-auto">
              <div className="flex min-h-full items-center justify-center p-4">
                <TransitionChild
                  as={Fragment}
                  enter="ease-out duration-200"
                  enterFrom="opacity-0 scale-95"
                  enterTo="opacity-100 scale-100"
                  leave="ease-in duration-150"
                  leaveFrom="opacity-100 scale-100"
                  leaveTo="opacity-0 scale-95"
                >
                  <DialogPanel className="w-full max-w-md bg-[var(--card)] border border-[var(--border)] rounded-lg shadow-xl">
                    <div className="p-6 border-b border-[var(--border)]">
                      <DialogTitle className="flex items-center gap-2 text-lg font-mono font-bold text-[var(--foreground)]">
                        <TrashIcon className="w-5 h-5 text-red-500" />
                        DELETE CAPABILITY
                      </DialogTitle>
                      <p className="text-sm font-mono text-[var(--muted-foreground)] mt-1">
                        Are you sure you want to delete this capability?
                      </p>
                    </div>

                    {selectedCapability && (
                      <div className="p-6 space-y-4">
                        <div>
                          <p className="text-xs font-mono text-[var(--muted-foreground)]">CAPABILITY</p>
                          <p className="text-sm font-mono font-medium text-[var(--foreground)] mt-1">
                            {selectedCapability.name}
                          </p>
                          {selectedCapability.description && (
                            <p className="text-sm font-mono text-[var(--muted-foreground)] mt-1">
                              {selectedCapability.description}
                            </p>
                          )}
                        </div>

                        <div className="p-3 bg-amber-500/10 border border-amber-500/50 rounded-lg">
                          <p className="text-xs font-mono text-amber-500">
                            This is a soft delete. The capability will be deactivated but can be restored later.
                          </p>
                        </div>

                        {deleteError && (
                          <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg">
                            <p className="text-sm font-mono text-red-500">{deleteError.message}</p>
                          </div>
                        )}
                      </div>
                    )}

                    <div className="p-6 border-t border-[var(--border)] flex justify-end gap-3">
                      <button
                        onClick={() => {
                          setShowDeleteDialog(false);
                          setSelectedCapability(null);
                        }}
                        className="px-4 py-2 text-xs font-mono tracking-wider border border-[var(--border)] rounded-md text-[var(--muted-foreground)] hover:bg-[var(--muted)] transition-colors"
                      >
                        CANCEL
                      </button>
                      <button
                        onClick={handleDelete}
                        disabled={isDeleting}
                        className="flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-red-500 text-white rounded-md hover:bg-red-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isDeleting ? (
                          <ArrowPathIcon className="w-4 h-4 animate-spin" />
                        ) : (
                          <TrashIcon className="w-4 h-4" />
                        )}
                        DELETE
                      </button>
                    </div>
                  </DialogPanel>
                </TransitionChild>
              </div>
            </div>
          </Dialog>
        </Transition>

        {/* Details Dialog */}
        <Transition appear show={showDetailsDialog} as={Fragment}>
          <Dialog as="div" className="relative z-50" onClose={() => setShowDetailsDialog(false)}>
            <TransitionChild
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0"
              enterTo="opacity-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100"
              leaveTo="opacity-0"
            >
              <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
            </TransitionChild>

            <div className="fixed inset-0 overflow-y-auto">
              <div className="flex min-h-full items-center justify-center p-4">
                <TransitionChild
                  as={Fragment}
                  enter="ease-out duration-200"
                  enterFrom="opacity-0 scale-95"
                  enterTo="opacity-100 scale-100"
                  leave="ease-in duration-150"
                  leaveFrom="opacity-100 scale-100"
                  leaveTo="opacity-0 scale-95"
                >
                  <DialogPanel className="w-full max-w-2xl bg-[var(--card)] border border-[var(--border)] rounded-lg shadow-xl">
                    <div className="p-6 border-b border-[var(--border)]">
                      <DialogTitle className="text-lg font-mono font-bold text-[var(--foreground)]">
                        CAPABILITY DETAILS
                      </DialogTitle>
                      <p className="text-sm font-mono text-[var(--muted-foreground)] mt-1">
                        {selectedCapability?.name}
                      </p>
                    </div>

                    {selectedCapability && (
                      <div className="p-6 space-y-6 max-h-[60vh] overflow-y-auto">
                        {/* Basic info */}
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">AGENT TYPE</p>
                            <code className="text-sm font-mono bg-[var(--muted)] px-2 py-1 rounded mt-1 inline-block">
                              {selectedCapability.agent_type}
                            </code>
                          </div>
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">DOMAIN</p>
                            <p className="text-sm font-mono text-[var(--foreground)] mt-1">
                              {selectedCapability.domain || '-'}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">TASK TYPE</p>
                            <p className="text-sm font-mono text-[var(--foreground)] mt-1">
                              {selectedCapability.task_type}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">VERSION</p>
                            <p className="text-sm font-mono text-[var(--foreground)] mt-1">
                              v{selectedCapability.version}
                            </p>
                          </div>
                        </div>

                        {/* Description */}
                        {selectedCapability.description && (
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">DESCRIPTION</p>
                            <p className="text-sm font-mono text-[var(--foreground)] mt-1">
                              {selectedCapability.description}
                            </p>
                          </div>
                        )}

                        {/* Tags */}
                        {selectedCapability.tags && selectedCapability.tags.length > 0 && (
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">TAGS</p>
                            <div className="flex flex-wrap gap-2 mt-2">
                              {selectedCapability.tags.map((tag) => (
                                <span
                                  key={tag}
                                  className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono bg-[var(--muted)] rounded"
                                >
                                  <TagIcon className="w-3 h-3" />
                                  {tag}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Usage stats */}
                        <div>
                          <p className="text-xs font-mono text-[var(--muted-foreground)] mb-2">USAGE STATISTICS</p>
                          <div className="grid grid-cols-3 gap-4">
                            <div className="p-3 bg-[var(--muted)] rounded-lg">
                              <p className="text-xs font-mono text-[var(--muted-foreground)]">Total Uses</p>
                              <p className="text-lg font-mono font-bold text-[var(--foreground)]">
                                {selectedCapability.usage_count}
                              </p>
                            </div>
                            <div className="p-3 bg-[var(--muted)] rounded-lg">
                              <p className="text-xs font-mono text-[var(--muted-foreground)]">Successes</p>
                              <p className="text-lg font-mono font-bold text-green-500">
                                {selectedCapability.success_count}
                              </p>
                            </div>
                            <div className="p-3 bg-[var(--muted)] rounded-lg">
                              <p className="text-xs font-mono text-[var(--muted-foreground)]">Failures</p>
                              <p className="text-lg font-mono font-bold text-red-500">
                                {selectedCapability.failure_count}
                              </p>
                            </div>
                          </div>
                        </div>

                        {/* Status badges */}
                        <div className="flex items-center gap-3">
                          {selectedCapability.is_system ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono bg-purple-500/10 text-purple-500 border border-purple-500/30 rounded">
                              <LockClosedIcon className="w-3 h-3" />
                              System
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono bg-green-500/10 text-green-500 border border-green-500/30 rounded">
                              <CheckCircleIcon className="w-3 h-3" />
                              Custom
                            </span>
                          )}
                          {selectedCapability.is_active ? (
                            <span className="inline-flex items-center px-2 py-0.5 text-xs font-mono bg-green-500 text-white rounded">
                              Active
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 text-xs font-mono bg-[var(--muted)] text-[var(--muted-foreground)] rounded">
                              Inactive
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    <div className="p-6 border-t border-[var(--border)] flex justify-end gap-3">
                      <button
                        onClick={() => setShowDetailsDialog(false)}
                        className="px-4 py-2 text-xs font-mono tracking-wider border border-[var(--border)] rounded-md text-[var(--muted-foreground)] hover:bg-[var(--muted)] transition-colors"
                      >
                        CLOSE
                      </button>
                      {selectedCapability?.can_edit && !selectedCapability?.is_system && (
                        <Link
                          href={`/capabilities/${selectedCapability.id}/edit`}
                          onClick={() => setShowDetailsDialog(false)}
                          className="flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity"
                        >
                          <PencilSquareIcon className="w-4 h-4" />
                          EDIT
                        </Link>
                      )}
                    </div>
                  </DialogPanel>
                </TransitionChild>
              </div>
            </div>
          </Dialog>
        </Transition>
      </div>
    </div>
  );
}
