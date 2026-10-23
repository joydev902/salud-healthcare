import type { ProviderRef } from '../auth/api'

export default function ProviderPicker({
  providers,
  selected,
  onChange,
}: {
  providers: ProviderRef[]
  selected: Set<number>
  onChange: (next: Set<number>) => void
}) {
  const groups = new Map<string, ProviderRef[]>()
  for (const p of providers) groups.set(p.group_name, [...(groups.get(p.group_name) ?? []), p])

  const toggle = (id: number) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onChange(next)
  }

  return (
    <fieldset className="provider-picker">
      <legend>
        Assigned providers <span className="muted">({selected.size} selected)</span>
      </legend>
      {groups.size === 0 ? (
        <p className="muted">
          No providers yet. Import a CSV and the names in that file show up here.
        </p>
      ) : null}
      {[...groups].map(([group, members]) => (
        <div key={group}>
          <div className="muted group-name">{group}</div>
          {members.map((p) => (
            <label key={p.id} className="checkbox">
              <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggle(p.id)} />
              {p.name}
            </label>
          ))}
        </div>
      ))}
    </fieldset>
  )
}
