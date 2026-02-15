/**
 * API service functions for workflow spec sharing and public templates
 */
import api from './api';
import type {
  PublicTemplateResponse,
  UpdateCheckResponse,
  PublicTemplatesResponse,
  TemplateDetailsResponse,
} from '../types/version';

/**
 * List public templates
 */
export async function listPublicTemplates(
  search?: string,
  category?: string,
  limit = 50,
  offset = 0
): Promise<PublicTemplatesResponse> {
  const { data } = await api.get('/api/workflow-specs/public', {
    params: { search, category, limit, offset },
  });
  return {
    specs: data.templates || [],
    total: data.total || 0,
  };
}

/**
 * Copy a public template to your account
 */
export async function copyTemplate(
  specId: string,
  newName?: string
): Promise<PublicTemplateResponse> {
  const { data } = await api.post(`/api/workflow-specs/${specId}/copy`, {
    new_name: newName,
  });
  return data;
}

/**
 * Share a spec publicly
 */
export async function shareSpec(specId: string): Promise<void> {
  await api.post(`/api/workflow-specs/${specId}/share`);
}

/**
 * Make a spec private
 */
export async function unshareSpec(specId: string): Promise<void> {
  await api.post(`/api/workflow-specs/${specId}/unshare`);
}

/**
 * Check if a copied spec has updates from the original
 */
export async function checkForUpdates(specId: string): Promise<UpdateCheckResponse> {
  const { data } = await api.get(`/api/workflow-specs/${specId}/updates`);
  return data;
}

/**
 * Pull latest content from original spec
 */
export async function pullUpdate(specId: string): Promise<PublicTemplateResponse> {
  const { data } = await api.post(`/api/workflow-specs/${specId}/pull-update`);
  return data;
}

/**
 * Get template details including YAML for preview
 */
export async function getTemplateDetails(specId: string): Promise<TemplateDetailsResponse> {
  const { data } = await api.get(`/api/workflow-specs/${specId}/yaml`);
  return {
    id: specId,
    name: data.name,
    description: data.description,
    version: data.version || '1.0.0',
    created_by: data.created_by,
    created_at: data.created_at || '',
    total_runs: data.total_runs || 0,
    successful_runs: data.successful_runs || 0,
    is_public: true,
    category: data.category,
    pattern_type: data.pattern_type,
    spec_yaml: data.yaml_content,
  };
}
