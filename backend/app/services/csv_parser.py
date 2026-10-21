"""Pure CSV parsing/validation for MRA opportunity files (no database access).

Splits a file into validated `ParsedRow`s and row-level `RowIssue`s so that one bad row
never blocks the rest of the file, while a bad header rejects the whole file up front.
"""

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.services.normalize import clean, normalize_code, normalize_name

EXPECTED_COLUMNS: tuple[str, ...] = (
    "member_id",
    "policy_number",
    "member_name",
    "date_of_birth",
    "payer_name",
    "provider_group",
    "provider_name",
    "icd_10",
    "icd_10_description",
    "hcc_code",
    "hcc_description",
    "initiative",
    "evidence",
    "last_dos",
    "source_file",
)
REQUIRED_VALUES: tuple[str, ...] = (
    "member_id",
    "policy_number",
    "member_name",
    "payer_name",
    "provider_group",
    "provider_name",
    "icd_10",
    "initiative",
    "source_file",
)
MAX_LENGTHS: dict[str, int] = {
    "member_id": 64,
    "policy_number": 64,
    "member_name": 200,
    "payer_name": 200,
    "provider_group": 200,
    "provider_name": 200,
    "icd_10": 16,
    "icd_10_description": 500,
    "hcc_code": 16,
    "hcc_description": 500,
    "initiative": 64,
    "evidence": 4000,
    "source_file": 255,
}
KNOWN_INITIATIVES = ("HCC Recapture", "HCC Gap", "Screenings", "Audit")
_INITIATIVE_BY_KEY = {normalize_name(i): i for i in KNOWN_INITIATIVES}

_PY_TOKEN = re.compile(r"PY[\s_-]?(20\d{2})", re.IGNORECASE)
_DATE_STAMP = re.compile(r"(?<!\d)(20\d{2})(?:0[1-9]|1[0-2])(?!\d)")
_ICD10 = re.compile(r"^[A-Z][0-9][0-9A-Z]{1,5}$")
_DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")


class HeaderError(Exception):
    def __init__(self, missing: list[str]) -> None:
        super().__init__(f"Missing required columns: {', '.join(missing)}")
        self.missing = missing


@dataclass(frozen=True)
class RowIssue:
    row: int
    field: str | None
    reason: str


@dataclass
class ParsedRow:
    row_number: int
    member_id: str
    policy_number: str
    member_name: str
    date_of_birth: date | None
    payer_name: str
    provider_group: str
    provider_name: str
    icd10_code: str
    icd10_description: str | None
    hcc_code: str | None
    hcc_description: str | None
    initiative: str
    evidence: str | None
    last_dos: date | None
    source_file: str
    performance_year: int
    raw: dict[str, str]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        self.fingerprint = row_fingerprint(self)


@dataclass
class ParseResult:
    rows: list[ParsedRow]
    errors: list[RowIssue]
    warnings: list[RowIssue]
    total_rows: int
    extra_columns: list[str]


def decode_csv_bytes(content: bytes) -> str:
    """UTF-8 with optional BOM. Raises UnicodeDecodeError for anything else."""
    return content.decode("utf-8-sig")


def performance_year_from_source(source_file: str) -> int | None:
    """Explicit PY20xx token wins; else a single unambiguous YYYYMM stamp; else None."""
    explicit = {int(y) for y in _PY_TOKEN.findall(source_file)}
    if explicit:
        return explicit.pop() if len(explicit) == 1 else None
    stamps = {int(y) for y in _DATE_STAMP.findall(source_file)}
    return stamps.pop() if len(stamps) == 1 else None


def parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(value)


