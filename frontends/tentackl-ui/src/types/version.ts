/**
 * Types for workflow spec sharing and public templates
 */

/**
 * A public workflow template that can be copied
 */
export interface PublicTemplateResponse {
  id: string;
  name: string;
  description?: string;
  version: string;
  created_by?: string;
  created_at: string;
  total_runs: number;
  successful_runs: number;
  is_public: boolean;
  category?: string;
  pattern_type?: string;
}

/**
 * Detailed template info including YAML for preview
 */
export interface TemplateDetailsResponse extends PublicTemplateResponse {
  spec_yaml: string;
}

/**
 * Response when checking for updates from original template
 */
export interface UpdateCheckResponse {
  has_update: boolean;
  current_version?: string;
  latest_version?: string;
  original_id?: string;
  original_name?: string;
  original_yaml?: string;
  local_yaml?: string;
  reason?: string;
}

/**
 * Response when listing public templates
 */
export interface PublicTemplatesResponse {
  specs: PublicTemplateResponse[];
  total: number;
}
