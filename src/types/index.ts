// ============================================================================
// Trust & Safety Priorities Dashboard — Type Definitions
// ============================================================================

// --- Enums / String Literals ---

export type RegulationStatus =
  | 'proposed'
  | 'inactive'
  | 'under_review'
  | 'passed'
  | 'implementation_period'
  | 'effective'
  | 'enforced'
  | 'challenged'
  | 'enjoined'
  | 'repealed';

// Severity / sentiment bands (shared 0-100 → 5-band scale)
export type SeverityBand = 'minimal' | 'low' | 'moderate' | 'high' | 'severe';

// The metric a user can view the heatmap by
export type HeatmapMetric = 'regulatory_severity' | 'china_sentiment';

export type ServiceTypeId =
  | 'social_media'
  | 'gaming'
  | 'ai_service'
  | 'direct_messaging'
  | 'app_store'
  | 'os_provider'
  | 'adult_content'
  | 'online_marketplace'
  | 'streaming'
  | 'other';

// Consolidated Trust & Safety obligation taxonomy (10 labels)
export type ObligationType =
  | 'age_assurance'
  | 'parental_consent'
  | 'access_restriction'
  | 'design_restrictions'
  | 'data_protection'
  | 'content_moderation'
  | 'risk_assessment'
  | 'transparency_reporting'
  | 'user_empowerment'
  | 'ai_transparency';

export type MilestoneType =
  | 'proposed'
  | 'inactive'
  | 'introduced'
  | 'committee_review'
  | 'passed'
  | 'signed'
  | 'implementation_period'
  | 'effective'
  | 'enforced'
  | 'challenged'
  | 'enjoined'
  | 'repealed'
  | 'amended';

export type LitigationStatus =
  | 'filed'
  | 'pending'
  | 'granted'
  | 'denied'
  | 'appealed'
  | 'withdrawn'
  | 'settled';

// --- Core Entities ---

export interface Jurisdiction {
  id: string;                    // ISO 3166-1 alpha-2 (e.g., "US", "GB") or sub-national (e.g., "US-CA", "AU-NSW")
  name: string;                  // Display name (e.g., "United States", "California")
  parent_id: string | null;      // Parent jurisdiction ID for sub-nationals (e.g., "US" for "US-CA")
  iso_alpha2: string;            // ISO 3166-1 alpha-2 code for ECharts mapping
  region: string;                // Geographic region (e.g., "Europe", "Asia Pacific", "North America")
  flag_emoji?: string;
}

export interface ServiceType {
  id: ServiceTypeId;
  label: string;
  description: string;
  icon?: string;
}

export interface Obligation {
  id: string;
  regulation_id: string;
  type: ObligationType;
  description: string;
  threshold_age?: number | null;
  threshold_label?: string | null;
  applies_to_service_types: ServiceTypeId[];
}

export interface Milestone {
  id: string;
  regulation_id: string;
  type: MilestoneType;
  date: string;                  // ISO 8601 date
  description: string;
  source_url?: string;
}

export interface Litigation {
  id: string;
  regulation_id: string;
  name: string;
  status: LitigationStatus;
  court?: string;
  plaintiff?: string;
  defendant?: string;
  filed_date?: string;
  description?: string;
  source_url?: string;
}

export interface Regulation {
  id: string;
  name: string;
  jurisdiction_id: string;
  summary: string;
  status: RegulationStatus;
  service_type_ids: ServiceTypeId[];
  year: number;
  source_url?: string;
  tags?: string[];
  obligations: Obligation[];
  milestones: Milestone[];
  litigations: Litigation[];
  created_at: string;
  updated_at: string;
}

// --- Market-level Trust & Safety posture (H1 2026 source of truth) ---

export interface Market {
  id: string;                       // ISO alpha-2 jurisdiction id
  jurisdiction_id: string;
  country: string;
  regulatory_status: RegulationStatus;
  regulatory_status_label: string;  // verbatim label from the spreadsheet
  service_type_ids: ServiceTypeId[];// scope / affected service types
  regulatory_severity: number;      // 0-100
  regulatory_severity_band: SeverityBand;
  china_sentiment: number;          // 0-100
  china_sentiment_band: SeverityBand;
  china_sentiment_trigger: string;
  obligation_ids: ObligationType[]; // the 10-label obligation set
  assessment_note: string;
  source_url: string;
  updated_at: string;
}

