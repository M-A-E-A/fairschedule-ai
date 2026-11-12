"""CSV import for institution data (S-07).

Nobody types a university's courses, rooms, lecturers and student groups by
hand. This endpoint accepts one UTF-8 CSV file per request for a named dataset
(``rooms``, ``courses``, ``lecturers``, ``student-groups``) and applies it
**all-or-nothing**: every data row is validated before anything is written, so
a single bad row imports nothing. The 400 response lists every failing row by
its row number *as it appears in the file* (header = row 1) together with the
reason it failed, so a spreadsheet can be corrected in one pass.

Parsing uses the standard library ``csv`` module only — no new dependencies.

Security: the endpoint is role-gated to administrators and campus operators
(``ROOM_MANAGERS``) and tenant-scoped — rows are always written into the
caller's own institution, a campus id belonging to another tenant is a row
error, and targeting another tenant's institution id is refused outright with
403 before the file is even read.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from typing import Any

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlmodel import Session, select

from app.api.deps import ensure_tenant, require_roles
from app.core.db import get_session
from app.core.roles import ROOM_MANAGERS
from app.models import AuditEvent, Campus, Course, Lecturer, Room, StudentGroup, User

router = APIRouter(tags=['imports'])

# dataset -> header columns that must be present (extra columns are ignored).
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    'rooms': ('campus_id', 'name', 'capacity'),
    'courses': ('code', 'name'),
    'lecturers': ('name', 'email'),
    'student-groups': ('name', 'size'),
}

ValidationResult = tuple[list[Any], list[dict[str, Any]]]


def _cell(cells: list[str], position: int | None) -> str:
    """Whitespace-stripped cell at ``position``; '' for absent/short rows."""
    if position is None or position >= len(cells):
        return ''
    return cells[position].strip()


def _optional(cells: list[str], index: dict[str, int], column: str, default: str) -> str:
    return _cell(cells, index.get(column)) or default


def _read_upload(content: bytes) -> tuple[list[str], list[tuple[int, list[str]]], list[dict[str, Any]]]:
    """Decode and parse the upload into (header, [(row_number, cells)], errors).

    Row numbers are the physical line numbers of the file (the header is line
    1), which is exactly what someone correcting a spreadsheet needs. A UTF-8
    BOM (written by Excel) is tolerated; anything that is not UTF-8 text, an
    empty file, or a file without a header is a single reportable error.
    """
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        return [], [], [{'row': 1, 'reason': 'file is not valid UTF-8 text'}]
    if not text.strip():
        return [], [], [{'row': 1, 'reason': 'file is empty'}]

    reader = csv.reader(io.StringIO(text))
    try:
        raw_header = next(reader)
    except StopIteration:  # pragma: no cover - text.strip() already rejected empty input
        return [], [], [{'row': 1, 'reason': 'file is empty'}]
    header = [column.strip() for column in raw_header]
    # reader.line_num is the physical line the record ends on, so numbering
    # matches the file even if a quoted field contains a newline.
    rows = [(reader.line_num, row) for row in reader if any(cell.strip() for cell in row)]
    return header, rows, []


def _validate_rooms(
    session: Session, institution_id: int, index: dict[str, int], rows: list[tuple[int, list[str]]]
) -> ValidationResult:
    campuses = {
        campus.id
        for campus in session.exec(select(Campus).where(Campus.institution_id == institution_id)).all()
    }
    existing = {
        (room.campus_id, room.name)
        for room in session.exec(select(Room).where(Room.institution_id == institution_id)).all()
    }
    objects: list[Any] = []
    errors: list[dict[str, Any]] = []
    for row_number, cells in rows:
        campus_raw = _cell(cells, index.get('campus_id'))
        name = _cell(cells, index.get('name'))
        capacity_raw = _cell(cells, index.get('capacity'))
        reason = None
        campus_id = None
        try:
            campus_id = int(campus_raw)
        except ValueError:
            reason = f'campus_id {campus_raw!r} is not an integer'
        else:
            if campus_id not in campuses:
                reason = f'campus_id {campus_id} does not belong to this institution'
        if reason is None and not name:
            reason = 'name is required'
        capacity = None
        if reason is None:
            try:
                capacity = int(capacity_raw)
            except ValueError:
                reason = f'capacity {capacity_raw!r} is not an integer'
            else:
                if not 1 <= capacity <= 10000:
                    reason = f'capacity {capacity} must be between 1 and 10000'
        if reason is None and (campus_id, name) in existing:
            reason = f'room {name!r} already exists on campus {campus_id}'
        if reason is not None:
            errors.append({'row': row_number, 'reason': reason})
            continue
        existing.add((campus_id, name))
        objects.append(
            Room(
                institution_id=institution_id,
                campus_id=campus_id,
                name=name,
                capacity=capacity,
                room_type=_optional(cells, index, 'room_type', 'lecture'),
                equipment=_optional(cells, index, 'equipment', ''),
            )
        )
    return objects, errors


def _validate_courses(
    session: Session, institution_id: int, index: dict[str, int], rows: list[tuple[int, list[str]]]
) -> ValidationResult:
    existing = {
        course.code
        for course in session.exec(select(Course).where(Course.institution_id == institution_id)).all()
    }
    objects: list[Any] = []
    errors: list[dict[str, Any]] = []
    for row_number, cells in rows:
        code = _cell(cells, index.get('code'))
        name = _cell(cells, index.get('name'))
        reason = None
        if not code:
            reason = 'code is required'
        elif not name:
            reason = 'name is required'
        elif code in existing:
            reason = f'course code {code!r} already exists'
        if reason is not None:
            errors.append({'row': row_number, 'reason': reason})
            continue
        existing.add(code)
        objects.append(
            Course(
                institution_id=institution_id,
                code=code,
                name=name,
                required_room_type=_optional(cells, index, 'required_room_type', 'any'),
            )
        )
    return objects, errors


def _validate_lecturers(
    session: Session, institution_id: int, index: dict[str, int], rows: list[tuple[int, list[str]]]
) -> ValidationResult:
    existing = {
        lecturer.email
        for lecturer in session.exec(select(Lecturer).where(Lecturer.institution_id == institution_id)).all()
    }
    objects: list[Any] = []
    errors: list[dict[str, Any]] = []
    for row_number, cells in rows:
        name = _cell(cells, index.get('name'))
        email = _cell(cells, index.get('email'))
        reason = None
        if not name:
            reason = 'name is required'
        elif not email:
            reason = 'email is required'
        else:
            # No network access: syntax check only (deliverability is not an
            # import concern and would make validation nondeterministic).
            try:
                validate_email(email, check_deliverability=False)
            except EmailNotValidError as exc:
                reason = f'email {email!r} is not a valid address ({exc})'
            else:
                if email in existing:
                    reason = f'lecturer email {email!r} already exists'
        if reason is not None:
            errors.append({'row': row_number, 'reason': reason})
            continue
        existing.add(email)
        objects.append(Lecturer(institution_id=institution_id, name=name, email=email))
    return objects, errors


def _validate_student_groups(
    session: Session, institution_id: int, index: dict[str, int], rows: list[tuple[int, list[str]]]
) -> ValidationResult:
    existing = {
        group.name
        for group in session.exec(select(StudentGroup).where(StudentGroup.institution_id == institution_id)).all()
    }
    objects: list[Any] = []
    errors: list[dict[str, Any]] = []
    for row_number, cells in rows:
        name = _cell(cells, index.get('name'))
        size_raw = _cell(cells, index.get('size'))
        reason = None
        if not name:
            reason = 'name is required'
        size = None
        if reason is None:
            try:
                size = int(size_raw)
            except ValueError:
                reason = f'size {size_raw!r} is not an integer'
            else:
                if not 1 <= size <= 100000:
                    reason = f'size {size} must be between 1 and 100000'
        if reason is None and name in existing:
            reason = f'student group {name!r} already exists'
        if reason is not None:
            errors.append({'row': row_number, 'reason': reason})
            continue
        existing.add(name)
        objects.append(StudentGroup(institution_id=institution_id, name=name, size=size))
    return objects, errors


VALIDATORS: dict[str, Callable[[Session, int, dict[str, int], list[tuple[int, list[str]]]], ValidationResult]] = {
    'rooms': _validate_rooms,
    'courses': _validate_courses,
    'lecturers': _validate_lecturers,
    'student-groups': _validate_student_groups,
}


@router.post(
    '/institutions/{institution_id}/import/{dataset}',
    status_code=status.HTTP_201_CREATED,
)
async def import_csv(
    institution_id: int,
    dataset: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles(*ROOM_MANAGERS)),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Validate a CSV upload for ``dataset`` and apply it all-or-nothing.

    Every row is checked (value types, ranges, tenant-owned references, and
    duplicates both within the file and against existing rows) before a single
    INSERT happens. Any failure returns 400 with *every* failing row and
    writes nothing; success commits all rows in one transaction and records a
    ``csv_import`` audit event.
    """
    ensure_tenant(current_user, institution_id)
    if dataset not in VALIDATORS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'unknown dataset {dataset!r}; supported: {", ".join(REQUIRED_COLUMNS)}',
        )

    header, rows, errors = _read_upload(await file.read())
    if not errors:
        missing = [column for column in REQUIRED_COLUMNS[dataset] if column not in header]
        if missing:
            errors.append({'row': 1, 'reason': f'missing required column(s): {", ".join(missing)}'})
        elif not rows:
            errors.append({'row': 1, 'reason': 'header is present but no data rows were found'})

    objects: list[Any] = []
    if not errors:
        index = {column: position for position, column in enumerate(header)}
        objects, errors = VALIDATORS[dataset](session, institution_id, index, rows)

    if errors:
        # All-or-nothing: nothing has been added to the session yet, so the
        # request session's rollback on close guarantees no partial import.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'message': f'{len(errors)} row(s) failed validation; nothing was imported',
                'errors': errors,
            },
        )

    session.add_all(objects)
    session.add(
        AuditEvent(
            institution_id=institution_id,
            user_email=current_user.email,
            event_type='csv_import',
            message=f'CSV import ({dataset}): {len(objects)} row(s) imported',
        )
    )
    session.commit()
    return {'dataset': dataset, 'imported': len(objects), 'errors': []}
