import pytest

from app.services.csv_parser import (
    EXPECTED_COLUMNS,
    HeaderError,
    parse_csv,
    performance_year_from_source,
)

HEADER = ",".join(EXPECTED_COLUMNS)
VALID = (
    "MEM001,W1,John Smith,3/15/1945,Aetna,Palm Medical Group,Dr. Garcia,E11.9,"
    "Type 2 diabetes,37,Diabetes,HCC Recapture,MAO-004 PY2025,6/15/2024,aetna_mao4_202501.csv"
)


@pytest.mark.parametrize(
    ("source_file", "year"),
    [
        ("aetna_mao4_202501.csv", 2025),
        ("chart_audit_202503.csv", 2025),
        ("careplus_mao4_202401.csv", 2024),
        ("payer_PY2024_extract_202501.csv", 2024),  # explicit PY token wins over file stamp
        ("gaps_202412_to_202501.csv", None),  # two different years: ambiguous
        ("gaps_latest.csv", None),
    ],
)
def test_performance_year_comes_from_source_file_not_upload_date(source_file, year):
    assert performance_year_from_source(source_file) == year


def test_header_is_case_insensitive_but_all_columns_required():
    text = HEADER.upper().replace("SOURCE_FILE", "Source File") + "\n" + VALID
    assert len(parse_csv(text).rows) == 1

    with pytest.raises(HeaderError) as exc:
        parse_csv(HEADER.replace(",hcc_code", "").replace(",source_file", "") + "\n")
    assert exc.value.missing == ["hcc_code", "source_file"]


def test_row_level_validation_keeps_good_rows_and_reports_bad_ones():
    bad_date = VALID.replace("3/15/1945", "1945/15/03")
    no_member = VALID.replace("MEM001", "")
    no_year = VALID.replace("aetna_mao4_202501.csv", "aetna_latest.csv")
    result = parse_csv("\n".join([HEADER, VALID, bad_date, no_member, no_year]))

    assert [r.row_number for r in result.rows] == [2]
    assert {(e.row, e.field) for e in result.errors} == {
        (3, "date_of_birth"),
        (4, "member_id"),
        (5, "source_file"),
    }


def test_quoted_commas_optional_nulls_and_code_normalization():
    row = VALID.replace("MAO-004 PY2025", '"Suspect COPD - prior year dx, no 2025 claim"')
    row = row.replace(",37,Diabetes,", ",,Non-HCC,").replace("6/15/2024", "")
    parsed = parse_csv("\ufeff" + HEADER + "\n" + row).rows[0]

    assert parsed.evidence == "Suspect COPD - prior year dx, no 2025 claim"
    assert parsed.hcc_code is None and parsed.hcc_description == "Non-HCC"
    assert parsed.last_dos is None
    assert parsed.icd10_code == "E119"


def test_fingerprint_ignores_formatting_noise_but_not_content():
    a = parse_csv(HEADER + "\n" + VALID).rows[0]
    b = parse_csv(HEADER + "\n" + VALID.replace("Dr. Garcia", "  dr.  GARCIA ")).rows[0]
    c = parse_csv(HEADER + "\n" + VALID.replace("MAO-004 PY2025", "Different evidence")).rows[0]
    assert a.fingerprint == b.fingerprint
    assert a.fingerprint != c.fingerprint
