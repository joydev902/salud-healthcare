import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError } from '../../shared/api/client'
import DispositionBadge from '../../shared/DispositionBadge'
import { formatDate, formatDateTime } from '../../shared/format'
import { useCurrentUser } from '../auth/useAuth'
import { queueApi, type OpportunityDetail } from './api'
import AuditTimeline from './AuditTimeline'
import DispositionForm from './DispositionForm'
import { HccCell } from './MemberPage'

export default function OpportunityPage() {
  const { opportunityId = '' } = useParams()
  const { data: user } = useCurrentUser()
  const detail = useQuery({
    queryKey: ['opportunity', opportunityId],
    queryFn: () => queueApi.opportunity(opportunityId),
  })

  if (detail.isPending) return <p className="page muted">Loading…</p>
  if (detail.isError) {
    const notFound = detail.error instanceof ApiError && detail.error.status === 404
    return (
      <main className="page stack">
        <p className="form-error">
          {notFound
            ? 'Opportunity not found or not assigned to you.'
            : 'Could not load this opportunity.'}
        </p>
        <Link to="/queue">← Back to work queue</Link>
      </main>
    )
  }

  const o = detail.data
  return (
    <main className="page stack">
      <Link to={`/members/${o.member.id}`}>
        ← {o.member.member_name} ({o.member.external_member_id})
      </Link>

      <section className="card stack">
        <div className="result-header">
          <h1>
            {o.icd10_code} <span className="muted">{o.icd10_description}</span>
          </h1>
          <DispositionBadge value={o.current_disposition} />
        </div>
        <dl className="facts">
          <Fact label="Performance year">PY{o.performance_year}</Fact>
          <Fact label="HCC">
            <HccCell opportunity={o} />
          </Fact>
          <Fact label="Payer">{o.payer.name}</Fact>
          <Fact label="Provider">
            {o.provider.name} <span className="muted">· {o.provider.group_name}</span>
          </Fact>
          <Fact label="Member">
            {o.member.member_name}{' '}
            <span className="muted">
              {o.member.external_member_id} · DOB {formatDate(o.member.date_of_birth)}
            </span>
          </Fact>
          <Fact label="Last date of service">{formatDate(o.last_dos)}</Fact>
        </dl>
        {o.hcc_conflict && <HccConflict opportunity={o} />}
      </section>

      <section className="card">
        <h2>Evidence ({o.sources.length})</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Initiative</th>
              <th>Evidence</th>
              <th>Reported HCC</th>
              <th>Last DOS</th>
              <th>Source file</th>
              <th>Policy</th>
            </tr>
          </thead>
          <tbody>
            {o.sources.map((s) => (
              <tr key={s.id}>
                <td>
                  <span className="badge initiative">{s.initiative}</span>
                </td>
                <td>{s.evidence ?? <span className="muted">No evidence text</span>}</td>
                <td>
                  {s.reported_hcc_code ? (
                    <>
                      HCC {s.reported_hcc_code}
                      <div className="muted">{s.reported_hcc_description}</div>
                    </>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>{formatDate(s.last_dos)}</td>
                <td>
                  {s.source_file}
                  <div className="muted">
                    row {s.source_row_number} · imported {formatDateTime(s.imported_at)}
                  </div>
                </td>
                <td>{s.policy_number}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card stack">
        <h2>Review</h2>
        {o.disposition_version === 0 ? (
          <p className="muted">Not reviewed yet.</p>
        ) : (
          <dl className="facts">
            <Fact label="Current disposition">
              <DispositionBadge value={o.current_disposition} />
            </Fact>
            <Fact label="Last changed">
              {formatDateTime(o.last_disposition_at)}
              {o.last_disposition_by_email && (
                <span className="muted"> · {o.last_disposition_by_email}</span>
              )}
            </Fact>
            <Fact label="Justification">{o.current_note}</Fact>
          </dl>
        )}
        {user?.role === 'CODER' ? (
          <DispositionForm opportunity={o} />
        ) : (
          <p className="muted">Only coders can record dispositions.</p>
        )}
      </section>

      <section className="card">
        <h2>Audit history</h2>
        <AuditTimeline opportunityId={o.id} />
      </section>
    </main>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function HccConflict({ opportunity: o }: { opportunity: OpportunityDetail }) {
  return (
    <div className="callout warning">
      <strong>Payers disagree on the HCC for this diagnosis.</strong> Each payer's assertion is kept
      as reported; none is preferred automatically.
      <ul>
        <li>
          {o.payer.name}: {o.hcc_code ? `HCC ${o.hcc_code} ${o.hcc_description ?? ''}` : 'none'}{' '}
          <span className="muted">(this opportunity)</span>
        </li>
        {o.hcc_candidates.map((c) => (
          <li key={c.opportunity_id}>
            <Link to={`/opportunities/${c.opportunity_id}`}>{c.payer_name}</Link>:{' '}
            {c.hcc_code ? `HCC ${c.hcc_code} ${c.hcc_description ?? ''}` : 'none'}
          </li>
        ))}
      </ul>
    </div>
  )
}
