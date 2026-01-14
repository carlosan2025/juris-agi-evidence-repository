// Common types
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// Document types
export type ExtractionStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type ProfileCode = 'general' | 'vc' | 'pharma' | 'insurance';

export const PROFILE_OPTIONS: { value: ProfileCode; label: string; description: string }[] = [
  { value: 'vc', label: 'Venture Capital', description: 'Startup due diligence, funding, metrics' },
  { value: 'pharma', label: 'Pharma/Biotech', description: 'Drug development, clinical trials, regulatory' },
  { value: 'insurance', label: 'Insurance', description: 'Underwriting, claims, risk assessment' },
  { value: 'general', label: 'General', description: 'Generic document analysis' },
];

export interface Document {
  id: string;
  filename: string;
  content_type: string;
  file_hash: string;
  file_size: number;
  profile_code: ProfileCode;
  metadata: Record<string, unknown>;
  current_version_id: string | null;
  extraction_status: ExtractionStatus;
  created_at: string;
  updated_at: string;
}

export interface DocumentVersion {
  id: string;
  document_id: string;
  version_number: number;
  storage_path: string;
  file_size: number;
  extracted_text: string | null;
  extraction_status: ExtractionStatus;
  created_at: string;
}

// Project types
export interface Project {
  id: string;
  name: string;
  description: string | null;
  case_ref: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  document_count?: number;
}

export interface ProjectCreate {
  name: string;
  description?: string;
  case_ref?: string;
  metadata?: Record<string, unknown>;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
  case_ref?: string;
  metadata?: Record<string, unknown>;
}

// Job types
export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled' | 'retrying';
export type JobType = 'extraction' | 'embedding' | 'ingestion' | 'analysis' | 'multi_level_extraction';

export interface Job {
  id: string;
  job_type: JobType;
  status: JobStatus;
  priority: number;
  entity_type: string | null;
  entity_id: string | null;
  parameters: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error_message: string | null;
  attempts: number;
  max_attempts: number;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

// Integration types
export type IntegrationProvider = 'openai' | 'lovepdf' | 'aws' | 'anthropic' | 'custom';

export interface IntegrationKey {
  id: string;
  provider: IntegrationProvider;
  name: string;
  key_type: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
  created_by: string | null;
  updated_by: string | null;
  masked_value: string;
}

export interface IntegrationKeyWithValue extends IntegrationKey {
  decrypted_value: string;
}

export interface IntegrationKeyCreate {
  provider: IntegrationProvider;
  name: string;
  key_type: string;
  value: string;
  description?: string;
  is_active?: boolean;
}

export interface IntegrationKeyUpdate {
  name?: string;
  description?: string;
  is_active?: boolean;
  value?: string;
}

export interface IntegrationStatus {
  configured: boolean;
  keys_count: number;
  active_keys_count: number;
  last_used: string | null;
  required_key_types: string[];
  configured_key_types: string[];
  missing_key_types: string[];
}

export interface IntegrationStatusResponse {
  openai: IntegrationStatus;
  lovepdf: IntegrationStatus;
  aws: IntegrationStatus;
}

export interface IntegrationKeyListResponse {
  items: IntegrationKey[];
  total: number;
  by_provider: Record<string, number>;
}

// Evidence types
export interface Span {
  id: string;
  document_version_id: string;
  text_content: string;
  span_type: string;
  start_locator: Record<string, unknown>;
  end_locator: Record<string, unknown>;
  created_at: string;
}

export interface Claim {
  id: string;
  project_id: string;
  span_id: string;
  claim_text: string;
  claim_type: string;
  certainty: string;
  reliability: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface EvidencePack {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  created_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  items_count?: number;
}

// Search types
export interface SearchResult {
  document_id: string;
  document_version_id: string;
  chunk_id: string;
  text: string;
  score: number;
  metadata: Record<string, unknown>;
}

export interface SearchRequest {
  query: string;
  limit?: number;
  threshold?: number;
  document_ids?: string[];
}

// Health types
export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  version: string;
  timestamp: string;
  database: string;
  redis: string;
  details?: Record<string, unknown>;
}