// --- Database File Structure ---

export interface RegulationsDatabase {
  version: string;
  last_updated: string;
  regulations: Regulation[];
}

export interface OverrideEntry {
  id: string;                     // Matches regulation ID
  _partial?: boolean;             // If true, only listed fields override
  _deleted?: boolean;             // If true, exclude from output
  [key: string]: unknown;         // Any regulation fields to override
}

export interface OverridesDatabase {
  version: string;
  last_updated: string;
  overrides: OverrideEntry[];
}

export interface SeenUrlsDatabase {
  version: string;
  last_updated: string;
  total_count: number;
  urls: Record<string, {
    url: string;
    first_seen: string;
    linked_record_id?: string | null;
  }>;
}

// --- Merged Data (what the frontend consumes) ---

export interface MergedData {
  version: string;
  last_updated: string;
  markets: Market[];
  regulations: Regulation[];
  jurisdictions: Jurisdiction[];
  service_types: ServiceType[];
}

// --- Filter State ---

export interface FilterState {
  search: string;
  statuses: RegulationStatus[];
  jurisdiction_ids: string[];
  service_type_ids: ServiceTypeId[];
  obligation_types: ObligationType[];
  severity_bands: SeverityBand[];
  regions: string[];
}

// --- Heatmap ---

export interface CountryRiskScore {
  jurisdiction_id: string;
  country_name: string;
  iso_alpha2: string;
  risk_score: number;            // 0-100 (value of the active metric)
  metric: HeatmapMetric;
  regulatory_severity: number;
  china_sentiment: number;
  regulation_count: number;      // markets contributing (1 in the market model)
  total_obligations: number;
  obligation_ids: ObligationType[];
  status: RegulationStatus;
}

// --- Status Metadata ---

export const STATUS_META: Record<RegulationStatus, {
  label: string;
  color: string;
  weight: number;
  order: number;
}> = {
  proposed:               { label: 'Proposed',                color: '#94a3b8', weight: 10,  order: 1 },
  inactive:               { label: 'Inactive / Lapsed',       color: '#cbd5e1', weight: 0,   order: 2 },
  under_review:           { label: 'Under Review',            color: '#f59e0b', weight: 20,  order: 3 },
  challenged:             { label: 'Challenged',              color: '#a78bfa', weight: 15,  order: 4 },
  enjoined:               { label: 'Enjoined',                color: '#6366f1', weight: 5,   order: 5 },
  passed:                 { label: 'Passed',                  color: '#3b82f6', weight: 40,  order: 6 },
  implementation_period:  { label: 'Implementation Period',   color: '#06b6d4', weight: 60,  order: 7 },
  effective:              { label: 'Effective',               color: '#10b981', weight: 70,  order: 8 },
  enforced:               { label: 'Enforced',                color: '#ef4444', weight: 100, order: 9 },
  repealed:               { label: 'Repealed',                color: '#6b7280', weight: 0,   order: 10 },
};

export const SERVICE_TYPE_META: Record<ServiceTypeId, {
  label: string;
  icon: string;
}> = {
  social_media:        { label: 'Social Media',        icon: '💬' },
  gaming:              { label: 'Gaming',              icon: '🎮' },
  ai_service:          { label: 'AI Service',          icon: '🤖' },
  direct_messaging:    { label: 'Direct Messaging',    icon: '✉️' },
  app_store:           { label: 'App Store',           icon: '📱' },
  os_provider:         { label: 'OS Provider',         icon: '💻' },
  adult_content:       { label: 'Adult Content',       icon: '🔞' },
  online_marketplace:  { label: 'Online Marketplace',  icon: '🛒' },
  streaming:           { label: 'Streaming',           icon: '📺' },
  other:               { label: 'Other',               icon: '📋' },
};

