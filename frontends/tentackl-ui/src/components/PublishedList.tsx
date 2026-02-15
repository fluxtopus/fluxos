'use client';

import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import toast from 'react-hot-toast';
import { listPublished, runPublished, getPublished, updatePublished, deletePublished } from '../services/arrow';
import type { PublishedWorkflow, PublishedWorkflowDetails } from '../services/arrow';
import { ShareButton } from './VersionActions/ShareButton';
import { UpdateBadge } from './PublicGallery/UpdateBadge';

const PublishedList: React.FC = () => {
  const router = useRouter();
  const [items, setItems] = React.useState<PublishedWorkflow[]>([]);
  const [loading, setLoading] = React.useState<boolean>(false);
  const [editing, setEditing] = React.useState<(PublishedWorkflowDetails & { yaml: string }) | null>(null);
  const [saving, setSaving] = React.useState<boolean>(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await listPublished();
      setItems(res);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => { load(); }, []);

  const handleShareChange = (specId: string, isPublic: boolean) => {
    setItems(prev => prev.map(item =>
      item.id === specId ? { ...item, is_public: isPublic } : item
    ));
  };

  return (
    <div className="space-y-2">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Workflow Specs</h3>
        <div className="flex items-center gap-3">
          <Link
            href="/specs/public"
            className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline"
          >
            Browse Public Templates
          </Link>
          <button
            onClick={load}
            className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            <span className={`w-4 h-4 inline-block ${loading ? 'animate-spin' : ''}`}>⟳</span>
          </button>
        </div>
      </div>
      {items.length === 0 && (
        <div className="p-8 text-center text-gray-500 dark:text-gray-400">No workflow specs</div>
      )}
      {items.map((w) => (
        <div key={w.id} className="p-3 rounded bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-gray-900 dark:text-white truncate">{w.name}</span>
                {w.version_tag && (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                    v{w.version_tag}
                  </span>
                )}
                <UpdateBadge specId={w.id} copiedFromId={w.copied_from_id} />
              </div>
              <div className="text-xs text-gray-500 truncate">{w.id}</div>
            </div>
            <div className="flex items-center gap-2 ml-4">
              <ShareButton
                specId={w.id}
                isPublic={w.is_public || false}
                onShareChange={(isPublic) => handleShareChange(w.id, isPublic)}
              />
              <button
                className="px-2 py-1 rounded bg-indigo-600 text-white text-xs hover:bg-indigo-700"
                onClick={async () => {
                  try {
                    const res = await runPublished(w.id);
                    if (res.ok && res.run_id) {
                      // Navigate using Next.js router
                      router.push(`/workflows?workflowRunId=${res.run_id}`);
                    } else {
                      // Show specific error messages from API
                      const errorMessages = res.errors?.map(e => e.message || e).join('\n') || 'Unknown error';
                      toast.error(`Failed to run workflow: ${errorMessages}`);
                    }
                  } catch (error) {
                    // Catch network errors or other exceptions
                    const errorMsg = error instanceof Error ? error.message : String(error);
                    toast.error(`Error running workflow: ${errorMsg}`);
                    console.error('Failed to run published workflow:', error);
                  }
                }}
              >
                Run
              </button>
              <button
                className="px-2 py-1 rounded bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-100 text-xs hover:bg-gray-300 dark:hover:bg-gray-600"
                onClick={async () => {
                  const data = await getPublished(w.id);
                  setEditing({ ...data, yaml: data.spec_yaml });
                }}
              >
                Edit
              </button>
              <button
                className="px-2 py-1 rounded bg-red-600 text-white text-xs hover:bg-red-700"
                onClick={async () => {
                  if (!window.confirm('Delete this published workflow? This will not affect existing runs.')) return;
                  const res = await deletePublished(w.id);
                  if (res.ok) {
                    await load();
                    toast.success('Workflow deleted');
                  } else {
                    toast.error('Failed to delete workflow');
                  }
                }}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      ))}

      {editing && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg w-[800px] max-w-full p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-800 dark:text-gray-200">Edit Workflow Spec</div>
              <button className="text-sm px-2 py-1" onClick={() => setEditing(null)}>✕</button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Name</label>
                <input className="w-full text-sm px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Version Tag</label>
                <input className="w-full text-sm px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" value={editing.version_tag || ''} onChange={e => setEditing({ ...editing, version_tag: e.target.value })} />
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">YAML</label>
              <textarea className="w-full h-64 text-xs font-mono px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100" value={editing.yaml} onChange={e => setEditing({ ...editing, yaml: e.target.value })} />
            </div>
            <div className="flex items-center justify-end gap-2">
              <button className="px-3 py-1 rounded text-sm" onClick={() => setEditing(null)}>Cancel</button>
              <button
                className="px-3 py-1 rounded bg-blue-600 text-white text-sm hover:bg-blue-700 disabled:opacity-50"
                disabled={saving}
                onClick={async () => {
                  if (!editing) return;
                  setSaving(true);
                  const res = await updatePublished(editing.id, editing.yaml, editing.name, editing.version_tag);
                  setSaving(false);
                  if (!res.ok) {
                    toast.error('Validation/Save failed');
                    return;
                  }
                  toast.success('Workflow saved');
                  setEditing(null);
                  await load();
                }}
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PublishedList;
