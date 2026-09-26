"""Centralized RBAC permissions for route protection."""

from __future__ import annotations

from enum import Enum

from app.models.user import UserRole


class Permission(str, Enum):
    DOCUMENTS_READ = "documents:read"
    DOCUMENTS_WRITE = "documents:write"
    DOCUMENTS_PROCESS = "documents:process"
    DOCUMENTS_EXTRACT = "documents:extract"
    DOCUMENTS_INDEX = "documents:index"
    PROCESSING_JOBS_READ = "processing_jobs:read"
    PROCESSING_JOBS_WRITE = "processing_jobs:write"
    VALIDATIONS_READ = "validations:read"
    VALIDATIONS_WRITE = "validations:write"
    RELATIONSHIPS_READ = "relationships:read"
    RELATIONSHIPS_WRITE = "relationships:write"
    REVIEWS_READ = "reviews:read"
    REVIEWS_WRITE = "reviews:write"
    DUPLICATES_READ = "duplicates:read"
    DUPLICATES_CHECK = "duplicates:check"
    DUPLICATES_RESOLVE = "duplicates:resolve"
    VENDORS_READ = "vendors:read"
    VENDORS_WRITE = "vendors:write"
    ANOMALIES_READ = "anomalies:read"
    ANOMALIES_SCORE = "anomalies:score"
    ANOMALIES_TRAIN = "anomalies:train"
    CLASSIFICATION_READ = "classification:read"
    CLASSIFICATION_TRAIN = "classification:train"
    WORKFLOWS_READ = "workflows:read"
    WORKFLOWS_TRIGGER = "workflows:trigger"
    RAG_USE = "rag:use"
    SQL_USE = "sql:use"
    INVESTIGATION_USE = "investigation:use"
    AGENT_USE = "agent:use"
    ANALYTICS_READ = "analytics:read"
    USERS_MANAGE = "users:manage"


_VIEWER: set[Permission] = {
    Permission.DOCUMENTS_READ,
    Permission.PROCESSING_JOBS_READ,
    Permission.VALIDATIONS_READ,
    Permission.RELATIONSHIPS_READ,
    Permission.REVIEWS_READ,
    Permission.DUPLICATES_READ,
    Permission.VENDORS_READ,
    Permission.ANOMALIES_READ,
    Permission.CLASSIFICATION_READ,
    Permission.WORKFLOWS_READ,
    Permission.RAG_USE,
    Permission.SQL_USE,
    Permission.INVESTIGATION_USE,
    Permission.AGENT_USE,
    Permission.ANALYTICS_READ,
}

_OPERATOR: set[Permission] = _VIEWER | {
    Permission.DOCUMENTS_WRITE,
    Permission.DOCUMENTS_PROCESS,
    Permission.DOCUMENTS_EXTRACT,
    Permission.DOCUMENTS_INDEX,
    Permission.PROCESSING_JOBS_WRITE,
    Permission.VALIDATIONS_WRITE,
    Permission.RELATIONSHIPS_WRITE,
    Permission.DUPLICATES_CHECK,
    Permission.VENDORS_WRITE,
    Permission.ANOMALIES_SCORE,
    Permission.WORKFLOWS_TRIGGER,
}

_REVIEWER: set[Permission] = _VIEWER | {
    Permission.REVIEWS_WRITE,
    Permission.DUPLICATES_RESOLVE,
    Permission.VALIDATIONS_WRITE,
}

_ADMIN: set[Permission] = set(Permission)


ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    UserRole.VIEWER.value: _VIEWER,
    UserRole.OPERATOR.value: _OPERATOR,
    UserRole.REVIEWER.value: _REVIEWER,
    UserRole.ADMIN.value: _ADMIN,
}


def permissions_for_role(role: str) -> set[Permission]:
    return set(ROLE_PERMISSIONS.get(role, set()))


def role_has_permission(role: str, permission: Permission) -> bool:
    return permission in permissions_for_role(role)
