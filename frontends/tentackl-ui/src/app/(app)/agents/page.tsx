'use client';

import { useState } from 'react';
import {
  PlusIcon,
  ArrowPathIcon,
  MagnifyingGlassIcon,
  PencilSquareIcon,
  TrashIcon,
  LockClosedIcon,
  CheckCircleIcon,
  EyeIcon,
  ClipboardDocumentIcon,
  TagIcon,
  CubeIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';
import { Dialog, DialogPanel, DialogTitle, Transition, TransitionChild } from '@headlessui/react';
import { Fragment } from 'react';
import {
  useAgents,
  useUpdateAgent,
  useDeleteAgent,
  useGenerateAgent,
} from '../../../hooks/useAgents';
import type { AgentSpec, UpdateAgentRequest } from '../../../types/agent';

export default function AgentsPage() {
  // Only show user-owned agents (not system agents)
  const { agents, isLoading, error, refetch } = useAgents(undefined, undefined, false, false);
  const { update, isLoading: isUpdating, error: updateError } = useUpdateAgent();
  const { deleteAgent, isLoading: isDeleting, error: deleteError } = useDeleteAgent();
  const { generate, isLoading: isGenerating, progress: generateProgress, error: generateError } = useGenerateAgent();

  // Dialog states
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showDetailsDialog, setShowDetailsDialog] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<AgentSpec | null>(null);

  // Create flow state
  const [agentDescription, setAgentDescription] = useState('');

  // Form state for edit
  const [editDescription, setEditDescription] = useState('');
  const [editCategory, setEditCategory] = useState('');
  const [editTags, setEditTags] = useState('');
  const [editYaml, setEditYaml] = useState('');
  const [editFormError, setEditFormError] = useState<string | null>(null);

  // Search filter
  const [searchQuery, setSearchQuery] = useState('');

  // Filter agents by search query
  const filteredAgents = agents.filter((agent) => {
    const query = searchQuery.toLowerCase();
    return (
      agent.name.toLowerCase().includes(query) ||
      agent.description?.toLowerCase().includes(query) ||
      agent.category?.toLowerCase().includes(query) ||
      agent.tags?.some((tag) => tag.toLowerCase().includes(query))
    );
  });

  // Stats (only user-owned agents, no system agents)
  const stats = {
    total: agents.length,
    active: agents.filter((a) => a.is_active).length,
  };

  // Generate and register agent from description (single step with SSE progress)
  const handleGenerate = async () => {
    if (!agentDescription.trim()) return;

    try {
      await generate(agentDescription);
      setShowCreateDialog(false);
      setAgentDescription('');
      refetch();
    } catch {
      // Error handled by hook
    }
  };

  const openCreateDialog = () => {
    setAgentDescription('');
    setShowCreateDialog(true);
  };

  const openEditDialog = (agent: AgentSpec) => {
    setSelectedAgent(agent);
    setEditDescription(agent.description || '');
    setEditCategory(agent.category || 'custom');
    setEditTags(agent.tags?.join(', ') || '');
    setEditYaml(agent.spec_yaml || '');
    setEditFormError(null);
    setShowEditDialog(true);
  };

  const handleUpdate = async () => {
    if (!selectedAgent) return;

    if (!editYaml.trim()) {
      setEditFormError('YAML content is required');
      return;
    }

    try {
      await update(selectedAgent.id, {
        yaml_content: editYaml,
        description: editDescription || undefined,
        category: editCategory || 'custom',
        tags: editTags ? editTags.split(',').map((t) => t.trim()).filter(Boolean) : undefined,
      });
      setShowEditDialog(false);
      setSelectedAgent(null);
      refetch();
    } catch {
      // Error handled by hook
    }
  };

  const openDeleteDialog = (agent: AgentSpec) => {
    setSelectedAgent(agent);
    setShowDeleteDialog(true);
  };

  const handleDelete = async () => {
    if (!selectedAgent) return;

    try {
      await deleteAgent(selectedAgent.id);
      setShowDeleteDialog(false);
      setSelectedAgent(null);
      refetch();
    } catch {
      // Error handled by hook
    }
  };

  const openDetailsDialog = (agent: AgentSpec) => {
    setSelectedAgent(agent);
    setShowDetailsDialog(true);
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="min-h-screen bg-[var(--background)]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-mono font-bold tracking-wider text-[var(--foreground)]">
              AGENTS
            </h1>
            <p className="text-sm font-mono text-[var(--muted-foreground)] mt-1">
              Manage AI agent specifications and configurations
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative">
              <MagnifyingGlassIcon className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" />
              <input
                type="text"
                placeholder="Search agents..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-4 py-2 w-48 text-sm font-mono bg-[var(--card)] border border-[var(--border)] rounded-md text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              />
            </div>
            <button
              onClick={() => refetch()}
              className="flex items-center gap-2 px-3 py-2 text-xs font-mono tracking-wider border border-[var(--border)] rounded-md text-[var(--muted-foreground)] hover:bg-[var(--muted)] transition-colors"
            >
              <ArrowPathIcon className="w-4 h-4" />
              REFRESH
            </button>
            <button
              onClick={openCreateDialog}
              className="flex items-center gap-2 px-3 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity"
            >
              <PlusIcon className="w-4 h-4" />
              CREATE
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 mb-8">
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
            <p className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">YOUR AGENTS</p>
            <p className="text-2xl font-mono font-bold text-[var(--foreground)] mt-1">{stats.total}</p>
          </div>
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
            <p className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">ACTIVE</p>
            <p className="text-2xl font-mono font-bold text-green-500 mt-1">{stats.active}</p>
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
              <p className="text-sm font-mono text-[var(--muted-foreground)]">Loading agents...</p>
            </div>
          </div>
        )}

        {/* Agents Table */}
        {!isLoading && filteredAgents.length > 0 && (
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">NAME</th>
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">DESCRIPTION</th>
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">VERSION</th>
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">CATEGORY</th>
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">TYPE</th>
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">STATUS</th>
                  <th className="px-4 py-3 text-left text-xs font-mono font-medium text-[var(--muted-foreground)] tracking-wider">ACTIONS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {filteredAgents.map((agent) => (
                  <tr key={agent.id} className="hover:bg-[var(--muted)]/50 transition-colors">
                    <td className="px-4 py-3">
                      <span className="text-sm font-mono font-medium text-[var(--foreground)]">{agent.name}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm font-mono text-[var(--muted-foreground)] line-clamp-1 max-w-[200px]">
                        {agent.description || '-'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center px-2 py-0.5 text-xs font-mono border border-[var(--border)] rounded">
                        v{agent.version}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono bg-[var(--muted)] rounded">
                        <CubeIcon className="w-3 h-3" />
                        {agent.category || 'custom'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {agent.is_system ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono bg-purple-500/10 text-purple-500 border border-purple-500/30 rounded">
                          <LockClosedIcon className="w-3 h-3" />
                          System
                        </span>
                      ) : agent.can_edit ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono bg-green-500/10 text-green-500 border border-green-500/30 rounded">
                          <CheckCircleIcon className="w-3 h-3" />
                          Owned
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 text-xs font-mono border border-[var(--border)] rounded">
                          Shared
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {agent.is_active ? (
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
                        <button
                          onClick={() => openDetailsDialog(agent)}
                          className="p-1.5 rounded border border-[var(--border)] hover:bg-[var(--muted)] transition-colors"
                          title="View details"
                        >
                          <EyeIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                        </button>
                        {agent.can_edit && !agent.is_system && (
                          <>
                            <button
                              onClick={() => openEditDialog(agent)}
                              className="p-1.5 rounded border border-[var(--border)] hover:bg-[var(--muted)] transition-colors"
                              title="Edit agent"
                            >
                              <PencilSquareIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                            </button>
                            <button
                              onClick={() => openDeleteDialog(agent)}
                              className="p-1.5 rounded hover:bg-red-500/10 transition-colors"
                              title="Delete agent"
                            >
                              <TrashIcon className="w-4 h-4 text-[var(--muted-foreground)] hover:text-red-500" />
                            </button>
                          </>
                        )}
                        {agent.is_system && (
                          <span className="text-xs font-mono text-[var(--muted-foreground)] flex items-center gap-1">
                            <LockClosedIcon className="w-3 h-3" />
                            Read-only
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && filteredAgents.length === 0 && (
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-12 text-center">
            <p className="text-lg font-mono text-[var(--muted-foreground)] mb-2">No agents found</p>
            <p className="text-sm font-mono text-[var(--muted-foreground)] mb-4">
              {searchQuery
                ? 'Try adjusting your search query'
                : 'Create your first agent to start building AI workflows'}
            </p>
            {!searchQuery && (
              <button
                onClick={openCreateDialog}
                className="inline-flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity"
              >
                <PlusIcon className="w-4 h-4" />
                CREATE
              </button>
            )}
          </div>
        )}

        {/* Create Dialog - Single-step with SSE progress */}
        <Transition appear show={showCreateDialog} as={Fragment}>
          <Dialog as="div" className="relative z-50" onClose={() => !isGenerating && setShowCreateDialog(false)}>
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
                  <DialogPanel className="w-full max-w-xl bg-[var(--card)] border border-[var(--border)] rounded-lg shadow-xl">
                    {/* Header */}
                    <div className="p-6 border-b border-[var(--border)]">
                      <DialogTitle className="flex items-center gap-2 text-lg font-mono font-bold text-[var(--foreground)]">
                        <SparklesIcon className="w-5 h-5 text-[var(--accent)]" />
                        CREATE AGENT
                      </DialogTitle>
                      <p className="text-sm font-mono text-[var(--muted-foreground)] mt-1">
                        Describe what you want your agent to do.
                      </p>
                    </div>

                    <div className="p-6">
                      <label className="block text-xs font-mono text-[var(--muted-foreground)] mb-2">
                        WHAT SHOULD THIS AGENT DO?
                      </label>
                      <textarea
                        value={agentDescription}
                        onChange={(e) => setAgentDescription(e.target.value)}
                        placeholder="Example: An agent that monitors my GitHub PRs and sends me a daily summary of new comments..."
                        rows={4}
                        autoFocus
                        disabled={isGenerating}
                        className="w-full px-4 py-3 text-sm font-mono bg-[var(--background)] border border-[var(--border)] rounded-lg text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-none disabled:opacity-50"
                      />
                      <p className="text-xs font-mono text-[var(--muted-foreground)] mt-2">
                        Be specific about inputs, outputs, and any integrations needed.
                      </p>

                      {/* Progress indicator */}
                      {isGenerating && generateProgress && (
                        <div className="mt-4 p-3 bg-[var(--muted)] border border-[var(--border)] rounded-lg">
                          <div className="flex items-center gap-3">
                            <ArrowPathIcon className="w-4 h-4 text-[var(--accent)] animate-spin flex-shrink-0" />
                            <p className="text-sm font-mono text-[var(--foreground)]">
                              {generateProgress.message}
                            </p>
                          </div>
                        </div>
                      )}

                      {generateError && (
                        <div className="mt-4 p-3 bg-red-500/10 border border-red-500/50 rounded-lg">
                          <p className="text-sm font-mono text-red-500">
                            {generateError.message}
                          </p>
                        </div>
                      )}
                    </div>

                    <div className="p-6 border-t border-[var(--border)] flex justify-end gap-3">
                      <button
                        onClick={() => setShowCreateDialog(false)}
                        disabled={isGenerating}
                        className="px-4 py-2 text-xs font-mono tracking-wider border border-[var(--border)] rounded-md text-[var(--muted-foreground)] hover:bg-[var(--muted)] transition-colors disabled:opacity-50"
                      >
                        CANCEL
                      </button>
                      <button
                        onClick={handleGenerate}
                        disabled={!agentDescription.trim() || isGenerating}
                        className="flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isGenerating ? (
                          <>
                            <ArrowPathIcon className="w-4 h-4 animate-spin" />
                            CREATING...
                          </>
                        ) : (
                          <>
                            <SparklesIcon className="w-4 h-4" />
                            CREATE AGENT
                          </>
                        )}
                      </button>
                    </div>
                  </DialogPanel>
                </TransitionChild>
              </div>
            </div>
          </Dialog>
        </Transition>

        {/* Edit Dialog */}
        <Transition appear show={showEditDialog} as={Fragment}>
          <Dialog as="div" className="relative z-50" onClose={() => setShowEditDialog(false)}>
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
                        EDIT AGENT: {selectedAgent?.name}
                      </DialogTitle>
                      <p className="text-sm font-mono text-[var(--muted-foreground)] mt-1">
                        Modify the agent specification and metadata.
                      </p>
                    </div>

                    <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
                      {editFormError && (
                        <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg">
                          <p className="text-sm font-mono text-red-500">{editFormError}</p>
                        </div>
                      )}

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-xs font-mono text-[var(--muted-foreground)] mb-1">
                            CATEGORY
                          </label>
                          <input
                            type="text"
                            value={editCategory}
                            onChange={(e) => setEditCategory(e.target.value)}
                            placeholder="custom"
                            className="w-full px-3 py-2 text-sm font-mono bg-[var(--background)] border border-[var(--border)] rounded-md text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-mono text-[var(--muted-foreground)] mb-1">
                            TAGS (COMMA-SEPARATED)
                          </label>
                          <input
                            type="text"
                            value={editTags}
                            onChange={(e) => setEditTags(e.target.value)}
                            placeholder="analyzer, data, custom"
                            className="w-full px-3 py-2 text-sm font-mono bg-[var(--background)] border border-[var(--border)] rounded-md text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block text-xs font-mono text-[var(--muted-foreground)] mb-1">
                          DESCRIPTION
                        </label>
                        <input
                          type="text"
                          value={editDescription}
                          onChange={(e) => setEditDescription(e.target.value)}
                          placeholder="A brief description..."
                          className="w-full px-3 py-2 text-sm font-mono bg-[var(--background)] border border-[var(--border)] rounded-md text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-mono text-[var(--muted-foreground)] mb-1">
                          YAML SPECIFICATION
                        </label>
                        <textarea
                          value={editYaml}
                          onChange={(e) => {
                            setEditYaml(e.target.value);
                            if (editFormError) setEditFormError(null);
                          }}
                          rows={16}
                          className="w-full px-3 py-2 text-sm font-mono bg-[var(--background)] border border-[var(--border)] rounded-md text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-none"
                        />
                      </div>

                      {updateError && (
                        <div className="p-3 bg-red-500/10 border border-red-500/50 rounded-lg">
                          <p className="text-sm font-mono text-red-500">{updateError.message}</p>
                        </div>
                      )}
                    </div>

                    <div className="p-6 border-t border-[var(--border)] flex justify-end gap-3">
                      <button
                        onClick={() => setShowEditDialog(false)}
                        className="px-4 py-2 text-xs font-mono tracking-wider border border-[var(--border)] rounded-md text-[var(--muted-foreground)] hover:bg-[var(--muted)] transition-colors"
                      >
                        CANCEL
                      </button>
                      <button
                        onClick={handleUpdate}
                        disabled={!editYaml.trim() || isUpdating}
                        className="flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isUpdating && <ArrowPathIcon className="w-4 h-4 animate-spin" />}
                        SAVE CHANGES
                      </button>
                    </div>
                  </DialogPanel>
                </TransitionChild>
              </div>
            </div>
          </Dialog>
        </Transition>

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
                        DELETE AGENT
                      </DialogTitle>
                      <p className="text-sm font-mono text-[var(--muted-foreground)] mt-1">
                        Are you sure you want to delete this agent? This action cannot be undone.
                      </p>
                    </div>

                    {selectedAgent && (
                      <div className="p-6 space-y-4">
                        <div>
                          <p className="text-xs font-mono text-[var(--muted-foreground)]">AGENT</p>
                          <p className="text-sm font-mono font-medium text-[var(--foreground)] mt-1">{selectedAgent.name}</p>
                          {selectedAgent.description && (
                            <p className="text-sm font-mono text-[var(--muted-foreground)] mt-1">{selectedAgent.description}</p>
                          )}
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
                          setSelectedAgent(null);
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
                        AGENT DETAILS: {selectedAgent?.name}
                      </DialogTitle>
                      <p className="text-sm font-mono text-[var(--muted-foreground)] mt-1">
                        View agent specification and metadata
                      </p>
                    </div>

                    {selectedAgent && (
                      <div className="p-6 space-y-6 max-h-[60vh] overflow-y-auto">
                        {/* Metadata */}
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">ID</p>
                            <div className="mt-1 flex items-center gap-2">
                              <code className="text-xs font-mono bg-[var(--muted)] px-2 py-1 rounded">
                                {selectedAgent.id}
                              </code>
                              <button
                                onClick={() => copyToClipboard(selectedAgent.id)}
                                className="p-1 hover:bg-[var(--muted)] rounded transition-colors"
                              >
                                <ClipboardDocumentIcon className="w-3 h-3 text-[var(--muted-foreground)]" />
                              </button>
                            </div>
                          </div>
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">VERSION</p>
                            <p className="mt-1 text-sm font-mono text-[var(--foreground)]">{selectedAgent.version}</p>
                          </div>
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">CATEGORY</p>
                            <p className="mt-1 text-sm font-mono text-[var(--foreground)]">{selectedAgent.category || 'custom'}</p>
                          </div>
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">STATUS</p>
                            <div className="mt-1 flex items-center gap-2">
                              {selectedAgent.is_active ? (
                                <span className="inline-flex items-center px-2 py-0.5 text-xs font-mono bg-green-500 text-white rounded">
                                  Active
                                </span>
                              ) : (
                                <span className="inline-flex items-center px-2 py-0.5 text-xs font-mono bg-[var(--muted)] text-[var(--muted-foreground)] rounded">
                                  Inactive
                                </span>
                              )}
                              {selectedAgent.is_system && (
                                <span className="inline-flex items-center px-2 py-0.5 text-xs font-mono bg-purple-500/10 text-purple-500 border border-purple-500/30 rounded">
                                  System
                                </span>
                              )}
                              {selectedAgent.can_edit && (
                                <span className="inline-flex items-center px-2 py-0.5 text-xs font-mono bg-green-500/10 text-green-500 border border-green-500/30 rounded">
                                  Owned
                                </span>
                              )}
                            </div>
                          </div>
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">CREATED</p>
                            <p className="mt-1 text-sm font-mono text-[var(--foreground)]">
                              {new Date(selectedAgent.created_at).toLocaleString()}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">USAGE COUNT</p>
                            <p className="mt-1 text-sm font-mono text-[var(--foreground)]">{selectedAgent.usage_count || 0}</p>
                          </div>
                        </div>

                        {/* Description */}
                        {selectedAgent.description && (
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">DESCRIPTION</p>
                            <p className="mt-1 text-sm font-mono text-[var(--foreground)]">{selectedAgent.description}</p>
                          </div>
                        )}

                        {/* Tags */}
                        {selectedAgent.tags && selectedAgent.tags.length > 0 && (
                          <div>
                            <p className="text-xs font-mono text-[var(--muted-foreground)]">TAGS</p>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {selectedAgent.tags.map((tag) => (
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

                        {/* YAML Spec */}
                        {selectedAgent.spec_yaml && (
                          <div>
                            <div className="flex items-center justify-between mb-2">
                              <p className="text-xs font-mono text-[var(--muted-foreground)]">YAML SPECIFICATION</p>
                              <button
                                onClick={() => copyToClipboard(selectedAgent.spec_yaml || '')}
                                className="flex items-center gap-1 text-xs font-mono text-[var(--accent)] hover:underline"
                              >
                                <ClipboardDocumentIcon className="w-3 h-3" />
                                Copy
                              </button>
                            </div>
                            <pre className="p-4 bg-[var(--muted)] rounded-lg overflow-auto max-h-80 text-xs font-mono text-[var(--foreground)]">
                              {selectedAgent.spec_yaml}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}

                    <div className="p-6 border-t border-[var(--border)] flex justify-end gap-3">
                      <button
                        onClick={() => setShowDetailsDialog(false)}
                        className="px-4 py-2 text-xs font-mono tracking-wider border border-[var(--border)] rounded-md text-[var(--muted-foreground)] hover:bg-[var(--muted)] transition-colors"
                      >
                        CLOSE
                      </button>
                      {selectedAgent?.can_edit && !selectedAgent?.is_system && (
                        <button
                          onClick={() => {
                            setShowDetailsDialog(false);
                            openEditDialog(selectedAgent);
                          }}
                          className="flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity"
                        >
                          <PencilSquareIcon className="w-4 h-4" />
                          EDIT AGENT
                        </button>
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
