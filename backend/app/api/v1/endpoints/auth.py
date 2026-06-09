"""Auth and RBAC endpoints: login, profile, sessions, users, roles, and permissions."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import desc, func, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.db.models import (
    ActivityLog,
    LoginHistory,
    Permission,
    Role,
    RolePermission,
    User,
    UserPermission,
    UserRole,
    UserSession,
)
from app.db.session import get_db
from app.schemas.auth import (
    ActivityLogItem,
    ChangePassword,
    ERP_MODULES,
    LoginHistoryItem,
    PermissionItem,
    PreferencesUpdate,
    ProfileUpdate,
    RoleCreate,
    RoleItem,
    RoleUpdate,
    SessionItem,
    Token,
    User as UserSchema,
    UserCreate,
    UserList,
    UserLogin,
    UserUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer(auto_error=False)

SYSTEM_ROLE_PRIORITIES = {
    "developer": 100,
    "admin": 50,
    "user": 10,
}

SYSTEM_ROLE_DESCRIPTIONS = {
    "developer": "Super admin role with full system control",
    "admin": "Administrative role for day-to-day user operations",
    "user": "Default least-privileged role",
}

EXTRA_PERMISSION_MODULES = ["system_settings", "security", "hidden_modules"]
DEVELOPER_USERNAME_DISPLAY = "HeilKnights"
DEVELOPER_USERNAME = DEVELOPER_USERNAME_DISPLAY.lower()

USER_ASSIGNABLE_MODULES = [
    "dashboard",
    "reports",
    "garments",
    "sales",
    "financial",
    "procurement",
    "manufacturing",
]

MODULE_NAME_ALIASES = {
    "overview": "dashboard",
}


def _permission_code(module: str, action: str) -> str:
    return f"{module}:{action}"


DEFAULT_ROLE_PERMISSION_CODES: Dict[str, Set[str]] = {
    "developer": {
        _permission_code(module, action)
        for module in [*ERP_MODULES, *EXTRA_PERMISSION_MODULES]
        for action in ("view", "create", "update", "delete")
    },
    "admin": {
        _permission_code(module, action)
        for module in [*ERP_MODULES]
        for action in ("view", "create", "update", "delete")
    },
    "user": set(),
}


# Helpers

def _normalize_role_name(role: Optional[str]) -> str:
    if not role:
        return "user"
    normalized = role.strip().lower().replace(" ", "_")
    if normalized in {"staff", "manager"}:
        return "user"
    if normalized not in SYSTEM_ROLE_PRIORITIES:
        return "user"
    return normalized


def _normalize_module_name(module: str) -> str:
    normalized = module.strip().lower().replace(" ", "_")
    return MODULE_NAME_ALIASES.get(normalized, normalized)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _parse_device(ua: str) -> str:
    ua_lower = ua.lower()
    browser = "Unknown"
    if "chrome" in ua_lower and "edg" not in ua_lower:
        browser = "Chrome"
    elif "firefox" in ua_lower:
        browser = "Firefox"
    elif "safari" in ua_lower and "chrome" not in ua_lower:
        browser = "Safari"
    elif "edg" in ua_lower:
        browser = "Edge"
    elif "python" in ua_lower:
        browser = "API Client"

    os_name = "Unknown"
    if "windows" in ua_lower:
        os_name = "Windows"
    elif "macintosh" in ua_lower or "mac os" in ua_lower:
        os_name = "macOS"
    elif "linux" in ua_lower:
        os_name = "Linux"
    elif "android" in ua_lower:
        os_name = "Android"
    elif "iphone" in ua_lower or "ipad" in ua_lower:
        os_name = "iOS"

    return f"{browser} on {os_name}"


def _role_by_name(db: Session, role_name: str) -> Optional[Role]:
    normalized = _normalize_role_name(role_name)
    try:
        return db.query(Role).filter(func.lower(Role.name) == normalized).first()
    except SQLAlchemyError:
        return None


def _get_role_priority(db: Session, role_name: str) -> int:
    normalized = _normalize_role_name(role_name)
    role = _role_by_name(db, normalized)
    if role:
        return role.priority
    return SYSTEM_ROLE_PRIORITIES.get(normalized, 10)


def _is_developer_role(db: Session, role_name: str) -> bool:
    normalized = _normalize_role_name(role_name)
    if normalized == "developer":
        return True
    role = _role_by_name(db, normalized)
    return bool(role and role.is_developer)


def _is_heilknights_developer(db: Session, user: User) -> bool:
    return _is_developer_role(db, user.role) and (user.username or "").strip().lower() == DEVELOPER_USERNAME


def _serialize_role(role: Role) -> dict:
    codes = sorted(
        {
            _permission_code(rp.permission.module, rp.permission.action)
            for rp in role.role_permissions
            if rp.permission is not None
        }
    )
    return {
        "id": role.id,
        "name": role.name,
        "priority": role.priority,
        "description": role.description,
        "is_system": role.is_system,
        "is_developer": role.is_developer,
        "permissions": codes,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }


def _get_user_permissions(db: Session, user: User) -> Set[str]:
    role_codes: Set[str] = set()
    user_codes: Set[str] = set()

    try:
        role_rows = (
            db.query(Permission.module, Permission.action)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == user.id, UserRole.is_primary.is_(True))
            .all()
        )
        role_codes = {_permission_code(m, a) for m, a in role_rows}

        user_rows = (
            db.query(Permission.module, Permission.action)
            .join(UserPermission, UserPermission.permission_id == Permission.id)
            .filter(UserPermission.user_id == user.id)
            .all()
        )
        user_codes = {_permission_code(m, a) for m, a in user_rows}
    except SQLAlchemyError:
        pass

    normalized = _normalize_role_name(user.role)
    codes = role_codes | user_codes
    if not codes:
        codes = set(DEFAULT_ROLE_PERMISSION_CODES.get(normalized, set()))

    explicit_modules = set(_get_user_module_access(db, user, explicit_only=True))
    if explicit_modules and not _is_developer_role(db, normalized):
        filtered: Set[str] = set()
        for code in codes:
            if ":" not in code:
                continue
            module, action = code.split(":", 1)
            if action == "view" and module in USER_ASSIGNABLE_MODULES and module not in explicit_modules:
                continue
            filtered.add(code)
        codes = filtered

    return codes


def _get_user_module_access(db: Session, user: User, explicit_only: bool = False) -> List[str]:
    explicit_modules: Set[str] = set()
    try:
        rows = (
            db.query(Permission.module)
            .join(UserPermission, UserPermission.permission_id == Permission.id)
            .filter(UserPermission.user_id == user.id, Permission.action == "view")
            .all()
        )
        explicit_modules = {
            _normalize_module_name(module)
            for (module,) in rows
            if _normalize_module_name(module) in USER_ASSIGNABLE_MODULES
        }
    except SQLAlchemyError:
        explicit_modules = set()

    if explicit_only:
        return [module for module in USER_ASSIGNABLE_MODULES if module in explicit_modules]

    if explicit_modules:
        return [module for module in USER_ASSIGNABLE_MODULES if module in explicit_modules]

    role_name = _normalize_role_name(user.role)
    if _is_developer_role(db, role_name) or role_name == "admin":
        return list(USER_ASSIGNABLE_MODULES)

    return []


def _set_user_module_access(db: Session, user: User, module_access: Optional[List[str]]) -> None:
    if module_access is None:
        return

    normalized_modules = {
        _normalize_module_name(module)
        for module in module_access
        if _normalize_module_name(module) in USER_ASSIGNABLE_MODULES
    }

    permission_rows = (
        db.query(Permission.id, Permission.module)
        .filter(Permission.action == "view", Permission.module.in_(USER_ASSIGNABLE_MODULES))
        .all()
    )
    module_to_perm = {module: perm_id for perm_id, module in permission_rows}
    managed_perm_ids = [perm_id for perm_id, _ in permission_rows]

    if managed_perm_ids:
        db.query(UserPermission).filter(
            UserPermission.user_id == user.id,
            UserPermission.permission_id.in_(managed_perm_ids),
        ).delete(synchronize_session=False)

    for module in sorted(normalized_modules):
        perm_id = module_to_perm.get(module)
        if perm_id is not None:
            db.add(UserPermission(user_id=user.id, permission_id=perm_id))

    db.flush()


def _serialize_user(db: Session, user: User, include_permissions: bool = False) -> dict:
    normalized = _normalize_role_name(user.role)
    payload = {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "role": normalized,
        "role_priority": _get_role_priority(db, normalized),
        "module_access": _get_user_module_access(db, user),
        "is_developer": _is_developer_role(db, normalized),
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "last_login": user.last_login,
        "timezone": user.timezone,
        "language": user.language,
        "email_notifications": user.email_notifications,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "permissions": [],
    }
    if include_permissions:
        payload["permissions"] = sorted(_get_user_permissions(db, user))
    return payload


# Process-level flag: RBAC seeding only needs to run once per process.
# Running it on every /login and /me request caused a 2-3s schema introspection
# (inspect().get_table_names() against the remote DB) on every single call.
_rbac_seeded: bool = False


def _ensure_rbac_schema(db: Session) -> None:
    """Create RBAC tables on-demand when migration chain is not available."""
    try:
        bind = db.get_bind()
        table_names = set(inspect(bind).get_table_names())

        if "roles" not in table_names:
            Role.__table__.create(bind=bind, checkfirst=True)
        if "permissions" not in table_names:
            Permission.__table__.create(bind=bind, checkfirst=True)
        if "role_permissions" not in table_names:
            RolePermission.__table__.create(bind=bind, checkfirst=True)
        if "user_roles" not in table_names:
            UserRole.__table__.create(bind=bind, checkfirst=True)
        if "user_permissions" not in table_names:
            UserPermission.__table__.create(bind=bind, checkfirst=True)

        if bind.dialect.name == "postgresql":
            db.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_users_single_developer
                    ON users (role)
                    WHERE lower(role) = 'developer'
                    """
                )
            )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("RBAC schema ensure skipped: %s", exc)


