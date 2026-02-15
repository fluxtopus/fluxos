'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  PencilSquareIcon,
  TrashIcon,
  LockClosedIcon,
  CheckCircleIcon,
  TagIcon,
  CubeIcon,
  ChartBarIcon,
  ClipboardDocumentIcon,
  CodeBracketIcon,
  BoltIcon,
  DocumentTextIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';
import { Dialog, DialogPanel, DialogTitle, Transition, TransitionChild } from '@headlessui/react';
import { Fragment } from 'react';
import { useCapability, useDeleteCapability } from '../../../../hooks/useCapabilities';
import { calculateSuccessRate } from '../../../../services/capabilityApi';

export default function CapabilityDetailPage() {
  const params = useParams();
  const router = useRouter();
  const capabilityId = params.id as string;

  const { capability, isLoading, error, refetch } = useCapability(capabilityId);
  const { deleteCapability, isLoading: isDeleting, error: deleteError } = useDeleteCapability();

  // UI state
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showYamlSection, setShowYamlSection] = useState(true);
  const [showInputsSection, setShowInputsSection] = useState(true);
  const [showOutputsSection, setShowOutputsSection] = useState(true);
  const [showHintsSection, setShowHintsSection] = useState(true);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const handleDelete = async () => {
    try {
      await deleteCapability(capabilityId);
      setShowDeleteDialog(false);
      router.push('/capabilities');
    } catch {
      // Error handled by hook
    }
  };

  const copyToClipboard = async (text: string, field: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const formatJson = (obj: unknown): string => {
    if (!obj || (typeof obj === 'object' && Object.keys(obj as object).length === 0)) {
      return 'No data';
    }
    return JSON.stringify(obj, null, 2);
  };

  const successRate = capability ? calculateSuccessRate(capability) : null;

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[var(--background)]">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-12">
            <div className="flex flex-col items-center gap-4">
              <ArrowPathIcon className="w-8 h-8 text-[var(--accent)] animate-spin" />
              <p className="text-sm font-mono text-[var(--muted-foreground)]">Loading capability...</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !capability) {
    return (
      <div className="min-h-screen bg-[var(--background)]">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-12 text-center">
            <p className="text-lg font-mono text-red-500 mb-4">
              {error?.message || 'Capability not found'}
            </p>
            <Link
              href="/capabilities"
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider border border-[var(--border)] rounded-md text-[var(--muted-foreground)] hover:bg-[var(--muted)] transition-colors"
            >
              <ArrowLeftIcon className="w-4 h-4" />
              BACK TO CAPABILITIES
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--background)]">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <Link
              href="/capabilities"
              className="p-2 rounded border border-[var(--border)] hover:bg-[var(--muted)] transition-colors"
            >
              <ArrowLeftIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
            </Link>
            <div>
              <h1 className="text-2xl font-mono font-bold tracking-wider text-[var(--foreground)]">
                {capability.name}
              </h1>
              <div className="flex items-center gap-2 mt-1">
                <code className="text-sm font-mono text-[var(--muted-foreground)] bg-[var(--muted)] px-2 py-0.5 rounded">
                  {capability.agent_type}
                </code>
                <span className="text-sm font-mono text-[var(--muted-foreground)]">v{capability.version}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => refetch()}
              className="flex items-center gap-2 px-3 py-2 text-xs font-mono tracking-wider border border-[var(--border)] rounded-md text-[var(--muted-foreground)] hover:bg-[var(--muted)] transition-colors"
            >
              <ArrowPathIcon className="w-4 h-4" />
              REFRESH
            </button>
            {capability.can_edit && !capability.is_system && (
              <>
                <Link
                  href={`/capabilities/${capabilityId}/edit`}
                  className="flex items-center gap-2 px-3 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity"
                >
                  <PencilSquareIcon className="w-4 h-4" />
                  EDIT
                </Link>
                <button
                  onClick={() => setShowDeleteDialog(true)}
                  className="flex items-center gap-2 px-3 py-2 text-xs font-mono tracking-wider border border-red-500/50 text-red-500 rounded-md hover:bg-red-500/10 transition-colors"
                >
                  <TrashIcon className="w-4 h-4" />
                  DELETE
                </button>
              </>
            )}
          </div>
        </div>

        {/* Status badges */}
        <div className="flex items-center gap-3 mb-6">
          {capability.is_system ? (
            <span className="inline-flex items-center gap-1 px-3 py-1 text-xs font-mono bg-purple-500/10 text-purple-500 border border-purple-500/30 rounded-full">
              <LockClosedIcon className="w-3 h-3" />
              System Capability
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-3 py-1 text-xs font-mono bg-green-500/10 text-green-500 border border-green-500/30 rounded-full">
              <CheckCircleIcon className="w-3 h-3" />
              Custom Capability
            </span>
          )}
          {capability.is_active ? (
            <span className="inline-flex items-center px-3 py-1 text-xs font-mono bg-green-500 text-white rounded-full">
              Active
            </span>
          ) : (
            <span className="inline-flex items-center px-3 py-1 text-xs font-mono bg-[var(--muted)] text-[var(--muted-foreground)] rounded-full">
              Inactive
            </span>
          )}
          {capability.domain && (
            <span className="inline-flex items-center gap-1 px-3 py-1 text-xs font-mono bg-[var(--muted)] rounded-full">
              <CubeIcon className="w-3 h-3" />
              {capability.domain}
            </span>
          )}
          <span className="inline-flex items-center px-3 py-1 text-xs font-mono bg-[var(--muted)] rounded-full">
            {capability.task_type}
          </span>
        </div>

        {/* Description */}
        {capability.description && (
          <div className="mb-6">
            <p className="text-sm font-mono text-[var(--foreground)] leading-relaxed">
              {capability.description}
            </p>
          </div>
        )}

        {/* Usage Statistics */}
        <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-6 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <ChartBarIcon className="w-5 h-5 text-[var(--accent)]" />
            <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)]">
              USAGE STATISTICS
            </h2>
          </div>
          <div className="grid grid-cols-4 gap-4">
            <div className="p-4 bg-[var(--muted)] rounded-lg">
              <p className="text-xs font-mono text-[var(--muted-foreground)]">TOTAL USES</p>
              <p className="text-2xl font-mono font-bold text-[var(--foreground)] mt-1">
                {capability.usage_count}
              </p>
            </div>
            <div className="p-4 bg-[var(--muted)] rounded-lg">
              <p className="text-xs font-mono text-[var(--muted-foreground)]">SUCCESSES</p>
              <p className="text-2xl font-mono font-bold text-green-500 mt-1">
                {capability.success_count}
              </p>
            </div>
            <div className="p-4 bg-[var(--muted)] rounded-lg">
              <p className="text-xs font-mono text-[var(--muted-foreground)]">FAILURES</p>
              <p className="text-2xl font-mono font-bold text-red-500 mt-1">
                {capability.failure_count}
              </p>
            </div>
            <div className="p-4 bg-[var(--muted)] rounded-lg">
              <p className="text-xs font-mono text-[var(--muted-foreground)]">SUCCESS RATE</p>
              <p className={`text-2xl font-mono font-bold mt-1 ${
                successRate === null ? 'text-[var(--muted-foreground)]' :
                successRate >= 80 ? 'text-green-500' :
                successRate >= 50 ? 'text-yellow-500' : 'text-red-500'
              }`}>
                {successRate !== null ? `${successRate.toFixed(1)}%` : '-'}
              </p>
            </div>
          </div>
          {capability.last_used_at && (
            <p className="text-xs font-mono text-[var(--muted-foreground)] mt-4">
              Last used: {new Date(capability.last_used_at).toLocaleString()}
            </p>
          )}
        </div>

        {/* Tags */}
        {capability.tags && capability.tags.length > 0 && (
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-6 mb-6">
            <div className="flex items-center gap-2 mb-4">
              <TagIcon className="w-5 h-5 text-[var(--accent)]" />
              <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)]">
                TAGS
              </h2>
            </div>
            <div className="flex flex-wrap gap-2">
              {capability.tags.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 px-3 py-1 text-xs font-mono bg-[var(--muted)] rounded"
                >
                  <TagIcon className="w-3 h-3" />
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Execution Hints */}
        {capability.execution_hints && Object.keys(capability.execution_hints).length > 0 && (
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg mb-6 overflow-hidden">
            <button
              onClick={() => setShowHintsSection(!showHintsSection)}
              className="w-full flex items-center justify-between p-6 hover:bg-[var(--muted)]/50 transition-colors"
            >
              <div className="flex items-center gap-2">
                <BoltIcon className="w-5 h-5 text-[var(--accent)]" />
                <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)]">
                  EXECUTION HINTS
                </h2>
              </div>
              {showHintsSection ? (
                <ChevronDownIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
              ) : (
                <ChevronRightIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
              )}
            </button>
            {showHintsSection && (
              <div className="px-6 pb-6">
                <div className="grid grid-cols-2 gap-4">
                  {capability.execution_hints.deterministic !== undefined && (
                    <div className="p-3 bg-[var(--muted)] rounded">
                      <p className="text-xs font-mono text-[var(--muted-foreground)]">DETERMINISTIC</p>
                      <p className="text-sm font-mono text-[var(--foreground)] mt-1">
                        {capability.execution_hints.deterministic ? 'Yes' : 'No'}
                      </p>
                    </div>
                  )}
                  {capability.execution_hints.speed && (
                    <div className="p-3 bg-[var(--muted)] rounded">
                      <p className="text-xs font-mono text-[var(--muted-foreground)]">SPEED</p>
                      <p className="text-sm font-mono text-[var(--foreground)] mt-1 capitalize">
                        {capability.execution_hints.speed}
                      </p>
                    </div>
                  )}
                  {capability.execution_hints.cost && (
                    <div className="p-3 bg-[var(--muted)] rounded">
                      <p className="text-xs font-mono text-[var(--muted-foreground)]">COST</p>
                      <p className="text-sm font-mono text-[var(--foreground)] mt-1 capitalize">
                        {capability.execution_hints.cost}
                      </p>
                    </div>
                  )}
                  {capability.execution_hints.max_tokens && (
                    <div className="p-3 bg-[var(--muted)] rounded">
                      <p className="text-xs font-mono text-[var(--muted-foreground)]">MAX TOKENS</p>
                      <p className="text-sm font-mono text-[var(--foreground)] mt-1">
                        {capability.execution_hints.max_tokens}
                      </p>
                    </div>
                  )}
                  {capability.execution_hints.temperature !== undefined && (
                    <div className="p-3 bg-[var(--muted)] rounded">
                      <p className="text-xs font-mono text-[var(--muted-foreground)]">TEMPERATURE</p>
                      <p className="text-sm font-mono text-[var(--foreground)] mt-1">
                        {capability.execution_hints.temperature}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Input Schema */}
        <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg mb-6 overflow-hidden">
          <button
            onClick={() => setShowInputsSection(!showInputsSection)}
            className="w-full flex items-center justify-between p-6 hover:bg-[var(--muted)]/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <DocumentTextIcon className="w-5 h-5 text-[var(--accent)]" />
              <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)]">
                INPUT SCHEMA
              </h2>
            </div>
            {showInputsSection ? (
              <ChevronDownIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
            ) : (
              <ChevronRightIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
            )}
          </button>
          {showInputsSection && (
            <div className="px-6 pb-6">
              <div className="relative">
                <button
                  onClick={() => copyToClipboard(formatJson(capability.inputs_schema), 'inputs')}
                  className="absolute top-2 right-2 p-1.5 bg-[var(--card)] border border-[var(--border)] rounded hover:bg-[var(--muted)] transition-colors z-10"
                  title="Copy"
                >
                  <ClipboardDocumentIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                </button>
                {copiedField === 'inputs' && (
                  <span className="absolute top-2 right-12 text-xs font-mono text-green-500">Copied!</span>
                )}
                <pre className="p-4 bg-[var(--muted)] rounded-lg overflow-auto max-h-64 text-xs font-mono text-[var(--foreground)]">
                  {formatJson(capability.inputs_schema)}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* Output Schema */}
        <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg mb-6 overflow-hidden">
          <button
            onClick={() => setShowOutputsSection(!showOutputsSection)}
            className="w-full flex items-center justify-between p-6 hover:bg-[var(--muted)]/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <DocumentTextIcon className="w-5 h-5 text-[var(--accent)]" />
              <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)]">
                OUTPUT SCHEMA
              </h2>
            </div>
            {showOutputsSection ? (
              <ChevronDownIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
            ) : (
              <ChevronRightIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
            )}
          </button>
          {showOutputsSection && (
            <div className="px-6 pb-6">
              <div className="relative">
                <button
                  onClick={() => copyToClipboard(formatJson(capability.outputs_schema), 'outputs')}
                  className="absolute top-2 right-2 p-1.5 bg-[var(--card)] border border-[var(--border)] rounded hover:bg-[var(--muted)] transition-colors z-10"
                  title="Copy"
                >
                  <ClipboardDocumentIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                </button>
                {copiedField === 'outputs' && (
                  <span className="absolute top-2 right-12 text-xs font-mono text-green-500">Copied!</span>
                )}
                <pre className="p-4 bg-[var(--muted)] rounded-lg overflow-auto max-h-64 text-xs font-mono text-[var(--foreground)]">
                  {formatJson(capability.outputs_schema)}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* YAML Specification */}
        {capability.spec_yaml && (
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg mb-6 overflow-hidden">
            <button
              onClick={() => setShowYamlSection(!showYamlSection)}
              className="w-full flex items-center justify-between p-6 hover:bg-[var(--muted)]/50 transition-colors"
            >
              <div className="flex items-center gap-2">
                <CodeBracketIcon className="w-5 h-5 text-[var(--accent)]" />
                <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)]">
                  YAML SPECIFICATION
                </h2>
              </div>
              {showYamlSection ? (
                <ChevronDownIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
              ) : (
                <ChevronRightIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
              )}
            </button>
            {showYamlSection && (
              <div className="px-6 pb-6">
                <div className="relative">
                  <button
                    onClick={() => copyToClipboard(capability.spec_yaml || '', 'yaml')}
                    className="absolute top-2 right-2 p-1.5 bg-[var(--card)] border border-[var(--border)] rounded hover:bg-[var(--muted)] transition-colors z-10"
                    title="Copy YAML"
                  >
                    <ClipboardDocumentIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                  </button>
                  {copiedField === 'yaml' && (
                    <span className="absolute top-2 right-12 text-xs font-mono text-green-500">Copied!</span>
                  )}
                  <pre className="p-4 bg-[var(--muted)] rounded-lg overflow-auto max-h-96 text-xs font-mono text-[var(--foreground)]">
                    {capability.spec_yaml}
                  </pre>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Metadata */}
        <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-6 mb-6">
          <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)] mb-4">
            METADATA
          </h2>
          <div className="grid grid-cols-2 gap-4 text-sm font-mono">
            <div>
              <p className="text-xs text-[var(--muted-foreground)]">ID</p>
              <div className="flex items-center gap-2 mt-1">
                <code className="text-xs bg-[var(--muted)] px-2 py-1 rounded truncate max-w-[200px]">
                  {capability.id}
                </code>
                <button
                  onClick={() => copyToClipboard(capability.id, 'id')}
                  className="p-1 hover:bg-[var(--muted)] rounded transition-colors"
                >
                  <ClipboardDocumentIcon className="w-3 h-3 text-[var(--muted-foreground)]" />
                </button>
                {copiedField === 'id' && (
                  <span className="text-xs text-green-500">Copied!</span>
                )}
              </div>
            </div>
            <div>
              <p className="text-xs text-[var(--muted-foreground)]">VERSION</p>
              <p className="text-[var(--foreground)] mt-1">
                {capability.version} {capability.is_latest && '(latest)'}
              </p>
            </div>
            {capability.created_at && (
              <div>
                <p className="text-xs text-[var(--muted-foreground)]">CREATED</p>
                <p className="text-[var(--foreground)] mt-1">
                  {new Date(capability.created_at).toLocaleString()}
                </p>
              </div>
            )}
            {capability.updated_at && (
              <div>
                <p className="text-xs text-[var(--muted-foreground)]">UPDATED</p>
                <p className="text-[var(--foreground)] mt-1">
                  {new Date(capability.updated_at).toLocaleString()}
                </p>
              </div>
            )}
            {capability.organization_id && (
              <div>
                <p className="text-xs text-[var(--muted-foreground)]">ORGANIZATION</p>
                <code className="text-xs bg-[var(--muted)] px-2 py-1 rounded mt-1 inline-block truncate max-w-[200px]">
                  {capability.organization_id}
                </code>
              </div>
            )}
            {capability.created_by && (
              <div>
                <p className="text-xs text-[var(--muted-foreground)]">CREATED BY</p>
                <code className="text-xs bg-[var(--muted)] px-2 py-1 rounded mt-1 inline-block truncate max-w-[200px]">
                  {capability.created_by}
                </code>
              </div>
            )}
          </div>
        </div>

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

                    <div className="p-6 space-y-4">
                      <div>
                        <p className="text-xs font-mono text-[var(--muted-foreground)]">CAPABILITY</p>
                        <p className="text-sm font-mono font-medium text-[var(--foreground)] mt-1">
                          {capability.name}
                        </p>
                        {capability.description && (
                          <p className="text-sm font-mono text-[var(--muted-foreground)] mt-1">
                            {capability.description}
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

                    <div className="p-6 border-t border-[var(--border)] flex justify-end gap-3">
                      <button
                        onClick={() => setShowDeleteDialog(false)}
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
      </div>
    </div>
  );
}
