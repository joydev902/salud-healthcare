// dateStyle/timeStyle cannot be combined with timeZoneName, so spell out the fields.
const dateTime = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  timeZoneName: 'short',
})

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTime.format(new Date(iso)) : '—'
}

const dateOnly = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  timeZone: 'UTC',
})

/** Calendar dates (DOB, date of service) carry no time zone; format them as-is. */
export function formatDate(isoDate: string | null | undefined): string {
  return isoDate ? dateOnly.format(new Date(`${isoDate}T00:00:00Z`)) : '—'
}

export function formatNumber(n: number): string {
  return n.toLocaleString()
}
