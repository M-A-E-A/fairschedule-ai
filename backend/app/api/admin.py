"""Administrator-only endpoints: user management and the tenant summary.

Every query is scoped to the caller's own institution — an administrator of
one tenant can neither read nor mutate another tenant's data, even by id.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from app.api.deps import ensure_tenant, require_roles
from app.core.db import get_session
from app.core.roles import ADMINISTRATOR, ALL_ROLES
from app.core.security import hash_password
from app.models import Campus, Institution, Lecturer, StudentGroup, User
from app.schemas.auth import CreateUserRequest, UpdateUserRequest

router = APIRouter(tags=['administration'])


def _user_dict(user: User) -> dict[str, Any]:
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'full_name': user.full_name,
        'role': user.role,
        'institution_id': user.institution_id,
        'is_active': user.is_active,
        'student_group_id': user.student_group_id,
        'lecturer_id': user.lecturer_id,
        'sso_linked': bool(user.external_subject),
    }


def _tenant_users(session: Session, institution_id: int) -> list[User]:
    return session.exec(select(User).where(User.institution_id == institution_id)).all()


def _validate_role(role: str) -> None:
    if role not in ALL_ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'unknown role {role!r}')


def _validate_links(session: Session, institution_id: int, group_id: int | None, lecturer_id: int | None) -> None:
    if group_id is not None:
        group = session.get(StudentGroup, group_id)
        if group is None or group.institution_id != institution_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='student group belongs to another tenant')
    if lecturer_id is not None:
        lecturer = session.get(Lecturer, lecturer_id)
        if lecturer is None or lecturer.institution_id != institution_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='lecturer belongs to another tenant')


def _get_target(session: Session, user_id: int, actor: User) -> User:
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='user not found')
    if target.institution_id != actor.institution_id:
        # Same status whether the attacker guesses an id or not: no cross-tenant
        # existence is revealed beyond the refusal itself.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='tenant mismatch')
    return target


@router.get('/demo/tenant-summary')
def tenant_summary(
    current_user: User = Depends(require_roles(ADMINISTRATOR)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Institution summary for the caller's tenant only (was: every tenant,
    unauthenticated — see ISSUES.md)."""
    institution = session.get(Institution, current_user.institution_id)
    if institution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='institution not found')
    campus_rows = session.exec(select(Campus).where(Campus.institution_id == institution.id)).all()
    return {
        'institutions': [
            {
                'id': institution.id,
                'name': institution.name,
                'slug': institution.slug,
                'campus_count': len(campus_rows),
                'user_count': len(_tenant_users(session, institution.id)),
            }
        ]
    }


@router.get('/admin/users')
def list_users(
    current_user: User = Depends(require_roles(ADMINISTRATOR)),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return [_user_dict(user) for user in _tenant_users(session, current_user.institution_id)]


@router.post('/admin/users', status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    current_user: User = Depends(require_roles(ADMINISTRATOR)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _validate_role(payload.role)
    _validate_links(session, current_user.institution_id, payload.student_group_id, payload.lecturer_id)
    if session.exec(select(User).where(User.username == payload.username)).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='username already taken')
    if session.exec(select(User).where(User.email == payload.email.lower())).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='email already registered')
    user = User(
        username=payload.username,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        institution_id=current_user.institution_id,
        student_group_id=payload.student_group_id,
        lecturer_id=payload.lecturer_id,
        is_active=payload.is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _user_dict(user)


@router.patch('/admin/users/{user_id}')
def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    current_user: User = Depends(require_roles(ADMINISTRATOR)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    target = _get_target(session, user_id, current_user)
    changes = payload.model_dump(exclude_unset=True)
    if 'role' in changes and changes['role'] is not None:
        _validate_role(changes['role'])
    if target.id == current_user.id:
        if 'role' in changes and changes['role'] != target.role:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='cannot change your own role')
        if changes.get('is_active') is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='cannot deactivate your own account')
    # Deleting an administrator can never lock the tenant out: only an
    # administrator may reach this endpoint and self-deletion is refused, so at
    # least the calling administrator always remains.
    if changes.get('email') is not None:
        existing = session.exec(select(User).where(User.email == changes['email'].lower())).first()
        if existing is not None and existing.id != target.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='email already registered')
        target.email = changes['email'].lower()
    if changes.get('full_name') is not None:
        target.full_name = changes['full_name']
    if changes.get('role') is not None:
        target.role = changes['role']
    if changes.get('password') is not None:
        target.password_hash = hash_password(changes['password'])
    if changes.get('is_active') is not None:
        target.is_active = changes['is_active']
    if payload.clear_links:
        target.student_group_id = None
        target.lecturer_id = None
    else:
        if 'student_group_id' in changes:
            _validate_links(session, target.institution_id, changes['student_group_id'], None)
            target.student_group_id = changes['student_group_id']
        if 'lecturer_id' in changes:
            _validate_links(session, target.institution_id, None, changes['lecturer_id'])
            target.lecturer_id = changes['lecturer_id']
    session.add(target)
    session.commit()
    session.refresh(target)
    return _user_dict(target)


@router.delete('/admin/users/{user_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: User = Depends(require_roles(ADMINISTRATOR)),
    session: Session = Depends(get_session),
) -> None:
    target = _get_target(session, user_id, current_user)
    if target.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='cannot delete your own account')
    session.delete(target)
    session.commit()