def _ensure_rbac_seeded(db: Session) -> None:
    """Idempotent role and permission bootstrap for production RBAC.

    Uses a process-level flag so the expensive schema introspection and full
    DB scan only run once per process lifetime, not on every request.
    """
    global _rbac_seeded
    if _rbac_seeded:
        return
    _ensure_rbac_schema(db)
    try:
        modules = [*ERP_MODULES, *EXTRA_PERMISSION_MODULES]

        existing_permissions = {(p.module, p.action): p for p in db.query(Permission).all()}
        for module in modules:
            for action in ("view", "create", "update", "delete"):
                key = (module, action)
                if key not in existing_permissions:
                    db.add(
                        Permission(
                            module=module,
                            action=action,
                            description=f"{action.title()} access for {module.replace('_', ' ').title()}",
                        )
                    )

        db.flush()

        existing_roles = {r.name.lower(): r for r in db.query(Role).all()}
        for name, priority in SYSTEM_ROLE_PRIORITIES.items():
            role = existing_roles.get(name)
            if role is None:
                role = Role(
                    name=name,
                    priority=priority,
                    is_system=True,
                    is_developer=(name == "developer"),
                    description=SYSTEM_ROLE_DESCRIPTIONS.get(name),
                )
                db.add(role)
                existing_roles[name] = role
            else:
                # Keep priorities and flags consistent for system roles
                role.priority = priority
                role.is_system = True
                if name == "developer":
                    role.is_developer = True
                if not role.description:
                    role.description = SYSTEM_ROLE_DESCRIPTIONS.get(name)

        # Keep only the 3 system roles in strict mode.
        obsolete_roles = [
            role for role_name, role in existing_roles.items()
            if role_name not in SYSTEM_ROLE_PRIORITIES
        ]
        for role in obsolete_roles:
            db.query(RolePermission).filter(RolePermission.role_id == role.id).delete(synchronize_session=False)
            db.query(UserRole).filter(UserRole.role_id == role.id).delete(synchronize_session=False)
            db.delete(role)
            existing_roles.pop(role.name.lower(), None)

        db.flush()

        perm_map = {
            _permission_code(p.module, p.action): p
            for p in db.query(Permission).all()
        }

        for role_name, codes in DEFAULT_ROLE_PERMISSION_CODES.items():
            role = existing_roles.get(role_name)
            if not role:
                continue
            has_permissions = db.query(RolePermission).filter(RolePermission.role_id == role.id).count() > 0
            if has_permissions:
                continue
            for code in codes:
                perm = perm_map.get(code)
                if perm is not None:
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id))

        # Normalize legacy role values to the 3-role system.
        for user in db.query(User).all():
            normalized = _normalize_role_name(user.role)
            if user.role != normalized:
                user.role = normalized
            user.is_superuser = normalized in {"developer", "admin"}

        # Developer account guardrails: keep exactly one developer and prioritize HeilKnights.
        heil_user = (
            db.query(User)
            .filter(func.lower(User.username) == DEVELOPER_USERNAME)
            .order_by(User.id.asc())
            .first()
        )
        developer_users = (
            db.query(User)
            .filter(func.lower(User.role) == "developer")
            .order_by(User.id.asc())
            .all()
        )

        chosen_developer: Optional[User] = None
        if heil_user is not None:
            chosen_developer = heil_user
        elif developer_users:
            chosen_developer = developer_users[0]

        if chosen_developer is not None:
            chosen_developer.username = DEVELOPER_USERNAME_DISPLAY
            chosen_developer.role = "developer"
            chosen_developer.is_superuser = True
            for user in developer_users:
                if user.id != chosen_developer.id:
                    user.role = "admin"
                    user.is_superuser = True

        db.commit()
        _rbac_seeded = True
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("RBAC bootstrap skipped: %s", exc)


