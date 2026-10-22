export type Disposition = 'OPEN' | 'CONFIRMED' | 'DENIED' | 'PENDING_CHART' | 'REFERRED_TO_PROVIDER'

export const DISPOSITION_LABEL: Record<Disposition, string> = {
  OPEN: 'Open',
  PENDING_CHART: 'Pending chart',
  REFERRED_TO_PROVIDER: 'Referred to provider',
  CONFIRMED: 'Confirmed',
  DENIED: 'Denied',
}

export const DISPOSITIONS = Object.keys(DISPOSITION_LABEL) as Disposition[]

/** The four outcomes a coder can choose; OPEN only means "not reviewed yet". */
export const SELECTABLE_DISPOSITIONS: Disposition[] = [
  'CONFIRMED',
  'DENIED',
  'PENDING_CHART',
  'REFERRED_TO_PROVIDER',
]

export const MIN_JUSTIFICATION_LENGTH = 10

/** Not yet Confirmed or Denied: still work for a coder. Mirrors the backend definition. */
export const ACTIVE_DISPOSITIONS: Disposition[] = ['OPEN', 'PENDING_CHART', 'REFERRED_TO_PROVIDER']
