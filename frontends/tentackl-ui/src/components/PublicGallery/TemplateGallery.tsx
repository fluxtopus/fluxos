'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ReactFlowProvider } from '@xyflow/react';
import { LockClosedIcon } from '@heroicons/react/24/outline';
import { listPublicTemplates, copyTemplate, getTemplateDetails } from '../../services/versions';
import type { PublicTemplateResponse, TemplateDetailsResponse } from '../../types/version';
import { PlaygroundWorkflowGraph } from '../Playground/PlaygroundWorkflowGraph';
import { useAuthGuard } from '../../hooks/useAuthGuard';

interface TemplateGalleryProps {
  onCopySuccess?: (template: PublicTemplateResponse) => void;
}

export const TemplateGallery: React.FC<TemplateGalleryProps> = ({ onCopySuccess }) => {
  const router = useRouter();
  const searchParams = useSearchParams();
  const templateIdFromUrl = searchParams.get('template');
  const { requireAuth, isAuthenticated } = useAuthGuard();

  const [templates, setTemplates] = useState<PublicTemplateResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Selected template state
  const [selectedTemplate, setSelectedTemplate] = useState<PublicTemplateResponse | null>(null);
  const [templateDetails, setTemplateDetails] = useState<TemplateDetailsResponse | null>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [copying, setCopying] = useState(false);
  const [newName, setNewName] = useState('');

  const loadTemplates = useCallback(async (searchQuery?: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await listPublicTemplates(searchQuery, undefined, 50, 0);
      setTemplates(response.specs);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load templates');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  useEffect(() => {
    const debounce = setTimeout(() => {
      loadTemplates(search || undefined);
    }, 300);
    return () => clearTimeout(debounce);
  }, [search, loadTemplates]);

  // Load template from URL on mount or when URL changes
  useEffect(() => {
    if (templateIdFromUrl && templates.length > 0) {
      const template = templates.find(t => t.id === templateIdFromUrl);
      if (template && template.id !== selectedTemplate?.id) {
        loadTemplateDetails(template);
      }
    }
  }, [templateIdFromUrl, templates]);

  const loadTemplateDetails = async (template: PublicTemplateResponse) => {
    setSelectedTemplate(template);
    setLoadingDetails(true);
    setNewName('');
    try {
      const details = await getTemplateDetails(template.id);
      setTemplateDetails(details);
    } catch (err) {
      console.error('Failed to load template details:', err);
      setTemplateDetails(null);
    } finally {
      setLoadingDetails(false);
    }
  };

  const handleSelectTemplate = (template: PublicTemplateResponse) => {
    // Update URL with template ID
    router.push(`/specs/public?template=${template.id}`, { scroll: false });
    loadTemplateDetails(template);
  };

  const handleDeselectTemplate = () => {
    // Remove template from URL
    router.push('/specs/public', { scroll: false });
    setSelectedTemplate(null);
    setTemplateDetails(null);
    setNewName('');
  };

  const performCopy = async () => {
    if (!selectedTemplate) return;
    setCopying(true);
    try {
      const copied = await copyTemplate(selectedTemplate.id, newName || undefined);
      if (onCopySuccess) {
        onCopySuccess(copied);
      }
    } finally {
      setCopying(false);
    }
  };

  const handleCopyTemplate = () => {
    if (!selectedTemplate) return;
    requireAuth(performCopy, 'copy', 'Copy this template to your account');
  };

  const handleQuickCopy = async (templateId: string) => {
    requireAuth(async () => {
      const copied = await copyTemplate(templateId);
      if (onCopySuccess) {
        onCopySuccess(copied);
      }
    }, 'copy', 'Copy this template to your account');
  };

  return (
    <div className="flex gap-6 h-[calc(100vh-120px)]">
      {/* Left Column - Template List */}
      <div className="w-[380px] flex-shrink-0 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <div className="w-2 h-2 rounded-full bg-[oklch(0.75_0.2_85)]" />
              <h2 className="font-mono text-sm tracking-wider text-[oklch(0.75_0.2_85)] uppercase">
                Template Gallery
              </h2>
            </div>
            <p className="text-[11px] text-[oklch(0.58_0.01_260)]">
              Discover and copy workflow templates
            </p>
          </div>
          <span className="font-mono text-[10px] text-[oklch(0.58_0.01_260)]">
            {total} AVAILABLE
          </span>
        </div>

        {/* Search */}
        <div className="relative mb-4">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search templates..."
            className="w-full px-4 py-2.5 pl-10 font-mono text-sm text-[oklch(0.95_0.01_90)] bg-[oklch(0.08_0.02_260)] border border-[oklch(0.22_0.03_260)] rounded-lg focus:outline-none focus:border-[oklch(0.65_0.25_180)] focus:shadow-[0_0_15px_oklch(0.65_0.25_180/0.2)] placeholder-[oklch(0.38_0.01_260)] transition-all duration-300"
          />
          <svg
            className="absolute left-3 top-3 h-4 w-4 text-[oklch(0.5_0.01_260)]"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>

        {/* Error */}
        {error && (
          <div className="p-3 rounded-lg border border-[oklch(0.577_0.245_27/0.5)] bg-[oklch(0.577_0.245_27/0.1)] mb-4">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-[oklch(0.577_0.245_27)]" />
              <span className="font-mono text-xs text-[oklch(0.577_0.245_27)]">{error}</span>
            </div>
          </div>
        )}

        {/* Template List */}
        <div className="flex-1 overflow-y-auto pr-2 space-y-2">
          {loading ? (
            <>
              {[1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="h-20 rounded-lg border border-[oklch(0.22_0.03_260)] bg-[oklch(0.12_0.02_260/0.5)] animate-pulse"
                />
              ))}
            </>
          ) : templates.length === 0 ? (
            <div className="text-center py-12">
              <svg className="w-12 h-12 mx-auto text-[oklch(0.2_0.02_260)] mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={0.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              <p className="font-mono text-xs text-[oklch(0.4_0.01_260)]">
                {search ? 'No matches' : 'No templates'}
              </p>
            </div>
          ) : (
            templates.map((template) => (
              <button
                key={template.id}
                onClick={() => handleSelectTemplate(template)}
                className={`w-full text-left p-3 rounded-lg border transition-all duration-200 ${
                  selectedTemplate?.id === template.id
                    ? 'border-[oklch(0.65_0.25_180)] bg-[oklch(0.65_0.25_180/0.1)] shadow-[0_0_15px_oklch(0.65_0.25_180/0.15)]'
                    : 'border-[oklch(0.22_0.03_260)] bg-[oklch(0.12_0.02_260/0.5)] hover:border-[oklch(0.65_0.25_180/0.5)] hover:bg-[oklch(0.65_0.25_180/0.05)]'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className={`font-mono text-xs tracking-wider uppercase truncate ${
                    selectedTemplate?.id === template.id
                      ? 'text-[oklch(0.65_0.25_180)]'
                      : 'text-[oklch(0.95_0.01_90)]'
                  }`}>
                    {template.name}
                  </span>
                  <span className="shrink-0 px-1.5 py-0.5 font-mono text-[9px] rounded border border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260)] text-[oklch(0.58_0.01_260)]">
                    v{template.version}
                  </span>
                </div>
                {template.description && (
                  <p className="text-[10px] text-[oklch(0.5_0.01_260)] line-clamp-1 mb-1">
                    {template.description}
                  </p>
                )}
                <div className="flex items-center gap-2 text-[oklch(0.4_0.01_260)]">
                  <span className="font-mono text-[9px]">{template.total_runs} runs</span>
                  {template.created_by && (
                    <>
                      <span>•</span>
                      <span className="font-mono text-[9px]">by {template.created_by}</span>
                    </>
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Right Column - Template Preview */}
      <div className="flex-1 rounded-xl border border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260)] overflow-hidden flex flex-col">
        {selectedTemplate ? (
          <>
            {/* Preview Header */}
            <div className="px-5 py-4 border-b border-[oklch(0.22_0.03_260)] flex items-center gap-3">
              <div className="p-2 rounded border border-[oklch(0.65_0.25_180/0.5)] bg-[oklch(0.65_0.25_180/0.1)] text-[oklch(0.65_0.25_180)]">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-mono text-sm tracking-wider text-[oklch(0.65_0.25_180)] uppercase truncate">
                  {selectedTemplate.name}
                </h3>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="font-mono text-[10px] text-[oklch(0.5_0.01_260)]">
                    v{selectedTemplate.version}
                  </span>
                  {selectedTemplate.created_by && (
                    <>
                      <span className="text-[oklch(0.3_0.01_260)]">•</span>
                      <span className="font-mono text-[10px] text-[oklch(0.5_0.01_260)]">
                        by {selectedTemplate.created_by}
                      </span>
                    </>
                  )}
                </div>
              </div>
              <button
                onClick={handleDeselectTemplate}
                className="p-1.5 rounded hover:bg-[oklch(0.2_0.02_260)] transition-colors"
              >
                <svg className="w-4 h-4 text-[oklch(0.5_0.01_260)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Preview Content */}
            <div className="flex-1 overflow-hidden flex flex-col">
              {loadingDetails ? (
                <div className="flex-1 flex items-center justify-center">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 rounded-full bg-[oklch(0.65_0.25_180)] animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-2 h-2 rounded-full bg-[oklch(0.65_0.25_180)] animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-2 h-2 rounded-full bg-[oklch(0.65_0.25_180)] animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              ) : (
                <>
                  {/* Workflow Visualization - Takes most space */}
                  <div className="flex-1 min-h-0">
                    {templateDetails?.spec_yaml ? (
                      <ReactFlowProvider>
                        <PlaygroundWorkflowGraph
                          yaml={templateDetails.spec_yaml}
                          executionNodes={[]}
                        />
                      </ReactFlowProvider>
                    ) : (
                      <div className="h-full flex items-center justify-center text-[oklch(0.4_0.01_260)]">
                        <span className="font-mono text-sm">No workflow data</span>
                      </div>
                    )}
                  </div>

                  {/* Info Footer */}
                  <div className="border-t border-[oklch(0.22_0.03_260)] p-4 space-y-4">
                    {/* Description */}
                    {selectedTemplate.description && (
                      <p className="font-mono text-xs text-[oklch(0.7_0.01_260)] leading-relaxed">
                        {selectedTemplate.description}
                      </p>
                    )}

                    {/* Stats Row */}
                    <div className="flex items-center gap-6">
                      <div>
                        <span className="font-mono text-lg text-[oklch(0.65_0.25_180)] font-bold">
                          {selectedTemplate.total_runs}
                        </span>
                        <span className="font-mono text-[10px] text-[oklch(0.5_0.01_260)] uppercase ml-2">
                          runs
                        </span>
                      </div>
                      <div>
                        <span className="font-mono text-lg text-[oklch(0.78_0.22_150)] font-bold">
                          {selectedTemplate.total_runs > 0
                            ? Math.round((selectedTemplate.successful_runs / selectedTemplate.total_runs) * 100)
                            : 0}%
                        </span>
                        <span className="font-mono text-[10px] text-[oklch(0.5_0.01_260)] uppercase ml-2">
                          success
                        </span>
                      </div>
                    </div>

                    {/* Copy Section */}
                    <div className="flex items-center gap-3">
                      <input
                        type="text"
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        placeholder={`${selectedTemplate.name.toLowerCase()} (copy)`}
                        className="flex-1 px-3 py-2 font-mono text-xs text-[oklch(0.95_0.01_90)] bg-[oklch(0.06_0.01_260)] border border-[oklch(0.22_0.03_260)] rounded-lg focus:outline-none focus:border-[oklch(0.65_0.25_180)] placeholder-[oklch(0.38_0.01_260)] transition-all"
                      />
                      <button
                        onClick={handleCopyTemplate}
                        disabled={copying}
                        className="flex items-center gap-2 px-4 py-2 font-mono text-xs tracking-wider uppercase rounded-lg border bg-[oklch(0.65_0.25_180/0.2)] border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180/0.3)] hover:shadow-[0_0_20px_oklch(0.65_0.25_180/0.3)] disabled:opacity-50 transition-all"
                      >
                        {!isAuthenticated ? (
                          <LockClosedIcon className="w-4 h-4" />
                        ) : (
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                          </svg>
                        )}
                        {copying ? '...' : 'Copy'}
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </>
        ) : (
          /* Empty State */
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
            <div className="p-4 rounded-full border border-[oklch(0.22_0.03_260)] bg-[oklch(0.1_0.02_260)] mb-4">
              <svg className="w-8 h-8 text-[oklch(0.3_0.01_260)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
            </div>
            <h3 className="font-mono text-sm text-[oklch(0.5_0.01_260)] uppercase tracking-wider mb-2">
              Select a Template
            </h3>
            <p className="font-mono text-[11px] text-[oklch(0.4_0.01_260)] max-w-[240px]">
              Click on a template from the list to preview its workflow visualization
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default TemplateGallery;
