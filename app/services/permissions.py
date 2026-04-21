from __future__ import annotations

from app.enums import Role

MANAGER_ROLES = {Role.SUPERVISOR, Role.MANAGER}
APPROVER_ROLES = {Role.CLIENT, Role.MANAGER}
REVIEWER_ROLES = {Role.CLIENT, Role.SUPERVISOR, Role.MANAGER}


def has_manager_access(role: Role | None) -> bool:
    return role in MANAGER_ROLES


def can_review_drafts(role: Role | None) -> bool:
    return role in REVIEWER_ROLES


def can_final_approve(role: Role | None) -> bool:
    return role in APPROVER_ROLES
