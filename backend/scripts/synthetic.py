"""Deterministic synthetic MRA files for load testing. Every value is invented; no PHI.

Shape mirrors the sample file: one file per payer x initiative x performance year, members
with one or two payer policies, and ~15% of diagnoses corroborated by a second initiative
(which ingestion folds into the same opportunity).
"""

import csv
import io
import random
from dataclasses import dataclass
from datetime import date, timedelta

from app.services.csv_parser import EXPECTED_COLUMNS

PAYERS = ("Aetna", "CarePlus", "Devoted", "Humana", "Wellcare")
PROVIDER_GROUPS = (
    "Palm Medical Group",
    "Sunshine Health Center",
    "Coastal Primary Care",
    "Bayview Family Medicine",
    "Gulf Coast Physicians",
    "Everglades Health Partners",
    "Harbor Internal Medicine",
    "Keystone Senior Care",
)
PROVIDERS_PER_GROUP = 5
SURNAMES = [
    "Garcia",
    "Thompson",
    "Patel",
    "Nguyen",
    "Smith",
    "Johnson",
    "Lee",
    "Brown",
    "Davis",
    "Martinez",
    "Lopez",
    "Wilson",
    "Clark",
    "Lewis",
    "Walker",
    "Hall",
    "Allen",
    "Young",
    "King",
    "Wright",
    "Scott",
    "Green",
    "Baker",
    "Adams",
    "Nelson",
    "Hill",
    "Ramirez",
    "Campbell",
    "Mitchell",
    "Roberts",
    "Carter",
    "Phillips",
    "Evans",
    "Turner",
    "Torres",
    "Parker",
    "Collins",
    "Edwards",
]
FIRST_NAMES = [
    "John",
    "Maria",
    "Robert",
    "Dorothy",
    "James",
    "Helen",
    "William",
    "Patricia",
    "Charles",
    "Susan",
    "Richard",
    "Barbara",
    "Thomas",
    "Margaret",
    "George",
    "Nancy",
    "Kenneth",
    "Linda",
    "Edward",
    "Carol",
    "Frank",
    "Ruth",
    "Donald",
    "Sharon",
    "Albert",
]
# (ICD-10, description, HCC, HCC description); HCC None = non-HCC diagnosis.
DIAGNOSES = (
    ("E119", "Type 2 diabetes mellitus without complications", "37", "Diabetes w/o Complication"),
    ("E1122", "Type 2 diabetes with diabetic CKD", "37", "Diabetes w/o Complication"),
    ("I5022", "Chronic systolic heart failure", "226", "Heart Failure"),
    ("I2510", "Atherosclerotic heart disease", "263", "Atherosclerosis of Arteries"),
    ("J449", "Chronic obstructive pulmonary disease", "280", "COPD"),
    ("N184", "Chronic kidney disease, stage 4", "327", "CKD Stage 4"),
    ("N183", "Chronic kidney disease, stage 3", "328", "CKD Stage 3"),
    ("F329", "Major depressive disorder, single episode", "155", "Major Depression"),
    ("I4891", "Unspecified atrial fibrillation", "238", "Specified Heart Arrhythmias"),
    ("E6601", "Morbid obesity due to excess calories", "48", "Morbid Obesity"),
    ("G629", "Polyneuropathy, unspecified", "75", "Neuropathy"),
    ("M069", "Rheumatoid arthritis, unspecified", "93", "Rheumatoid Arthritis"),
    ("C61", "Malignant neoplasm of prostate", "23", "Prostate Cancer"),
    ("F17210", "Nicotine dependence, cigarettes", None, None),
    ("I10", "Essential hypertension", None, None),
    ("E785", "Hyperlipidemia, unspecified", None, None),
    ("Z1231", "Screening mammogram", None, None),
    ("Z23", "Encounter for immunization", None, None),
)
# (initiative, file slug, weight)
INITIATIVES = (
    ("HCC Recapture", "mao4", 0.45),
    ("HCC Gap", "hcc_gaps", 0.30),
    ("Screenings", "screenings", 0.15),
    ("Audit", "chart_audit", 0.10),
)
YEARS = ((2024, 0.3), (2025, 0.7))


@dataclass(frozen=True)
class _Member:
    member_id: str
    name: str
    dob: date
    provider: tuple[str, str]
    policies: tuple[tuple[str, str], ...]


def _members(rng: random.Random, count: int) -> list[_Member]:
    providers = [
        (group, f"Dr. {rng.choice(SURNAMES)} {chr(65 + g)}{i}")
        for g, group in enumerate(PROVIDER_GROUPS)
        for i in range(PROVIDERS_PER_GROUP)
    ]
    members = []
    for n in range(1, count + 1):
        payers = rng.sample(PAYERS, 2 if rng.random() < 0.1 else 1)
        members.append(
            _Member(
                member_id=f"SYN{n:06d}",
                name=f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}",
                dob=date(1935, 1, 1) + timedelta(days=rng.randrange(365 * 25)),
                provider=rng.choice(providers),
                policies=tuple((p, f"{p[:2].upper()}{n:07d}") for p in payers),
            )
        )
    return members


def generate(rows: int = 200_000, members: int = 25_000, seed: int = 7) -> dict[str, bytes]:
    """Return {filename: csv bytes}; total data rows == `rows`."""
    rng = random.Random(seed)
    people = _members(rng, members)
    names, slugs, weights = zip(*INITIATIVES, strict=True)
    files: dict[str, list[list[str]]] = {}

    emitted = 0
    while emitted < rows:
        m = rng.choice(people)
        payer, policy = rng.choice(m.policies)
        year = rng.choices([y for y, _ in YEARS], [w for _, w in YEARS])[0]
        icd, icd_desc, hcc, hcc_desc = rng.choice(DIAGNOSES)
        picks = {rng.choices(range(len(names)), weights)[0]}
        if rng.random() < 0.15:
            picks.add(rng.choices(range(len(names)), weights)[0])
        for idx in picks:
            if emitted >= rows:
                break
            dos = date(year - 1, 1, 1) + timedelta(days=rng.randrange(700))
            filename = f"{payer.lower()}_{slugs[idx]}_PY{year}.csv"
            files.setdefault(filename, []).append(
                [
                    m.member_id,
                    policy,
                    m.name,
                    f"{m.dob.month}/{m.dob.day}/{m.dob.year}",
                    payer,
                    m.provider[0],
                    m.provider[1],
                    icd,
                    icd_desc,
                    hcc or "",
                    hcc_desc or "",
                    names[idx],
                    f"{names[idx]} evidence #{emitted} - documented {dos.isoformat()}",
                    f"{dos.month}/{dos.day}/{dos.year}" if rng.random() > 0.05 else "",
                    filename,
                ]
            )
            emitted += 1

    out = {}
    for filename, body in sorted(files.items()):
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(EXPECTED_COLUMNS)
        writer.writerows(body)
        out[filename] = buf.getvalue().encode()
    return out
