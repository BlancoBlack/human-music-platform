from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.user_profile import UserProfile
from app.services.onboarding_state_service import (
    COMPLETED,
    DISCOVERY_STARTED,
    PREFERENCES_SET,
    REGISTERED,
    advance_onboarding_state,
    is_state_at_least,
    validate_onboarding_state,
)

router = APIRouter()


class OnboardingPreferencesRequest(BaseModel):
    genres: list[str] = Field(default_factory=list)
    artists: list[str] = Field(default_factory=list)

    @field_validator("genres")
    @classmethod
    def validate_genres(cls, v: list[str]) -> list[str]:
        cleaned = [x.strip() for x in v if x and x.strip()]
        if len(cleaned) > 5:
            raise ValueError("genres supports at most 5 values")
        return cleaned

    @field_validator("artists")
    @classmethod
    def validate_artists(cls, v: list[str]) -> list[str]:
        return [x.strip() for x in v if x and x.strip()][:20]


class OnboardingStateResponse(BaseModel):
    onboarding_completed: bool
    onboarding_step: str | None = None


@router.post("/preferences", response_model=OnboardingStateResponse)
def post_onboarding_preferences(
    body: OnboardingPreferencesRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnboardingStateResponse:
    try:
        current = validate_onboarding_state(user.onboarding_step)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid onboarding state") from None
    if current == REGISTERED:
        user.onboarding_step = advance_onboarding_state(current, PREFERENCES_SET)
    elif not is_state_at_least(current, PREFERENCES_SET):
        raise HTTPException(status_code=400, detail="Invalid onboarding transition")
    profile = db.query(UserProfile).filter(UserProfile.user_id == int(user.id)).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="User profile not found")
    profile.preferred_genres = body.genres
    profile.preferred_artists = body.artists
    db.commit()
    return OnboardingStateResponse(
        onboarding_completed=bool(user.onboarding_completed),
        onboarding_step=user.onboarding_step,
    )


@router.post("/complete", response_model=OnboardingStateResponse)
def post_onboarding_complete(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnboardingStateResponse:
    try:
        current = validate_onboarding_state(user.onboarding_step)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid onboarding state") from None
    if current == DISCOVERY_STARTED:
        user.onboarding_step = advance_onboarding_state(current, COMPLETED)
    elif current != COMPLETED:
        raise HTTPException(status_code=400, detail="Invalid onboarding transition")
    user.onboarding_completed = user.onboarding_step == COMPLETED
    db.commit()
    return OnboardingStateResponse(
        onboarding_completed=bool(user.onboarding_completed),
        onboarding_step=user.onboarding_step,
    )
