import { useQuery } from '@tanstack/react-query'
import DispositionBadge from '../../shared/DispositionBadge'
import { formatDateTime } from '../../shared/format'
import { queueApi } from './api'

export default function AuditTimeline({ opportunityId }: { opportunityId: string }) {
  const history = useQuery({
    queryKey: ['opportunity', opportunityId, 'history'],
    queryFn: () => queueApi.dispositionHistory(opportunityId),
  })

  if (history.isPending) return <p className="muted">Loading history…</p>
  if (history.isError) return <p className="form-error">Could not load the audit history.</p>
  if (history.data.length === 0) {
    return <p className="muted">No decisions recorded yet.</p>
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>When</th>
          <th>Coder</th>
          <th>Previous</th>
          <th>New</th>
          <th>Justification</th>
        </tr>
      </thead>
      <tbody>
        {history.data.map((h) => (
          <tr key={h.id}>
            <td className="nowrap">{formatDateTime(h.changed_at)}</td>
            <td>
              {h.changed_by_name}
              <div className="muted">{h.changed_by_email}</div>
            </td>
            <td>
              <DispositionBadge value={h.old_status} />
            </td>
            <td>
              <DispositionBadge value={h.new_status} />
            </td>
            <td className="note">{h.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
