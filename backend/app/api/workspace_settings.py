"""Workspace settings (LEGAL-1): the installation-wide values an admin sets
from the screen.

Workspace settings and editable registration-email copy are available only
to super admins. The public route exposes only the privacy notice URL.

  GET /api/workspace/public
      No auth. What the public registration form needs and nothing more:
      today, the organisation's privacy notice URL, or null.

  GET/PUT /api/admin/workspace/settings
      Super-admin privacy-notice settings.

  GET/PUT /api/admin/workspace/email-templates
      Super-admin email-copy settings. These are installation-wide and
      validated against the supported languages, fields, placeholders,
      and maximum value length.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User, UserRole
from app.services.workspace_settings_service import (
    InvalidEmailTemplates,
    InvalidPrivacyNoticeUrl,
    get_email_templates,
    get_privacy_notice_url,
    set_email_templates,
    set_privacy_notice_url,
)

router = APIRouter(tags=["workspace_settings"])


class WorkspacePublicResponse(BaseModel):
    privacy_notice_url: str | None = None


class WorkspaceSettingsResponse(BaseModel):
    privacy_notice_url: str | None = None


class WorkspaceSettingsUpdate(BaseModel):
    # Optional so a client that sends only the fields it changed keeps
    # working when a second setting arrives. Today there is one.
    privacy_notice_url: str | None = None


class EmailTemplatesResponse(BaseModel):
    templates: dict[str, dict[str, str]]


class EmailTemplatesUpdate(BaseModel):
    templates: dict[str, dict[str, str]]


def _require_super_admin(current_user: User) -> None:
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"key": "errors.workspace.super_admin_only"},
        )


@router.get("/api/workspace/public", response_model=WorkspacePublicResponse)
async def get_workspace_public(db: AsyncSession = Depends(get_db)) -> WorkspacePublicResponse:
    """What the registration form shows a stranger. No auth."""
    return WorkspacePublicResponse(privacy_notice_url=await get_privacy_notice_url(db))


@router.get("/api/admin/workspace/settings", response_model=WorkspaceSettingsResponse)
async def get_workspace_settings_admin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkspaceSettingsResponse:
    _require_super_admin(current_user)
    return WorkspaceSettingsResponse(privacy_notice_url=await get_privacy_notice_url(db))


@router.put("/api/admin/workspace/settings", response_model=WorkspaceSettingsResponse)
async def update_workspace_settings(
    body: WorkspaceSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkspaceSettingsResponse:
    _require_super_admin(current_user)
    try:
        row = await set_privacy_notice_url(db, body.privacy_notice_url)
    except InvalidPrivacyNoticeUrl:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "key": "errors.workspace.privacy_url_invalid",
                "fields": {"privacy_notice_url": "errors.workspace.privacy_url_invalid"},
            },
        )
    await db.commit()
    return WorkspaceSettingsResponse(privacy_notice_url=row.privacy_notice_url)


@router.get(
    "/api/admin/workspace/email-templates",
    response_model=EmailTemplatesResponse,
)
async def get_workspace_email_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmailTemplatesResponse:
    _require_super_admin(current_user)
    return EmailTemplatesResponse(templates=await get_email_templates(db))


@router.put(
    "/api/admin/workspace/email-templates",
    response_model=EmailTemplatesResponse,
)
async def update_workspace_email_templates(
    body: EmailTemplatesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EmailTemplatesResponse:
    _require_super_admin(current_user)
    try:
        await set_email_templates(db, body.templates)
    except InvalidEmailTemplates as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "key": "errors.workspace.email_templates_invalid",
                "reason": str(exc),
            },
        ) from exc
    await db.commit()
    return EmailTemplatesResponse(templates=await get_email_templates(db))