def row_fingerprint(row: ParsedRow) -> str:
    """Stable hash of the normalized business content (not row number / upload)."""
    parts = [
        row.member_id,
        row.policy_number,
        normalize_name(row.member_name),
        row.date_of_birth.isoformat() if row.date_of_birth else "",
        normalize_name(row.payer_name),
        normalize_name(row.provider_group),
        normalize_name(row.provider_name),
        row.icd10_code,
        row.icd10_description or "",
        row.hcc_code or "",
        row.hcc_description or "",
        normalize_name(row.initiative),
        row.evidence or "",
        row.last_dos.isoformat() if row.last_dos else "",
        row.source_file.casefold(),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _normalize_header(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def parse_csv(text: str) -> ParseResult:
    reader = csv.reader(io.StringIO(text.removeprefix("\ufeff"), newline=""))
    try:
        header = [_normalize_header(h) for h in next(reader)]
    except StopIteration:
        raise HeaderError(list(EXPECTED_COLUMNS)) from None

    missing = [c for c in EXPECTED_COLUMNS if c not in header]
    if missing:
        raise HeaderError(missing)
    index = {name: header.index(name) for name in EXPECTED_COLUMNS}
    extra = [h for h in header if h and h not in EXPECTED_COLUMNS]

    rows: list[ParsedRow] = []
    errors: list[RowIssue] = []
    warnings: list[RowIssue] = []
    total = 0
    for row_number, values in enumerate(reader, start=2):
        if not any(v.strip() for v in values):
            continue
        total += 1
        if len(values) < len(header):
            values = values + [""] * (len(header) - len(values))
        raw = {name: values[i] for name, i in index.items()}
        parsed = _parse_row(row_number, raw, errors, warnings)
        if parsed is not None:
            rows.append(parsed)

    return ParseResult(rows, errors, warnings, total, extra)


def _parse_row(
    row_number: int, raw: dict[str, str], errors: list[RowIssue], warnings: list[RowIssue]
) -> ParsedRow | None:
    values = {k: clean(v) for k, v in raw.items()}
    row_errors: list[RowIssue] = []

    for name in REQUIRED_VALUES:
        if values[name] is None:
            row_errors.append(RowIssue(row_number, name, "Missing required value"))
    for name, limit in MAX_LENGTHS.items():
        if values[name] is not None and len(values[name]) > limit:
            row_errors.append(RowIssue(row_number, name, f"Longer than {limit} characters"))

    dates: dict[str, date | None] = {}
    for name in ("date_of_birth", "last_dos"):
        try:
            dates[name] = parse_date(values[name])
        except ValueError:
            dates[name] = None
            row_errors.append(
                RowIssue(row_number, name, "Invalid date (expected M/D/YYYY or YYYY-MM-DD)")
            )

    icd10 = normalize_code(values["icd_10"])
    if icd10 is not None and not _ICD10.match(icd10):
        row_errors.append(RowIssue(row_number, "icd_10", "Not a valid ICD-10-CM code"))

    year = None
    if values["source_file"] is not None:
        year = performance_year_from_source(values["source_file"])
        if year is None:
            row_errors.append(
                RowIssue(row_number, "source_file", "Cannot determine performance year")
            )

    if row_errors:
        errors.extend(row_errors)
        return None

    evidence_years = {int(y) for y in _PY_TOKEN.findall(values["evidence"] or "")}
    if evidence_years and evidence_years != {year}:
        warnings.append(
            RowIssue(
                row_number,
                "evidence",
                f"Evidence mentions PY{'/'.join(map(str, sorted(evidence_years)))} "
                f"but source file indicates PY{year}",
            )
        )

    initiative = values["initiative"]
    return ParsedRow(
        row_number=row_number,
        member_id=values["member_id"].upper(),
        policy_number=values["policy_number"].upper(),
        member_name=values["member_name"],
        date_of_birth=dates["date_of_birth"],
        payer_name=values["payer_name"],
        provider_group=values["provider_group"],
        provider_name=values["provider_name"],
        icd10_code=icd10,
        icd10_description=values["icd_10_description"],
        hcc_code=normalize_code(values["hcc_code"]),
        hcc_description=values["hcc_description"],
        initiative=_INITIATIVE_BY_KEY.get(normalize_name(initiative), initiative),
        evidence=values["evidence"],
        last_dos=dates["last_dos"],
        source_file=values["source_file"],
        performance_year=year,
        raw=raw,
    )