def _ensure_user_primary_role(db: Session, user: User) -> None:
    normalized = _normalize_role_name(user.role)
    user.role = normalized
    user.is_superuser = normalized in {"developer", "admin"}

    try:
        role = _role_by_name(db, normalized)
        if role is None:
            fallback_name = "admin" if normalized == "developer" else "user"
            role = _role_by_name(db, fallback_name)
            if role is None:
                raise SQLAlchemyError(f"Missing required role '{fallback_name}'")
            user.role = fallback_name
            user.is_superuser = fallback_name in {"developer", "admin"}

        # Single-role system: remove stale links from previous role assignments.
        db.query(UserRole).filter(
            UserRole.user_id == user.id,
            UserRole.role_id != role.id,
        ).delete(synchronize_session=False)

        db.query(UserRole).filter(UserRole.user_id == user.id).update(
            {"is_primary": False},
            synchronize_session=False,
        )

        link = db.query(UserRole).filter(UserRole.user_id == user.id, UserRole.role_id == role.id).first()
        if link is None:
            db.add(UserRole(user_id=user.id, role_id=role.id, is_primary=True))
        else:
            link.is_primary = True

        db.flush()
    except SQLAlchemyError:
        # If RBAC tables are unavailable, keep legacy role flow alive.
        db.rollback()


