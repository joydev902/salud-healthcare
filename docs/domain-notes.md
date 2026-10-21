# Domain notes — sample data analysis

Source: `sample_data/sample_mra_data.csv` (128 rows, 15 columns).

## Columns

`member_id, policy_number, member_name, date_of_birth, payer_name, provider_group,
provider_name, icd_10, icd_10_description, hcc_code, hcc_description, initiative,
evidence, last_dos, source_file`

## Data mess observed (and what the model must do about it)

| Issue | Example | Handling |
|---|---|---|
| Dual-payer members | MEM015: `CP861206611` (CarePlus) and `W628146752` (Aetna); MEM020: `DH123657456` (Devoted) and `CP617653535` (CarePlus) | `members` keyed on `member_id`; `member_policies` holds one row per (member, payer, policy_number) |
| Conflicting ICD→HCC mapping | `I2510` → HCC 222 (Ischemic Heart Disease) in most files, → HCC 226 (Heart Failure) in MEM015/MEM020 secondary-coverage rows | Keep the HCC exactly as reported on each source row; flag conflicts rather than silently picking one |
| Multi-source duplicates | MEM001 `E119` appears in `aetna_mao4_202501` (Recapture), `aetna_hcc_gaps_202501` (Gap), and `aetna_mao4_202401` (PY2024) | One **opportunity** per (member, ICD-10, payment year); each file row becomes an **evidence** record linked to it |
| Year-over-year rollover | 12 source files across PY2024 (`*_202401`) and PY2025 (`*_2025xx`) | Derive payment year from the source; conditions in PY2024 with no PY2025 row = drop-off candidates |
| Non-HCC rows | `hcc_code` empty, `hcc_description = "Non-HCC"` (e.g. E785, I10, E876, G4700) | Nullable HCC; filterable |
| Null `last_dos` | All HCC Gap / Screenings rows | Nullable date |
| Quoted fields with commas | `"Suspect COPD - prior year dx, no 2025 claim"` | Standard CSV parser (`csv` module), never naive split |
| Missing description | MEM032 `E785` has empty `icd_10_description` | Only key fields are required; descriptions optional |
| Date format | `M/D/YYYY` (e.g. `3/15/1945`) | Parse explicitly; reject invalid with a row-level error |
| Provider hierarchy | 3 groups (Palm Medical Group, Sunshine Health Center, Coastal Primary Care); providers Dr. Garcia, Dr. Thompson, Dr. Patel, Dr. Nguyen | `provider_group` → `provider`; coder scoping maps users to providers |

Initiatives: `HCC Recapture`, `HCC Gap`, `Screenings`, `Audit`.
Payers: `Aetna`, `Devoted`, `CarePlus`.

## Ingestion decisions (implemented)

- **Performance year** comes from `source_file`, never the upload date: an explicit
  `PY20xx` token wins; otherwise a single `_YYYYMM` stamp (e.g. `aetna_mao4_202501.csv` →
  2025). No year, or two different years, rejects the row. A `PY20xx` in `evidence` that
  disagrees with the file year is reported as a warning.
- **Opportunity key**: (member, payer, provider, performance year, ICD-10). Other files and
  initiatives for the same key attach as additional `source_records`.
- **Exact duplicates**: SHA-256 fingerprint of all normalized row fields; unique per
  `source_file`. Re-uploading the same file inserts nothing but is still logged.
- **HCC conflicts** are evaluated per member + year + ICD-10 *across payers* (the sample's
  I2510 222-vs-226 conflict is between payers, so a per-opportunity check would miss it).
  Each opportunity keeps the HCC its own sources agree on; every opportunity in a
  conflicting group gets `hcc_conflict = true`.
- **Policy ownership**: a (payer, policy_number) belongs to one member. A row that maps an
  existing policy to a different member is rejected with a row-level error.
- **Member demographics** are not overwritten by later files; differences are warnings.
- **Unknown payers/providers** are created on import. New providers have no coder
  assignments, so their records stay invisible to coders until an Admin assigns them.

Sample import result: 128 rows → 128 evidence rows, 118 opportunities (10 multi-source),
32 members, 34 policies (MEM015 and MEM020 dual-payer), 4 conflict-flagged opportunities
(I2510 for MEM015 and MEM020), 14 PY2024 opportunities; re-import → 128 duplicates, 0 new.

## Implemented core entities

- `users` (email, Argon2 hash, role `ADMIN` \| `CODER`, `is_active`), `user_provider_assignments`
- `payers`, `provider_groups`, `providers`
- `members`, `member_policies` (identity resolution; one policy per payer)
- `upload_batches` (filename, uploader, timestamps, counts, JSONB error summary)
- `opportunities` (member, payer, provider, year, ICD-10, current disposition, version)
- `source_records` (one per imported CSV row: initiative, evidence, last_dos, fingerprint)
- `disposition_history` (append-only: previous → new status, note, actor, versions)

Dispositions: `OPEN` (initial, not user-selectable) → `CONFIRMED` \| `DENIED` \|
`PENDING_CHART` \| `REFERRED_TO_PROVIDER`. Open-count = not yet Confirmed or Denied.
