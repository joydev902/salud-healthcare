import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models import Disposition
from app.schemas.auth import ProviderRef


class PayerRef(BaseModel):
    id: int
    name: str


class QueueMember(BaseModel):
    member_id: uuid.UUID
    external_member_id: str
    member_name: str
    date_of_birth: date | None
    # Both counts are computed over the opportunities that match every active filter.
    matched_opportunity_count: int
    open_opportunity_count: int
    providers: list[str]
    payers: list[str]


class MemberPage(BaseModel):
    items: list[QueueMember]
    next_cursor: str | None
    has_more: bool


class MemberPolicyOut(BaseModel):
    payer_name: str
    policy_number: str


class MemberDetail(BaseModel):
    id: uuid.UUID
    external_member_id: str
    member_name: str
    date_of_birth: date | None
    policies: list[MemberPolicyOut]
    providers: list[ProviderRef]
    total_opportunity_count: int
    open_opportunity_count: int


class MemberRef(BaseModel):
    id: uuid.UUID
    external_member_id: str
    member_name: str
    date_of_birth: date | None


class OpportunitySummary(BaseModel):
    id: uuid.UUID
    performance_year: int
    icd10_code: str
    icd10_description: str | None
    hcc_code: str | None
    hcc_description: str | None
    hcc_conflict: bool
    payer: PayerRef
    provider: ProviderRef
    current_disposition: Disposition
    disposition_version: int
    last_disposition_at: datetime | None
    initiatives: list[str]
    source_files: list[str]
    source_count: int
    last_dos: date | None


class SourceEvidence(BaseModel):
    id: int
    source_file: str
    source_row_number: int
    policy_number: str
    initiative: str
    evidence: str | None
    last_dos: date | None
    reported_hcc_code: str | None
    reported_hcc_description: str | None
    imported_at: datetime


class HccCandidate(BaseModel):
    """Another payer's HCC assertion for the same member, year and diagnosis."""

    opportunity_id: uuid.UUID
    payer_name: str
    hcc_code: str | None
    hcc_description: str | None


class OpportunityDetail(OpportunitySummary):
    member: MemberRef
    current_note: str | None
    last_disposition_by_email: str | None
    sources: list[SourceEvidence]
    hcc_candidates: list[HccCandidate]
