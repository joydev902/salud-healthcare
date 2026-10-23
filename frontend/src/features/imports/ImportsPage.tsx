import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../../shared/api/client'
import { formatDateTime, formatNumber } from '../../shared/format'
import { meQueryKey } from '../auth/useAuth'
import { importsApi, type ImportDetail, type UploadStatus } from './api'

const STATUS_LABEL: Record<UploadStatus, string> = {
  PROCESSING: 'Processing',
  COMPLETED: 'Completed',
  COMPLETED_WITH_ERRORS: 'Completed with errors',
  FAILED: 'Failed',
}

function StatusBadge({ status }: { status: UploadStatus }) {
  return <span className={`badge status-${status.toLowerCase()}`}>{STATUS_LABEL[status]}</span>
}

export default function ImportsPage() {
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const history = useInfiniteQuery({
    queryKey: ['imports', 'history'],
    queryFn: ({ pageParam }) => importsApi.list(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })

  const upload = useMutation({
    mutationFn: importsApi.upload,
    onSuccess: (result) => {
      queryClient.setQueryData(['imports', 'detail', result.id], result)
      setSelectedId(result.id)
      setFile(null)
      if (fileInput.current) fileInput.current.value = ''
    },
    onError: (err) => {
      const uploadId = err instanceof ApiError ? uploadIdFrom(err.details) : null
      if (uploadId) setSelectedId(uploadId)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['imports', 'history'] })
      queryClient.invalidateQueries({ queryKey: meQueryKey })
      queryClient.invalidateQueries({ queryKey: ['ref'] })
      queryClient.invalidateQueries({ queryKey: ['members'] })
    },
  })

  const detail = useQuery({
    queryKey: ['imports', 'detail', selectedId],
    queryFn: () => importsApi.get(selectedId!),
    enabled: selectedId !== null,
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (file) upload.mutate(file)
  }

  const rows = history.data?.pages.flatMap((p) => p.items) ?? []

  return (
    <main className="page stack">
      <h1>Data imports</h1>

      <form className="card upload-card" onSubmit={onSubmit}>
        <div>
          <h2>Upload opportunity file</h2>
          <p className="muted">
            CSV with the 15 standard MRA columns. Re-uploading a file is safe: rows already imported
            are counted as duplicates and not added again.
          </p>
        </div>
        <div className="upload-controls">
          <input
            ref={fileInput}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <button type="submit" disabled={!file || upload.isPending}>
            {upload.isPending ? 'Importing…' : 'Import'}
          </button>
        </div>
        {upload.error && (
          <p className="form-error" role="alert">
            {upload.error instanceof ApiError ? upload.error.message : 'Upload failed'}
          </p>
        )}
      </form>

      {selectedId && detail.data && <ImportResult result={detail.data} />}

      <section className="card">
        <h2>Upload history</h2>
        {history.isPending ? (
          <p className="muted">Loading…</p>
        ) : history.isError ? (
          <p className="form-error">Could not load upload history.</p>
        ) : rows.length === 0 ? (
          <p className="muted">No files have been imported yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>File</th>
                <th>Uploaded by</th>
                <th>Uploaded at</th>
                <th>Status</th>
                <th className="num">Rows</th>
                <th className="num">New evidence</th>
                <th className="num">Duplicates</th>
                <th className="num">Rejected</th>
                <th className="num">New opportunities</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className={r.id === selectedId ? 'selected clickable' : 'clickable'}
                  onClick={() => setSelectedId(r.id)}
                >
                  <td>{r.filename}</td>
                  <td>{r.uploaded_by_email}</td>
                  <td>{formatDateTime(r.started_at)}</td>
                  <td>
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="num">{formatNumber(r.total_rows)}</td>
                  <td className="num">{formatNumber(r.inserted_source_rows)}</td>
                  <td className="num">{formatNumber(r.duplicate_source_rows)}</td>
                  <td className="num">{formatNumber(r.rejected_rows)}</td>
                  <td className="num">{formatNumber(r.new_opportunities)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {history.hasNextPage && (
          <button
            type="button"
            className="secondary load-more"
            onClick={() => history.fetchNextPage()}
            disabled={history.isFetchingNextPage}
          >
            {history.isFetchingNextPage ? 'Loading…' : 'Load more'}
          </button>
        )}
      </section>
    </main>
  )
}

function ImportResult({ result }: { result: ImportDetail }) {
  return (
    <section className="card stack">
      <div className="result-header">
        <h2>{result.filename}</h2>
        <StatusBadge status={result.status} />
        <span className="muted">
          {formatDateTime(result.started_at)} · {result.uploaded_by_email}
        </span>
      </div>

      {result.missing_columns.length > 0 && (
        <p className="form-error">
          File rejected — missing required columns:{' '}
          <strong>{result.missing_columns.join(', ')}</strong>
        </p>
      )}
      {result.message && result.missing_columns.length === 0 && (
        <p className="form-error">{result.message}</p>
      )}

      {result.status !== 'FAILED' || result.total_rows > 0 ? (
        <dl className="stats">
          <Stat label="Rows in file" value={result.total_rows} />
          <Stat label="New evidence rows" value={result.inserted_source_rows} />
          <Stat label="Duplicates skipped" value={result.duplicate_source_rows} />
          <Stat label="Rows rejected" value={result.rejected_rows} />
          <Stat label="New opportunities" value={result.new_opportunities} />
        </dl>
      ) : null}

      <IssueTable title="Errors (row rejected)" issues={result.errors} total={result.error_count} />
      <IssueTable
        title="Warnings (row imported)"
        issues={result.warnings}
        total={result.warning_count}
      />
    </section>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{formatNumber(value)}</dd>
    </div>
  )
}

function IssueTable({
  title,
  issues,
  total,
}: {
  title: string
  issues: ImportDetail['errors']
  total: number
}) {
  if (total === 0) return null
  return (
    <div>
      <h3>
        {title} — {formatNumber(total)}
        {total > issues.length && <span className="muted"> (showing first {issues.length})</span>}
      </h3>
      <table className="table compact">
        <thead>
          <tr>
            <th className="num">Row</th>
            <th>Field</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {issues.map((i, idx) => (
            <tr key={`${i.row}-${i.field}-${idx}`}>
              <td className="num">{i.row}</td>
              <td>{i.field ?? '—'}</td>
              <td>{i.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function uploadIdFrom(details: unknown): string | null {
  if (details && typeof details === 'object' && 'upload_id' in details) {
    const id = (details as { upload_id: unknown }).upload_id
    return typeof id === 'string' ? id : null
  }
  return null
}