// Consolidated 10-label obligation taxonomy for Trust & Safety priorities.
// `priority` groups obligations into the broadened T&S themes surfaced on the dashboard.
export const OBLIGATION_TYPE_META: Record<ObligationType, {
  label: string;
  color: string;
  description: string;
  priority: PriorityTheme;
}> = {
  age_assurance:          { label: 'Age Assurance / Gating',            color: '#ef4444', priority: 'minor_protection',description: 'Age verification, estimation, and registration / age-gating at sign-up.' },
  parental_consent:       { label: 'Parental Consent',                  color: '#8b5cf6', priority: 'minor_protection',description: 'Guardian approval required for a minor to access a service or have data processed.' },
  access_restriction:     { label: 'Access Restriction',                color: '#3b82f6', priority: 'minor_protection',description: 'Account bans for minors, curfews, time and communication limits, keeping harmful media from minors.' },
  design_restrictions:    { label: 'Design Restrictions',               color: '#10b981', priority: 'minor_protection',description: 'Safety-by-design: default privacy, no dark patterns, loot boxes, addictive-design / feed limits.' },
  data_protection:        { label: 'Data Protection',                   color: '#84cc16', priority: 'minor_protection',description: "Minors' data minimisation, consent and processing limits." },
  content_moderation:     { label: 'Content Moderation',                color: '#eab308', priority: 'content_integrity',description: 'Detect and remove illegal and harmful content (CSAM, self-harm, etc.).' },
  risk_assessment:        { label: 'Risk Assessment',                   color: '#f97316', priority: 'governance',      description: 'Mandatory illegal-content and children-safety risk assessments.' },
  transparency_reporting: { label: 'Transparency Reporting',            color: '#0ea5e9', priority: 'governance',      description: 'Annual transparency reports and risk-assessment disclosures to the regulator.' },
  user_empowerment:       { label: 'User Empowerment / Redress',        color: '#14b8a6', priority: 'governance',      description: 'User content controls, complaint / reporting and appeal routes.' },
  ai_transparency:        { label: 'AI Transparency / Content Labelling',color: '#a855f7', priority: 'ai_safety',      description: 'AI-generated content marking, deepfake and chatbot disclosure (EU AI Act Art. 50).' },
};

// --- Trust & Safety priority themes (broadened scope) ---

export type PriorityTheme =
  | 'minor_protection'
  | 'content_integrity'
  | 'governance'
  | 'ai_safety';

export const PRIORITY_THEME_META: Record<PriorityTheme, {
  label: string;
  icon: string;
  color: string;
  description: string;
}> = {
  minor_protection:   { label: 'Minor Protection',     icon: '🛡️', color: '#3b82f6', description: 'Age assurance, parental consent, access restriction and safe-by-design duties for minors.' },
  content_integrity:  { label: 'Content Integrity',    icon: '🧹', color: '#eab308', description: 'Moderating illegal and harmful content.' },
  governance:         { label: 'Governance & Redress', icon: '⚖️', color: '#0ea5e9', description: 'Risk assessment, transparency and user redress duties.' },
  ai_safety:          { label: 'AI Safety',            icon: '🤖', color: '#a855f7', description: 'AI transparency, content labelling and disclosure.' },
};

// --- Severity / sentiment band metadata (shared 5-band scale) ---

export const BAND_META: Record<SeverityBand, {
  label: string;
  range: string;
  color: string;
  min: number;
}> = {
  minimal:  { label: 'Minimal',  range: '0-20',   color: '#1a7a3c', min: 0 },
  low:      { label: 'Low',      range: '21-40',  color: '#7cc47f', min: 21 },
  moderate: { label: 'Moderate', range: '41-60',  color: '#ffd633', min: 41 },
  high:     { label: 'High',     range: '61-80',  color: '#f08a24', min: 61 },
  severe:   { label: 'Severe',   range: '81-100', color: '#c00000', min: 81 },
};

export function bandFromScore(score: number): SeverityBand {
  if (score >= 81) return 'severe';
  if (score >= 61) return 'high';
  if (score >= 41) return 'moderate';
  if (score >= 21) return 'low';
  return 'minimal';
}
