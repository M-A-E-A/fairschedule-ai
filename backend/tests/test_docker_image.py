"""Static regression guard for the backend Docker image (R-015).

The image's only entrypoint boots the API, whose lifespan runs
``run_migrations()`` unconditionally; ``app.core.migrations`` resolves
``alembic.ini`` and the ``alembic/`` script directory from ``BACKEND_ROOT``,
which is ``/app`` inside the image. The image therefore only boots if those
artifacts are COPYed in — Compose's ``./backend:/app`` bind mount must stay a
dev convenience, not a load-bearing mask.

Docker is unavailable on this machine and in CI, so the wiring is pinned
statically: the paths ``build_alembic_config()`` actually resolves must exist
in the build context and be referenced by the Dockerfile's COPY instructions.
This fails on the pre-R-015 Dockerfile, which copied only
``requirements.txt`` and ``app/``.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.migrations import BACKEND_ROOT, build_alembic_config

DOCKERFILE = BACKEND_ROOT / 'Dockerfile'


def _copy_sources(dockerfile_text: str) -> set[str]:
    """Return the context paths referenced by every COPY instruction.

    Handles the plain (``COPY src... dest``) and JSON-list forms, skips build
    flags such as ``--chown``, and normalizes ``./alembic/`` to ``alembic``.
    The trailing token is always the destination and is dropped.
    """
    sources: set[str] = set()
    for line in dockerfile_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        upper = stripped.upper()
        if upper.startswith('COPY ['):
            paths = json.loads(stripped[5:])[:-1]
        elif upper.startswith('COPY '):
            tokens = [token for token in stripped.split()[1:] if not token.startswith('--')]
            paths = tokens[:-1]
        else:
            continue
        for path in paths:
            sources.add(path.removeprefix('./').rstrip('/'))
    return sources


def test_migrations_artifacts_exist_in_build_context() -> None:
    """``run_migrations()`` must resolve a complete Alembic chain in the context."""
    config = build_alembic_config()
    ini = Path(config.config_file_name)
    script_dir = Path(config.get_main_option('script_location'))
    assert ini.is_file(), f'{ini} is missing from the build context'
    assert (script_dir / 'env.py').is_file(), 'alembic/env.py is missing from the build context'
    assert (script_dir / 'script.py.mako').is_file(), 'alembic/script.py.mako is missing from the build context'
    assert list(script_dir.glob('versions/*.py')), 'no Alembic revisions tracked in alembic/versions/'


def test_dockerfile_copies_migration_artifacts() -> None:
    """The Dockerfile must COPY what startup migrations need (R-015)."""
    config = build_alembic_config()
    needed = {
        Path(config.config_file_name).relative_to(BACKEND_ROOT).as_posix(),
        Path(config.get_main_option('script_location')).relative_to(BACKEND_ROOT).as_posix(),
    }
    sources = _copy_sources(DOCKERFILE.read_text(encoding='utf-8'))
    assert sources, 'Dockerfile contains no COPY instructions'
    if '.' in sources:
        return  # the whole build context is copied; the artifacts ride along
    missing = needed - sources
    assert not missing, (
        f'Dockerfile does not COPY {sorted(missing)} into the image; '
        'startup migrations crash outside the Compose bind mount (R-015)'
    )
