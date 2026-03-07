from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath


DISABLED_NAME_TOKEN = ".disabled"
IGNORE_FILENAME = ".pocketcodeignore"


@dataclass(frozen=True)
class _DiscoveryRule:
    pattern: str
    include: bool
    anchored: bool
    dir_only: bool
    basename_only: bool


class DiscoveryFilter:
    def __init__(self, root: Path, rules: list[_DiscoveryRule] | None = None):
        self._root = Path(root).resolve()
        self._rules = rules or []

    @classmethod
    def from_root(cls, root: Path, *, ignore_dir: Path | None = None) -> "DiscoveryFilter":
        root = Path(root).resolve()
        base_dir = Path(ignore_dir).resolve() if ignore_dir is not None else root
        ignore_path = base_dir / IGNORE_FILENAME
        if not ignore_path.is_file():
            return cls(root=root, rules=[])
        return cls(root=root, rules=_parse_rules(ignore_path.read_text(encoding="utf-8")))

    def ignores(self, path: Path, *, is_dir: bool | None = None) -> bool:
        resolved = Path(path).resolve()
        if is_dir is None:
            is_dir = resolved.is_dir()

        if _contains_disabled_name(resolved, self._root):
            return True

        try:
            relative = resolved.relative_to(self._root)
        except ValueError:
            return False

        include = True
        for rule in self._rules:
            if _rule_matches(rule, relative, is_dir=is_dir):
                include = rule.include
        return not include

    def ignores_relative(self, relative_path: Path | str, *, is_dir: bool = False) -> bool:
        relative = Path(relative_path)

        if any(DISABLED_NAME_TOKEN in part for part in relative.parts):
            return True

        include = True
        for rule in self._rules:
            if _rule_matches(rule, relative, is_dir=is_dir):
                include = rule.include
        return not include


def _parse_rules(raw_text: str) -> list[_DiscoveryRule]:
    rules: list[_DiscoveryRule] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        include = False
        if line.startswith("!"):
            include = True
            line = line[1:].strip()
            if not line:
                continue

        anchored = line.startswith("/")
        if anchored:
            line = line[1:]

        dir_only = line.endswith("/")
        if dir_only:
            line = line[:-1]

        pattern = line.strip()
        if not pattern:
            continue

        rules.append(
            _DiscoveryRule(
                pattern=pattern,
                include=include,
                anchored=anchored,
                dir_only=dir_only,
                basename_only="/" not in pattern,
            )
        )
    return rules


def _contains_disabled_name(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return any(DISABLED_NAME_TOKEN in part for part in relative.parts)


def _rule_matches(rule: _DiscoveryRule, relative_path: Path, *, is_dir: bool) -> bool:
    posix_path = PurePosixPath(relative_path.as_posix())

    if rule.dir_only:
        directory_candidates = list(_directory_candidates(posix_path, is_dir=is_dir))
        if rule.basename_only:
            return any(fnmatchcase(candidate.name, rule.pattern) for candidate in directory_candidates)
        return any(_path_pattern_matches(candidate, rule.pattern, anchored=rule.anchored) for candidate in directory_candidates)

    if rule.basename_only:
        return any(fnmatchcase(part, rule.pattern) for part in posix_path.parts)

    return _path_pattern_matches(posix_path, rule.pattern, anchored=rule.anchored)


def _directory_candidates(path: PurePosixPath, *, is_dir: bool) -> list[PurePosixPath]:
    parts = path.parts if is_dir else path.parts[:-1]
    return [PurePosixPath(*parts[:index]) for index in range(1, len(parts) + 1)]


def _path_pattern_matches(path: PurePosixPath, pattern: str, *, anchored: bool) -> bool:
    if path.match(pattern):
        return True
    if anchored:
        return False
    return path.match(f"**/{pattern}")
