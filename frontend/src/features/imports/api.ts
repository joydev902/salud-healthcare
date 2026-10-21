import { apiFetch } from '../../shared/api/client'

export type UploadStatus = 'PROCESSING' | 'COMPLETED' | 'COMPLETED_WITH_ERRORS' | 'FAILED'

export interface ImportIssue {
  row: number
  field: string | null
  reason: string
}

export interface ImportSummary {
  id: string
  filename: string
  sha256: string
  status: UploadStatus
  uploaded_by_email: string
  started_at: string
  finished_at: string | null
  total_rows: number
  inserted_source_rows: number
  duplicate_source_rows: number
  rejected_rows: number
  new_opportunities: number
}

export interface ImportDetail extends ImportSummary {
  message: string | null
  missing_columns: string[]
  error_count: number
  warning_count: number
  errors: ImportIssue[]
  warnings: ImportIssue[]
}

export interface ImportPage {
  items: ImportSummary[]
  next_cursor: string | null
  has_more: boolean
}

export const importsApi = {
  upload: (file: File) => {
    const body = new FormData()
    body.append('file', file)
    return apiFetch<ImportDetail>('/imports', { method: 'POST', body })
  },
  list: (cursor: string | null) =>
    apiFetch<ImportPage>(
      `/imports?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`,
    ),
  get: (id: string) => apiFetch<ImportDetail>(`/imports/${id}`),
}
