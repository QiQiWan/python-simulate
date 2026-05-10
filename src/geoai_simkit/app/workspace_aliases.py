from __future__ import annotations

from typing import Any

CANONICAL_FEM_PAGES: tuple[str, ...] = ('modeling', 'mesh', 'solve', 'results', 'benchmark', 'advanced')
LEGACY_SPACE_ALIASES: dict[str, str] = {
    'project': 'modeling',
    'model': 'mesh',
    'diagnostics': 'benchmark',
    'delivery': 'advanced',
}
FEM_PAGE_TO_LEGACY_SPACE: dict[str, str] = {
    'modeling': 'project',
    'mesh': 'model',
    'solve': 'solve',
    'results': 'results',
    'benchmark': 'diagnostics',
    'advanced': 'delivery',
}

def canonical_space(space: str | None, *, default: str = 'modeling') -> str:
    key = str(space or '').strip().lower()
    if key in CANONICAL_FEM_PAGES:
        return key
    if key in LEGACY_SPACE_ALIASES:
        return LEGACY_SPACE_ALIASES[key]
    return default

def compatibility_alias_rows() -> list[dict[str, Any]]:
    return [
        {'legacy_space': legacy, 'canonical_space': canonical, 'status': 'compatibility_alias', 'remove_internal_dependency': True}
        for legacy, canonical in LEGACY_SPACE_ALIASES.items()
    ]
