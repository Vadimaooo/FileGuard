"""Зрозумілі правила виключення без виконання регулярних виразів або коду."""

from fnmatch import fnmatchcase


class ExclusionRules:
    def __init__(self, patterns: tuple[str, ...] = ()) -> None:
        self.patterns = self.validate(patterns)

    @staticmethod
    def validate(patterns) -> tuple[str, ...]:
        if not isinstance(patterns, (list, tuple)) or len(patterns) > 100:
            raise ValueError("Допускається список не більш ніж зі 100 правил виключення.")
        result = []
        seen = set()
        for pattern in patterns:
            if not isinstance(pattern, str):
                raise ValueError("Кожне правило виключення повинно бути текстом.")
            value = pattern.strip().replace("\\", "/")
            if (not value or len(value) > 256 or value.startswith(("/", "!")) or ":" in value
                    or any(ord(char) < 32 for char in value)
                    or any(part in ("", ".", "..") for part in value.rstrip("/").split("/"))):
                raise ValueError("Некоректне виключення. Приклади: *.tmp, .git, cache/, logs/*.log.")
            if value.casefold() not in seen:
                result.append(value)
                seen.add(value.casefold())
        return tuple(result)

    @staticmethod
    def under_path(path: str, excluded: tuple[str, ...]) -> bool:
        key = path.casefold()
        return any(key == item.casefold() or key.startswith(item.casefold() + "/") for item in excluded)

    def matches(self, path: str, is_directory: bool = False) -> bool:
        parts = path.casefold().split("/")
        parents = ["/".join(parts[:index]) for index in range(1, len(parts))]
        for original in self.patterns:
            directories_only = original.endswith("/")
            pattern = original.rstrip("/").casefold()
            candidates = parents + (["/".join(parts)] if is_directory or not directories_only else [])
            if "/" not in pattern:
                candidates = parts[:-1] + ([parts[-1]] if is_directory or not directories_only else [])
            if any(fnmatchcase(candidate, pattern) for candidate in candidates):
                return True
        return False
