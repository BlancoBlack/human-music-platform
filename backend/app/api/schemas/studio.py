from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ReleaseArtistOut(BaseModel):
    id: int
    name: str


class ReleaseBaseOut(BaseModel):
    id: int
    title: str
    cover_url: str | None
    artist: ReleaseArtistOut
    type: Literal["single", "ep", "album"]
    created_at: str | None
    split_version: int
    track_count: int
    genres: list[str]
    moods: list[str]
    location: str | None


class SongFeaturedArtistOut(BaseModel):
    artist_id: int
    artist_name: str


class SongCreditOut(BaseModel):
    name: str
    role: str


class SongOut(BaseModel):
    id: int
    title: str
    primary_artist_id: int
    featured_artists: list[SongFeaturedArtistOut]
    credits: list[SongCreditOut]


class SplitOut(BaseModel):
    artist_id: int
    artist_name: str
    share: float


class ParticipantOut(BaseModel):
    artist_id: int
    artist_name: str
    role: Literal["primary", "collaborator", "featured"]
    status: Literal["pending", "accepted", "rejected"]
    approval_type: Literal["split", "feature", "none"]
    requires_approval: bool
    blocking: bool
    is_actionable_for_user: bool
    has_feature_context: bool
    rejection_reason: str | None
    approved_at: str | None


class PendingSummaryOut(BaseModel):
    split: int
    feature: int


class PendingItemOut(BaseModel):
    release: ReleaseBaseOut
    approval_status: Literal["draft", "pending_approvals", "ready"]
    songs: list[SongOut]
    splits: list[SplitOut]
    participants: list[ParticipantOut]
    pending_summary: PendingSummaryOut


PendingApprovalsResponse = list[PendingItemOut]


class PendingListReleaseOut(BaseModel):
    id: int
    title: str
    cover_url: str | None
    artist: ReleaseArtistOut
    type: Literal["single", "ep", "album"]
    created_at: str | None
    track_count: int
    split_version: int


class PendingListParticipantOut(BaseModel):
    artist_id: int
    artist_name: str
    role: Literal["primary", "collaborator", "featured"]
    status: Literal["pending", "accepted", "rejected"]
    approval_type: Literal["split", "feature", "none"]
    blocking: bool
    is_actionable_for_user: bool


class PendingListItemOut(BaseModel):
    release: PendingListReleaseOut
    approval_status: Literal["draft", "pending_approvals", "ready"]
    pending_summary: PendingSummaryOut
    participants: list[PendingListParticipantOut]


PendingApprovalsListResponse = list[PendingListItemOut]


class ReleaseDetailUserContextOut(BaseModel):
    owned_artist_ids: list[int]
    pending_actions_count: int


class ReleaseDetailReleaseOut(ReleaseBaseOut):
    approval_status: Literal["draft", "pending_approvals", "ready"]


class ReleaseDetailResponse(BaseModel):
    release: ReleaseDetailReleaseOut
    user_context: ReleaseDetailUserContextOut
    songs: list[SongOut]
    splits: list[SplitOut]
    participants: list[ParticipantOut]
    pending_summary: PendingSummaryOut


class ApprovalActionUpdatedParticipantOut(BaseModel):
    artist_id: int
    role: Literal["primary", "collaborator", "featured"]
    approval_type: Literal["split", "feature", "none"]
    blocking: bool
    status: Literal["pending", "accepted", "rejected"]
    rejection_reason: str | None
    approved_at: str | None


class ApprovalActionResponse(BaseModel):
    status: Literal["accepted", "rejected"]
    updated_participant: ApprovalActionUpdatedParticipantOut
    release_approval_status: Literal["draft", "pending_approvals", "ready"] | None
