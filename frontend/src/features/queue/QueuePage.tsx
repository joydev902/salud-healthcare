import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { ApiError } from '../../shared/api/client'
import { DISPOSITION_LABEL, DISPOSITIONS } from '../../shared/dispositions'
import { formatDate, formatNumber } from '../../shared/format'
import { useCurrentUser } from '../auth/useAuth'
import { ACTIVE_FILTER, filtersFrom, PAGE_SIZE, queueApi, type FilterKey } from './api'

const STALE_REFERENCE_MS = 5 * 60 * 1000

export default function QueuePage() {
  const { data: user } = useCurrentUser()
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = filtersFrom(searchParams)
  const filterKey = filters.toString()

  const setFilter = (key: FilterKey, value: string) => {
    const next = new URLSearchParams(filters)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearchParams(next, { replace: true })
  }

  if (user && user.providers.length === 0) {
    return (
      <main className="page">
        <h1>Work queue</h1>
        <p className="muted">
          {user.role === 'ADMIN'
            ? 'No providers yet. Import a CSV and every provider in that file is included.'
            : 'You have no provider assignments yet. Ask an Admin to assign providers to you.'}
        </p>
      </main>
    )
  }

  return (
    <main className="page stack">
      <h1>Work queue</h1>
      <QueueFilters filters={filters} onChange={setFilter} onReset={() => setSearchParams({})} />
      <QueueResults key={filterKey} filters={filters} />
    </main>
  )
}

function QueueFilters({
  filters,
  onChange,
  onReset,
}: {
  filters: URLSearchParams
  onChange: (key: FilterKey, value: string) => void
  onReset: () => void
}) {
  const reference = { staleTime: STALE_REFERENCE_MS }
  const providers = useQuery({
    queryKey: ['ref', 'providers'],
    queryFn: queueApi.providers,
    ...reference,
  })
  const payers = useQuery({ queryKey: ['ref', 'payers'], queryFn: queueApi.payers, ...reference })
  const initiatives = useQuery({
    queryKey: ['ref', 'initiatives'],
    queryFn: queueApi.initiatives,
    ...reference,
  })
  const years = useQuery({
    queryKey: ['ref', 'years'],
    queryFn: queueApi.performanceYears,
    ...reference,
  })
  const [search, setSearch] = useState(filters.get('q') ?? '')

  const onSearch = (e: FormEvent) => {
    e.preventDefault()
    onChange('q', search.trim())
  }

  return (
    <section className="card filters">
      <form className="filter-search" onSubmit={onSearch}>
        <label>
          Member
          <input
            type="search"
            placeholder="Member ID or name"
            value={search}
            maxLength={100}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <button type="submit" className="secondary">
          Search
        </button>
      </form>
      <FilterSelect
        label="Provider"
        value={filters.get('provider_id')}
        onChange={(v) => onChange('provider_id', v)}
        options={(providers.data ?? []).map((p) => ({
          value: String(p.id),
          label: `${p.name} · ${p.group_name}`,
        }))}
      />
      <FilterSelect
        label="Payer"
        value={filters.get('payer_id')}
        onChange={(v) => onChange('payer_id', v)}
        options={(payers.data ?? []).map((p) => ({ value: String(p.id), label: p.name }))}
      />
      <FilterSelect
        label="Initiative"
        value={filters.get('initiative')}
        onChange={(v) => onChange('initiative', v)}
        options={(initiatives.data ?? []).map((i) => ({ value: i, label: i }))}
      />
      <FilterSelect
        label="Disposition"
        value={filters.get('disposition')}
        onChange={(v) => onChange('disposition', v)}
        options={[
          { value: ACTIVE_FILTER, label: 'Active (not confirmed or denied)' },
          ...DISPOSITIONS.map((d) => ({ value: d, label: DISPOSITION_LABEL[d] })),
        ]}
      />
      <FilterSelect
        label="Performance year"
        value={filters.get('performance_year')}
        onChange={(v) => onChange('performance_year', v)}
        options={(years.data ?? []).map((y) => ({ value: String(y), label: `PY${y}` }))}
      />
      {filters.size > 0 && (
        <button
          type="button"
          className="link"
          onClick={() => {
            setSearch('')
            onReset()
          }}
        >
          Clear filters
        </button>
      )}
    </section>
  )
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string | null
  options: { value: string; label: string }[]
  onChange: (value: string) => void
}) {
  return (
    <label>
      {label}
      <select value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
        <option value="">All</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function QueueResults({ filters }: { filters: URLSearchParams }) {
  const navigate = useNavigate()
  // cursors[i] fetches page i; page 0 has no cursor.
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const page = cursors.length - 1
  const cursor = cursors[page]

  const members = useQuery({
    queryKey: ['members', filters.toString(), cursor],
    queryFn: () => queueApi.members(filters, cursor),
    placeholderData: keepPreviousData,
  })

  if (members.isPending) return <p className="muted">Loading…</p>
  if (members.isError) {
    const message =
      members.error instanceof ApiError ? members.error.message : 'Could not load the work queue.'
    return <p className="form-error">{message}</p>
  }

  const { items, next_cursor } = members.data
  const memberQuery = filters.toString()

  return (
    <section className="card">
      {items.length === 0 ? (
        <p className="muted">No members match these filters.</p>
      ) : (
        <table className={members.isPlaceholderData ? 'table loading' : 'table'}>
          <thead>
            <tr>
              <th>Member ID</th>
              <th>Name</th>
              <th>Date of birth</th>
              <th>Provider</th>
              <th>Payer</th>
              <th className="num" title="Matching opportunities not yet confirmed or denied">
                Open
              </th>
              <th className="num" title="Opportunities matching the current filters">
                Matched
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((m) => (
              <tr
                key={m.member_id}
                className="clickable"
                onClick={() =>
                  navigate(`/members/${m.member_id}${memberQuery ? `?${memberQuery}` : ''}`)
                }
              >
                <td>
                  <strong>{m.external_member_id}</strong>
                </td>
                <td>{m.member_name}</td>
                <td>{formatDate(m.date_of_birth)}</td>
                <td>{m.providers.join(', ')}</td>
                <td>{m.payers.join(', ')}</td>
                <td className="num">{formatNumber(m.open_opportunity_count)}</td>
                <td className="num">{formatNumber(m.matched_opportunity_count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="pager">
        <span className="muted">
          Page {page + 1} · up to {PAGE_SIZE} members per page · counts reflect the active filters
        </span>
        <button
          type="button"
          className="secondary"
          disabled={page === 0 || members.isFetching}
          onClick={() => setCursors((c) => c.slice(0, -1))}
        >
          Previous
        </button>
        <button
          type="button"
          className="secondary"
          disabled={!next_cursor || members.isFetching}
          onClick={() => next_cursor && setCursors((c) => [...c, next_cursor])}
        >
          Next
        </button>
      </div>
    </section>
  )
}
