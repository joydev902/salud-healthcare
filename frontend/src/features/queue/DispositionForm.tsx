import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError } from '../../shared/api/client'
import {
  DISPOSITION_LABEL,
  MIN_JUSTIFICATION_LENGTH,
  SELECTABLE_DISPOSITIONS,
  type Disposition,
} from '../../shared/dispositions'
import { formatDateTime } from '../../shared/format'
import { queueApi, type OpportunityDetail } from './api'

interface StaleDetails {
  current_disposition: Disposition
  last_disposition_at: string | null
  last_disposition_by_email: string | null
}

export default function DispositionForm({ opportunity }: { opportunity: OpportunityDetail }) {
  const queryClient = useQueryClient()
  const [disposition, setDisposition] = useState<Disposition | null>(null)
  const [justification, setJustification] = useState('')
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: () =>
      queueApi.recordDisposition(opportunity.id, {
        new_disposition: disposition!,
        justification,
        expected_version: opportunity.disposition_version,
      }),
    onSuccess: () => {
      setDisposition(null)
      setJustification('')
      setSaved(true)
    },
    onSettled: () => {
      // Success and a 409 both mean the server state moved on; refetch everything shown.
      queryClient.invalidateQueries({ queryKey: ['opportunity', opportunity.id] })
      queryClient.invalidateQueries({ queryKey: ['member'] })
      queryClient.invalidateQueries({ queryKey: ['members'] })
    },
  })

  const trimmed = justification.trim()
  const canSubmit =
    disposition !== null && trimmed.length >= MIN_JUSTIFICATION_LENGTH && !save.isPending

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setSaved(false)
    if (canSubmit) save.mutate()
  }

  const stale =
    save.error instanceof ApiError && save.error.code === 'STALE_VERSION'
      ? (save.error.details as StaleDetails)
      : null

  return (
    <form className="disposition-form stack" onSubmit={onSubmit}>
      <fieldset>
        <legend>Decision</legend>
        <div className="choice-row">
          {SELECTABLE_DISPOSITIONS.map((d) => (
            <label key={d} className={d === disposition ? 'choice selected' : 'choice'}>
              <input
                type="radio"
                name="disposition"
                value={d}
                checked={d === disposition}
                onChange={() => setDisposition(d)}
              />
              {DISPOSITION_LABEL[d]}
            </label>
          ))}
        </div>
      </fieldset>
      <label>
        Justification for this opportunity
        <textarea
          rows={4}
          maxLength={4000}
          value={justification}
          onChange={(e) => setJustification(e.target.value)}
          placeholder="What did you review, and why does it support this decision?"
        />
        <span className="muted hint">
          Required, at least {MIN_JUSTIFICATION_LENGTH} characters. Recorded permanently in the
          audit history.
        </span>
      </label>

      {stale ? (
        <p className="form-error" role="alert">
          Someone else updated this opportunity to{' '}
          <strong>{DISPOSITION_LABEL[stale.current_disposition]}</strong>
          {stale.last_disposition_by_email && <> ({stale.last_disposition_by_email})</>} at{' '}
          {formatDateTime(stale.last_disposition_at)}. The page now shows their decision; submit
          again if yours still applies.
        </p>
      ) : (
        save.error && (
          <p className="form-error" role="alert">
            {save.error instanceof ApiError ? save.error.message : 'Could not save the decision.'}
          </p>
        )
      )}
      {saved && !save.error && <p className="success">Decision saved.</p>}

      <div>
        <button type="submit" disabled={!canSubmit}>
          {save.isPending ? 'Saving…' : 'Save decision'}
        </button>
      </div>
    </form>
  )
}
