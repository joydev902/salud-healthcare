import { DISPOSITION_LABEL, type Disposition } from './dispositions'

export default function DispositionBadge({ value }: { value: Disposition }) {
  return (
    <span className={`badge disposition-${value.toLowerCase()}`}>{DISPOSITION_LABEL[value]}</span>
  )
}
