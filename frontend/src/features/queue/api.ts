import { apiFetch } from '../../shared/api/client'
import { ACTIVE_DISPOSITIONS, type Disposition } from '../../shared/dispositions'
import type { ProviderRef } from '../auth/api'

export interface PayerRef {
  id: number
  name: string
}

export interface QueueMember {
  member_id: string
  external_member_id: string
  member_name: string
  date_of_birth: string | null
  matched_opportunity_count: number
  open_opportunity_count: number
  providers: string[]
  payers: string[]
}

export interface MemberPage {
  items: QueueMember[]
  next_cursor: string | null
  has_more: boolean
}

export interface MemberDetail {
  id: string
  external_member_id: string
  member_name: string
  date_of_birth: string | null
  policies: { payer_name: string; policy_number: string }[]
  providers: ProviderRef[]
  total_opportunity_count: number
  open_opportunity_count: number
}

export interface OpportunitySummary {
  id: string
  performance_year: number
  icd10_code: string
  icd10_description: string | null
  hcc_code: string | null
  hcc_description: string | null
  hcc_conflict: boolean
  payer: PayerRef
  provider: ProviderRef
  current_disposition: Disposition
  disposition_version: number
  last_disposition_at: string | null
  initiatives: string[]
  source_files: string[]
  source_count: number
  last_dos: string | null
}

export interface SourceEvidence {
  id: number
  source_file: string
  source_row_number: number
  policy_number: string
  initiative: string
  evidence: string | null
  last_dos: string | null
  reported_hcc_code: string | null
  reported_hcc_description: string | null
  imported_at: string
}

export interface OpportunityDetail extends OpportunitySummary {
  member: Pick<MemberDetail, 'id' | 'external_member_id' | 'member_name' | 'date_of_birth'>
  current_note: string | null
  last_disposition_by_email: string | null
  sources: SourceEvidence[]
  hcc_candidates: {
    opportunity_id: string
    payer_name: string
    hcc_code: string | null
    hcc_description: string | null
  }[]
}

export interface DispositionResult {
  opportunity_id: string
  current_disposition: Disposition
  disposition_version: number
  changed_at: string
}

export interface DispositionHistoryItem {
  id: number
  changed_at: string
  changed_by_email: string
  changed_by_name: string
  old_status: Disposition
  new_status: Disposition
  note: string
  old_version: number
  new_version: number
}

/** Queue filters exactly as they appear in the page URL. */
export const FILTER_KEYS = [
  'provider_id',
  'payer_id',
  'initiative',
  'disposition',
  'performance_year',
  'q',
] as const

export type FilterKey = (typeof FILTER_KEYS)[number]

/** "ACTIVE" is a UI shorthand that expands to every not-yet-final disposition. */
export const ACTIVE_FILTER = 'ACTIVE'

export function filtersFrom(params: URLSearchParams): URLSearchParams {
  const out = new URLSearchParams()
  for (const key of FILTER_KEYS) {
    const value = params.get(key)
    if (value) out.set(key, value)
  }
  return out
}

function toApiParams(filters: URLSearchParams, extra: Record<string, string> = {}): string {
  const out = new URLSearchParams()
  for (const [key, value] of filters) {
    if (key === 'disposition' && value === ACTIVE_FILTER) {
      ACTIVE_DISPOSITIONS.forEach((d) => out.append('disposition', d))
    } else {
      out.append(key, value)
    }
  }
  for (const [key, value] of Object.entries(extra)) out.set(key, value)
  const qs = out.toString()
  return qs ? `?${qs}` : ''
}

export const PAGE_SIZE = 25

export const queueApi = {
  members: (filters: URLSearchParams, cursor: string | null) =>
    apiFetch<MemberPage>(
      `/members${toApiParams(filters, { limit: String(PAGE_SIZE), ...(cursor ? { cursor } : {}) })}`,
    ),
  member: (id: string) => apiFetch<MemberDetail>(`/members/${id}`),
  memberOpportunities: (id: string, filters: URLSearchParams) => {
    const scoped = new URLSearchParams(filters)
    scoped.delete('q')
    return apiFetch<OpportunitySummary[]>(`/members/${id}/opportunities${toApiParams(scoped)}`)
  },
  opportunity: (id: string) => apiFetch<OpportunityDetail>(`/opportunities/${id}`),
  dispositionHistory: (id: string) =>
    apiFetch<DispositionHistoryItem[]>(`/opportunities/${id}/dispositions`),
  recordDisposition: (
    id: string,
    body: { new_disposition: Disposition; justification: string; expected_version: number },
  ) =>
    apiFetch<DispositionResult>(`/opportunities/${id}/dispositions`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  providers: () => apiFetch<ProviderRef[]>('/providers'),
  payers: () => apiFetch<PayerRef[]>('/payers'),
  initiatives: () => apiFetch<string[]>('/initiatives'),
  performanceYears: () => apiFetch<number[]>('/performance-years'),
}
