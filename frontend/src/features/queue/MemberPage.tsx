import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { ApiError } from '../../shared/api/client'
import DispositionBadge from '../../shared/DispositionBadge'
import { formatDate, formatNumber } from '../../shared/format'
import { filtersFrom, queueApi, type OpportunitySummary } from './api'

export default function MemberPage() {
  const { memberId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const queueFilters = filtersFrom(searchParams)
  const opportunityFilters = new URLSearchParams(queueFilters)
  opportunityFilters.delete('q')
  const filtered = opportunityFilters.size > 0
  const backToQueue = `/queue${queueFilters.size ? `?${queueFilters}` : ''}`

  const member = useQuery({
    queryKey: ['member', memberId],
    queryFn: () => queueApi.member(memberId),
  })
  const opportunities = useQuery({
    queryKey: ['member', memberId, 'opportunities', opportunityFilters.toString()],
    queryFn: () => queueApi.memberOpportunities(memberId, opportunityFilters),
    enabled: member.isSuccess,
  })

  if (member.isPending) return <p className="page muted">Loading…</p>
  if (member.isError) {
    const notFound = member.error instanceof ApiError && member.error.status === 404
    return (
      <main className="page stack">
        <p className="form-error">
          {notFound ? 'Member not found or not assigned to you.' : 'Could not load this member.'}
        </p>
        <Link to={backToQueue}>← Back to work queue</Link>
      </main>
    )
  }

  const m = member.data
  return (
    <main className="page stack">
      <Link to={backToQueue}>← Back to work queue</Link>
      <section className="card member-header">
        <div>
          <h1>{m.member_name}</h1>
          <p className="muted">
            {m.external_member_id} · DOB {formatDate(m.date_of_birth)}
          </p>
        </div>
        <dl className="facts">
          <div>
            <dt>Policies</dt>
            <dd>
              {m.policies.map((p) => (
                <div key={`${p.payer_name}-${p.policy_number}`}>
                  {p.payer_name} <span className="muted">{p.policy_number}</span>
                </div>
              ))}
            </dd>
          </div>
          <div>
            <dt>Providers</dt>
            <dd>
              {m.providers.map((p) => (
                <div key={p.id}>
                  {p.name} <span className="muted">· {p.group_name}</span>
                </div>
              ))}
            </dd>
          </div>
          <div>
            <dt>Open opportunities</dt>
            <dd className="big">
              {formatNumber(m.open_opportunity_count)}
              <span className="muted"> of {formatNumber(m.total_opportunity_count)}</span>
            </dd>
          </div>
        </dl>
      </section>

      <section className="card">
        <div className="section-header">
          <h2>Opportunities</h2>
          {filtered && (
            <span className="muted">
              Showing opportunities matching the queue filters ·{' '}
              <Link to={`/members/${memberId}`}>Show all</Link>
            </span>
          )}
        </div>
        {opportunities.isPending ? (
          <p className="muted">Loading…</p>
        ) : opportunities.isError ? (
          <p className="form-error">Could not load opportunities.</p>
        ) : opportunities.data.length === 0 ? (
          <p className="muted">No opportunities match these filters.</p>
        ) : (
          <OpportunityTable rows={opportunities.data} />
        )}
      </section>
    </main>
  )
}

function OpportunityTable({ rows }: { rows: OpportunitySummary[] }) {
  const navigate = useNavigate()
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Year</th>
          <th>Diagnosis (ICD-10)</th>
          <th>HCC</th>
          <th>Payer</th>
          <th>Provider</th>
          <th>Initiatives</th>
          <th className="num">Evidence</th>
          <th>Last DOS</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((o) => (
          <tr key={o.id} className="clickable" onClick={() => navigate(`/opportunities/${o.id}`)}>
            <td>PY{o.performance_year}</td>
            <td>
              <strong>{o.icd10_code}</strong>
              <div className="muted">{o.icd10_description ?? '—'}</div>
            </td>
            <td>
              <HccCell opportunity={o} />
            </td>
            <td>{o.payer.name}</td>
            <td>{o.provider.name}</td>
            <td>
              <div className="badges">
                {o.initiatives.map((i) => (
                  <span key={i} className="badge initiative">
                    {i}
                  </span>
                ))}
              </div>
            </td>
            <td className="num" title={o.source_files.join('\n')}>
              {formatNumber(o.source_count)}
            </td>
            <td>{formatDate(o.last_dos)}</td>
            <td>
              <DispositionBadge value={o.current_disposition} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function HccCell({ opportunity: o }: { opportunity: OpportunitySummary }) {
  return (
    <>
      {o.hcc_code ? (
        <>
          <strong>HCC {o.hcc_code}</strong>
          <div className="muted">{o.hcc_description}</div>
        </>
      ) : (
        <span className="muted">Non-HCC</span>
      )}
      {o.hcc_conflict && (
        <div>
          <span className="badge warning" title="Payers disagree on the HCC for this diagnosis">
            HCC conflict
          </span>
        </div>
      )}
    </>
  )
}