def _jwt_pair(db: Session, user: User) -> dict:
    normalized = _normalize_role_name(user.role)
    payload = {
        "sub": str(user.id),
        "role": normalized,
        "priority": _get_role_priority(db, normalized),
    }
    return {
        "access_token": create_access_token(data=payload),
        "refresh_token": create_refresh_token(data=payload),
        "token_type": "bearer",
    }


def _log_activity(db: Session, user_id: int, action: str, detail: str = "", ip: str = ""):
    try:
        db.add(ActivityLog(user_id=user_id, action=action, detail=detail, ip_address=ip))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Activity log write failed for user_id=%s action=%s: %s", user_id, action, exc)


def _create_session(db: Session, user_id: int, refresh_token: str, ip: str, ua: str):
    token_hash = _hash_token(refresh_token)
    expires = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    try:
        db.add(
            UserSession(
                user_id=user_id,
                refresh_token_hash=token_hash,
                ip_address=ip,
                user_agent=ua[:512],
                device_label=_parse_device(ua),
                is_current=False,
                created_at=datetime.utcnow(),
                expires_at=expires,
            )
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Session persistence failed for user_id=%s: %s", user_id, exc)


def _verify_user_password(user: User, provided_password: str) -> bool:
    """Verify password defensively to avoid 500s from malformed legacy hashes."""
    stored_hash = user.hashed_password or ""
    try:
        return verify_password(provided_password, stored_hash)
    except Exception as exc:
        logger.warning("Password verify failed for user_id=%s: %s", user.id, exc)

    # Legacy compatibility: some old records may store plaintext passwords.
    if stored_hash and provided_password == stored_hash:
        user.hashed_password = get_password_hash(provided_password)
        return True

    return False


def _assert_role_assignable_by_actor(db: Session, actor: User, requested_role: str) -> Role:
    target_name = _normalize_role_name(requested_role)
    if target_name == "developer":
        raise HTTPException(status_code=403, detail="Developer role cannot be assigned")

    if target_name not in {"admin", "user"}:
        raise HTTPException(status_code=400, detail="Role must be either admin or user")

    role = _role_by_name(db, target_name)
    if role is None:
        raise HTTPException(status_code=400, detail=f"Role '{requested_role}' does not exist")

    actor_role = _normalize_role_name(actor.role)
    if _is_developer_role(db, actor_role):
        return role

    if actor_role != "admin":
        raise HTTPException(status_code=403, detail="Only developer and admin can manage users")

    if role.name != "user":
        raise HTTPException(status_code=403, detail="Admin can assign only user role")

    return role


def _assert_actor_can_manage_user(db: Session, actor: User, target: User, allow_self: bool = False) -> None:
    if actor.id == target.id and not allow_self:
        raise HTTPException(status_code=400, detail="Cannot perform this action on your own account")

    actor_role = _normalize_role_name(actor.role)
    target_role = _normalize_role_name(target.role)

    actor_is_developer = _is_heilknights_developer(db, actor)
    target_is_developer = _is_developer_role(db, target_role) or (target.username or "").strip().lower() == DEVELOPER_USERNAME

    if target_is_developer and not actor_is_developer:
        raise HTTPException(status_code=403, detail="Only developer can manage developer account")

    if actor_is_developer:
        return

    if actor_role != "admin":
        raise HTTPException(status_code=403, detail="Only developer and admin can manage users")

    if target_role == "admin":
        raise HTTPException(status_code=403, detail="Only developer can manage admin accounts")

    actor_priority = _get_role_priority(db, actor_role)
    target_priority = _get_role_priority(db, target_role)
    if actor_priority <= target_priority:
        raise HTTPException(status_code=403, detail="Hierarchy violation: cannot manage same/higher role")


# Dependencies

async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})

    payload = decode_token(creds.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")

    return user


def checkDeveloper():
    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        _ensure_rbac_seeded(db)
        if not _is_heilknights_developer(db, current_user):
            raise HTTPException(status_code=403, detail="Developer (HeilKnights) access required")
        return current_user

    return dependency


def checkRole(allowed_roles: Optional[Set[str]] = None, min_priority: Optional[int] = None):
    allowed = {_normalize_role_name(role) for role in (allowed_roles or set())}

    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        _ensure_rbac_seeded(db)
        role_name = _normalize_role_name(current_user.role)
        is_heil_developer = _is_heilknights_developer(db, current_user)

        if _is_developer_role(db, role_name) and not is_heil_developer:
            raise HTTPException(status_code=403, detail="Developer account must be HeilKnights")

        if is_heil_developer:
            return current_user

        if allowed and role_name not in allowed:
            raise HTTPException(status_code=403, detail="Role access denied")

        if min_priority is not None and _get_role_priority(db, role_name) < min_priority:
            raise HTTPException(status_code=403, detail="Role hierarchy access denied")

        return current_user

    return dependency


def checkPermission(module: str, action: str):
    module_key = _normalize_module_name(module)
    action_key = action.strip().lower()
    requested = _permission_code(module_key, action_key)

    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        _ensure_rbac_seeded(db)
        role_name = _normalize_role_name(current_user.role)
        is_heil_developer = _is_heilknights_developer(db, current_user)

        if _is_developer_role(db, role_name) and not is_heil_developer:
            raise HTTPException(status_code=403, detail="Developer account must be HeilKnights")

        if is_heil_developer:
            return current_user

        permissions = _get_user_permissions(db, current_user)
        if requested not in permissions and _permission_code(module_key, "*") not in permissions:
            raise HTTPException(status_code=403, detail=f"Permission denied: {requested}")

        return current_user

    return dependency


def checkModuleAccess(module: str):
    return checkPermission(module, "view")


def checkHierarchy(user_id_param: str = "user_id", allow_self: bool = False, allowed_roles: Optional[Set[str]] = None):
    allowed = {_normalize_role_name(role) for role in (allowed_roles or set())}

    def dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        _ensure_rbac_seeded(db)

        current_role = _normalize_role_name(current_user.role)
        is_heil_developer = _is_heilknights_developer(db, current_user)
        if _is_developer_role(db, current_role) and not is_heil_developer:
            raise HTTPException(status_code=403, detail="Developer account must be HeilKnights")

        if allowed and current_role not in allowed and not is_heil_developer:
            raise HTTPException(status_code=403, detail="Role access denied")

        raw_id = request.path_params.get(user_id_param)
        if raw_id is None:
            return current_user

        try:
            target_id = int(raw_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid target user id")

        target = db.query(User).filter(User.id == target_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")

        _assert_actor_can_manage_user(db, current_user, target, allow_self=allow_self)
        return current_user

    return dependency


def require_admin(current_user: User = Depends(checkRole(allowed_roles={"admin", "developer"}))) -> User:
    return current_user


def require_manager_or_above(current_user: User = Depends(checkRole(allowed_roles={"admin", "developer"}))) -> User:
    return current_user


def require_owner(current_user: User = Depends(checkDeveloper())) -> User:
    # Backward-compatible alias: owner-only screens now map to developer role.
    return current_user


# Auth endpoints

@router.post("/login", response_model=Token)
def login(credentials: UserLogin, request: Request, db: Session = Depends(get_db)):
    _ensure_rbac_seeded(db)

    ip = request.client.host if request.client else ""
    ua = (request.headers.get("user-agent") or "")[:512]

    identifier = (credentials.username or "").strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="Username is required")

    identifier_lc = identifier.lower()

    user = db.query(User).filter(User.username == identifier).first()
    if not user:
        user = db.query(User).filter(func.lower(User.username) == identifier_lc).order_by(User.id.asc()).first()
    if not user:
        user = db.query(User).filter(func.lower(User.email) == identifier_lc).order_by(User.id.asc()).first()

    if not user or not _verify_user_password(user, credentials.password):
        if user:
            db.add(LoginHistory(user_id=user.id, ip_address=ip, user_agent=ua, status="failed"))
            db.commit()
        raise HTTPException(status_code=401, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    _ensure_user_primary_role(db, user)

    tokens = _jwt_pair(db, user)
    _create_session(db, user.id, tokens["refresh_token"], ip, ua)

    try:
        user.last_login = datetime.utcnow()
        db.add(LoginHistory(user_id=user.id, ip_address=ip, user_agent=ua, status="success"))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Login history write failed for user_id=%s: %s", user.id, exc)

    _log_activity(db, user.id, "login", f"Login from {ip}", ip)

    return tokens


@router.post("/register", response_model=UserSchema, status_code=201)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """Bootstrap flow: first account is always developer."""
    _ensure_rbac_seeded(db)

    if db.query(User).count() > 0:
        raise HTTPException(status_code=403, detail="Registration closed. Ask a developer/admin to create your account.")

    existing = db.query(User).filter((User.email == user_in.email) | (User.username == user_in.username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email or username already registered")

    db_user = User(
        email=user_in.email,
        username=DEVELOPER_USERNAME_DISPLAY,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role="developer",
        is_active=True,
        is_superuser=True,
    )
    db.add(db_user)
    db.flush()

    _ensure_user_primary_role(db, db_user)

    db.commit()
    db.refresh(db_user)
    return _serialize_user(db, db_user, include_permissions=True)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=Token)
def refresh_tokens(body: RefreshTokenRequest, request: Request, db: Session = Depends(get_db)):
    _ensure_rbac_seeded(db)

    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token", headers={"WWW-Authenticate": "Bearer"})

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")

    _ensure_user_primary_role(db, user)

    old_hash = _hash_token(body.refresh_token)
    db.query(UserSession).filter(UserSession.refresh_token_hash == old_hash).delete()

    tokens = _jwt_pair(db, user)
    ip = request.client.host if request.client else ""
    ua = (request.headers.get("user-agent") or "")[:512]
    _create_session(db, user.id, tokens["refresh_token"], ip, ua)
    db.commit()

    return tokens


@router.get("/me", response_model=UserSchema)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_rbac_seeded(db)
    _ensure_user_primary_role(db, current_user)
    db.commit()
    db.refresh(current_user)
    return _serialize_user(db, current_user, include_permissions=True)


@router.put("/me", response_model=UserSchema)
def update_profile(
    body: ProfileUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.full_name is not None:
        current_user.full_name = body.full_name
    ip = request.client.host if request.client else ""
    _log_activity(db, current_user.id, "update_profile", "Profile updated", ip)
    db.commit()
    db.refresh(current_user)
    return _serialize_user(db, current_user, include_permissions=True)


@router.put("/me/password")
def change_password(
    body: ChangePassword,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _verify_user_password(current_user, body.old_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = get_password_hash(body.new_password)
    ip = request.client.host if request.client else ""
    _log_activity(db, current_user.id, "change_password", "Password changed", ip)
    db.commit()
    return {"message": "Password updated"}


@router.get("/me/preferences")
def get_preferences(current_user: User = Depends(get_current_user)):
    return {
        "full_name": current_user.full_name,
        "timezone": current_user.timezone or "Asia/Kolkata",
        "language": current_user.language or "en",
        "email_notifications": current_user.email_notifications if current_user.email_notifications is not None else True,
    }


@router.put("/me/preferences")
def update_preferences(
    body: PreferencesUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.full_name is not None:
        current_user.full_name = body.full_name
    if body.timezone is not None:
        current_user.timezone = body.timezone
    if body.language is not None:
        current_user.language = body.language
    if body.email_notifications is not None:
        current_user.email_notifications = body.email_notifications

    ip = request.client.host if request.client else ""
    _log_activity(db, current_user.id, "update_preferences", "Preferences updated", ip)
    db.commit()
    db.refresh(current_user)

    return {
        "full_name": current_user.full_name,
        "timezone": current_user.timezone,
        "language": current_user.language,
        "email_notifications": current_user.email_notifications,
    }


@router.get("/sessions", response_model=List[SessionItem])
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    sessions = (
        db.query(UserSession)
        .filter(UserSession.user_id == current_user.id, UserSession.expires_at > now)
        .order_by(desc(UserSession.created_at))
        .all()
    )
    if sessions:
        sessions[0].is_current = True
    return sessions


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sess = db.query(UserSession).filter(UserSession.id == session_id, UserSession.user_id == current_user.id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    db.delete(sess)
    ip = request.client.host if request.client else ""
    _log_activity(db, current_user.id, "revoke_session", f"Revoked session #{session_id}", ip)
    db.commit()
    return {"message": "Session revoked"}


@router.post("/sessions/logout-others")
def logout_other_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    active = (
        db.query(UserSession)
        .filter(UserSession.user_id == current_user.id, UserSession.expires_at > now)
        .order_by(desc(UserSession.created_at))
        .all()
    )

    count = 0
    for idx, sess in enumerate(active):
        if idx == 0:
            continue
        db.delete(sess)
        count += 1

    ip = request.client.host if request.client else ""
    _log_activity(db, current_user.id, "logout_others", f"Revoked {count} other sessions", ip)
    db.commit()
    return {"message": f"Logged out {count} other sessions"}


# ADMIN + DEVELOPER: USER MANAGEMENT

@router.get("/users", response_model=UserList)
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(checkRole(allowed_roles={"admin", "developer"})),
    db: Session = Depends(get_db),
):
    _ensure_rbac_seeded(db)

    query = db.query(User)
    if not _is_heilknights_developer(db, current_user):
        query = query.filter(func.lower(User.role) != "developer", func.lower(User.username) != DEVELOPER_USERNAME)

    total = query.count()
    users = query.order_by(User.id).offset(skip).limit(limit).all()

    return {
        "users": [_serialize_user(db, u) for u in users],
        "total": total,
    }


@router.post("/users", response_model=UserSchema, status_code=201)
def create_user(
    user_in: UserCreate,
    request: Request,
    current_user: User = Depends(checkRole(allowed_roles={"admin", "developer"})),
    db: Session = Depends(get_db),
):
    _ensure_rbac_seeded(db)

    if (user_in.username or "").strip().lower() == DEVELOPER_USERNAME:
        raise HTTPException(status_code=403, detail="HeilKnights username is reserved for Developer account")

    role = _assert_role_assignable_by_actor(db, current_user, user_in.role)

    existing = db.query(User).filter((User.email == user_in.email) | (User.username == user_in.username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email or username already registered")

    db_user = User(
        email=user_in.email,
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=role.name,
        is_active=True,
        is_superuser=role.name in {"developer", "admin"},
    )
    db.add(db_user)
    db.flush()

    _ensure_user_primary_role(db, db_user)
    selected_modules = user_in.module_access
    if not selected_modules and role.name == "admin":
        selected_modules = list(USER_ASSIGNABLE_MODULES)
    if not selected_modules and role.name == "user":
        selected_modules = ["dashboard"]
    _set_user_module_access(db, db_user, selected_modules)

    db.commit()
    db.refresh(db_user)

    ip = request.client.host if request.client else ""
    _log_activity(db, current_user.id, "create_user", f"Created user {db_user.username} ({db_user.role})", ip)

    return _serialize_user(db, db_user)


@router.put("/users/{user_id}", response_model=UserSchema)
def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    current_user: User = Depends(checkHierarchy(allowed_roles={"admin", "developer"}, allow_self=False)),
    db: Session = Depends(get_db),
):
    _ensure_rbac_seeded(db)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # checkHierarchy already enforces target restrictions, keep explicit hard-stop for admin-on-admin
    _assert_actor_can_manage_user(db, current_user, user, allow_self=False)

    changes: List[str] = []

    if body.email is not None and body.email != user.email:
        user.email = body.email
        changes.append(f"email={body.email}")

    if body.full_name is not None:
        user.full_name = body.full_name
        changes.append(f"full_name={body.full_name}")

    if body.role is not None:
        target_role = _assert_role_assignable_by_actor(db, current_user, body.role)

        if _is_developer_role(db, user.role) and target_role.name != "developer":
            dev_count = db.query(User).filter(func.lower(User.role) == "developer").count()
            if dev_count <= 1:
                raise HTTPException(status_code=400, detail="Cannot demote the only developer account")

        user.role = target_role.name
        user.is_superuser = target_role.name in {"developer", "admin"}
        _ensure_user_primary_role(db, user)
        changes.append(f"role={target_role.name}")

    if body.module_access is not None:
        _set_user_module_access(db, user, body.module_access)
        changes.append(f"module_access={len(body.module_access)}")

    if body.is_active is not None:
        user.is_active = body.is_active
        changes.append(f"is_active={body.is_active}")

    db.commit()
    db.refresh(user)

    ip = request.client.host if request.client else ""
    _log_activity(db, current_user.id, "update_user", f"Updated user #{user_id}: {', '.join(changes)}", ip)

    return _serialize_user(db, user)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(checkHierarchy(allowed_roles={"admin", "developer"}, allow_self=False)),
    db: Session = Depends(get_db),
):
    _ensure_rbac_seeded(db)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _assert_actor_can_manage_user(db, current_user, user, allow_self=False)

    if _is_developer_role(db, user.role):
        dev_count = db.query(User).filter(func.lower(User.role) == "developer").count()
        if dev_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the only developer account")

    username = user.username
    db.delete(user)
    db.commit()

    ip = request.client.host if request.client else ""
    _log_activity(db, current_user.id, "delete_user", f"Deleted user {username} (#{user_id})", ip)

    return {"message": f"User {username} deleted"}


# DEVELOPER: ROLE & PERMISSION MANAGEMENT

@router.get("/permissions/catalog", response_model=List[PermissionItem])
def permission_catalog(
    current_user: User = Depends(checkDeveloper()),
    db: Session = Depends(get_db),
):
    _ensure_rbac_seeded(db)

    perms = db.query(Permission).order_by(Permission.module.asc(), Permission.action.asc()).all()
    return [
        {
            "id": p.id,
            "module": p.module,
            "action": p.action,
            "code": _permission_code(p.module, p.action),
            "description": p.description,
        }
        for p in perms
    ]


@router.get("/roles", response_model=List[RoleItem])
def list_roles(
    current_user: User = Depends(checkRole(allowed_roles={"admin", "developer"})),
    db: Session = Depends(get_db),
):
    _ensure_rbac_seeded(db)

    query = db.query(Role).filter(func.lower(Role.name).in_(["developer", "admin", "user"]))
    if not _is_developer_role(db, current_user.role):
        query = query.filter(Role.is_developer.is_(False))

    roles = query.order_by(Role.priority.desc(), Role.name.asc()).all()
    return [_serialize_role(role) for role in roles]


def _set_role_permissions(db: Session, role: Role, permission_codes: List[str]) -> None:
    if permission_codes is None:
        return

    normalized_codes = {_permission_code(*code.split(":", 1)) if ":" in code else "" for code in permission_codes}
    normalized_codes.discard("")

    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()

    if not normalized_codes:
        db.flush()
        return

    permissions = db.query(Permission).all()
    perm_map = {_permission_code(p.module, p.action): p for p in permissions}

    unknown = sorted([code for code in normalized_codes if code not in perm_map])
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown permission codes: {', '.join(unknown)}")

    for code in sorted(normalized_codes):
        perm = perm_map[code]
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    db.flush()


@router.post("/roles", response_model=RoleItem, status_code=201)
def create_role(
    body: RoleCreate,
    request: Request,
    current_user: User = Depends(checkDeveloper()),
    db: Session = Depends(get_db),
):
    _ensure_rbac_seeded(db)

    raise HTTPException(status_code=403, detail="Custom role creation is disabled. Use Developer/Admin/User roles only.")

    role_name = _normalize_role_name(body.name)
    if role_name in SYSTEM_ROLE_PRIORITIES:
        raise HTTPException(status_code=400, detail="System role names are reserved")

    if role_name == "developer":
        raise HTTPException(status_code=403, detail="Developer role cannot be created")

    if not role_name:
        raise HTTPException(status_code=400, detail="Role name is required")

    if not (SYSTEM_ROLE_PRIORITIES["user"] < body.priority < SYSTEM_ROLE_PRIORITIES["admin"]):
        raise HTTPException(status_code=400, detail="Custom role priority must be between 11 and 49")

    existing = _role_by_name(db, role_name)
    if existing:
        raise HTTPException(status_code=400, detail="Role already exists")

    role = Role(
        name=role_name,
        priority=body.priority,
        is_system=False,
        is_developer=False,
        description=body.description,
    )
    db.add(role)
    db.flush()

    _set_role_permissions(db, role, body.permission_codes)

    db.commit()
    db.refresh(role)

    ip = request.client.host if request.client else ""
    _log_activity(db, current_user.id, "create_role", f"Created role {role.name}", ip)

    db.refresh(role)
    return _serialize_role(role)


@router.put("/roles/{role_id}", response_model=RoleItem)
def update_role(
    role_id: int,
    body: RoleUpdate,
    request: Request,
    current_user: User = Depends(checkDeveloper()),
    db: Session = Depends(get_db),
):
    _ensure_rbac_seeded(db)

    raise HTTPException(status_code=403, detail="Custom role updates are disabled. Use Developer/Admin/User roles only.")

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_developer:
        raise HTTPException(status_code=403, detail="Developer role cannot be edited")

    if body.name is not None:
        new_name = _normalize_role_name(body.name)
        if role.is_system and new_name != role.name:
            raise HTTPException(status_code=400, detail="System role name cannot be changed")
        if new_name in SYSTEM_ROLE_PRIORITIES and new_name != role.name:
            raise HTTPException(status_code=400, detail="System role names are reserved")
        dup = _role_by_name(db, new_name)
        if dup and dup.id != role.id:
            raise HTTPException(status_code=400, detail="Role name already exists")
        role.name = new_name

    if body.priority is not None:
        if role.is_system and body.priority != role.priority:
            raise HTTPException(status_code=400, detail="System role priority cannot be changed")
        if not role.is_system and not (SYSTEM_ROLE_PRIORITIES["user"] < body.priority < SYSTEM_ROLE_PRIORITIES["admin"]):
            raise HTTPException(status_code=400, detail="Custom role priority must be between 11 and 49")
        role.priority = body.priority

    if body.description is not None:
        role.description = body.description

    if body.permission_codes is not None:
        _set_role_permissions(db, role, body.permission_codes)

    db.commit()
    db.refresh(role)

    ip = request.client.host if request.client else ""
    _log_activity(db, current_user.id, "update_role", f"Updated role {role.name}", ip)

    db.refresh(role)
    return _serialize_role(role)


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: int,
    request: Request,
    current_user: User = Depends(checkDeveloper()),
    db: Session = Depends(get_db),
):
    _ensure_rbac_seeded(db)

    raise HTTPException(status_code=403, detail="Custom role deletion is disabled. Use Developer/Admin/User roles only.")

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_developer:
        raise HTTPException(status_code=403, detail="Developer role cannot be deleted")

    if role.is_system:
        raise HTTPException(status_code=400, detail="System roles cannot be deleted")

    in_use_count = db.query(UserRole).filter(UserRole.role_id == role.id).count()
    if in_use_count > 0:
        raise HTTPException(status_code=400, detail="Role is assigned to users and cannot be deleted")

    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
    role_name = role.name
    db.delete(role)
    db.commit()

    ip = request.client.host if request.client else ""
    _log_activity(db, current_user.id, "delete_role", f"Deleted role {role_name}", ip)

    return {"message": f"Role {role_name} deleted"}


# DEVELOPER: LOGIN HISTORY & ACTIVITY LOGS

@router.get("/history/logins", response_model=List[LoginHistoryItem])
def get_login_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[int] = Query(None),
    current_user: User = Depends(checkDeveloper()),
    db: Session = Depends(get_db),
):
    _ = current_user

    query = db.query(LoginHistory).order_by(desc(LoginHistory.created_at))
    if user_id:
        query = query.filter(LoginHistory.user_id == user_id)

    rows = query.offset(skip).limit(limit).all()
    result = []
    for row in rows:
        item = LoginHistoryItem.model_validate(row)
        item.username = row.user.username if row.user else None
        result.append(item)
    return result


@router.get("/history/activity", response_model=List[ActivityLogItem])
def get_activity_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[int] = Query(None),
    current_user: User = Depends(checkDeveloper()),
    db: Session = Depends(get_db),
):
    _ = current_user

    query = db.query(ActivityLog).order_by(desc(ActivityLog.created_at))
    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)

    rows = query.offset(skip).limit(limit).all()
    result = []
    for row in rows:
        item = ActivityLogItem.model_validate(row)
        item.username = row.user.username if row.user else None
        result.append(item)
    return result
