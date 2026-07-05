---
name: cucut-language
description: >-
  English-only policy for cucut: all code, comments, docstrings, CLI messages,
  docs, commit messages, and agent-written repo content must be in English.
  Use when writing or editing any file in this repository, or when the user
  asks for Russian/non-English text in the codebase.
---

# Cucut language policy

## Rule (mandatory)

**English only** in everything that lives in the repository:

| Scope | English required |
|-------|------------------|
| Python source | identifiers, comments, docstrings, CLI help, errors |
| Shell scripts | comments, echo messages |
| Docs | README, AGENTS, CONTRIBUTING, CHANGELOG, skills |
| Config | workflow names, inline comments |
| Git | commit messages, PR descriptions, tags notes |
| CSV labels | column names, export labels (already English) |

## Never use non-English for

- User-facing CLI output (`print`, `argparse` descriptions)
- Code comments explaining logic
- Markdown documentation
- Agent-generated files committed to the repo

## Allowed exceptions

- **Chat with the user** may be in any language the user prefers — but **translate to English** before writing to repo files.
- **Proper nouns** (DJI, LosslessCut, file paths) stay as-is.
- **Third-party vendored skills** under `.agents/` / `.continue/` (e.g. caveman) — do not rewrite upstream content; new cucut-owned skills must be English.

## When editing existing Russian text

Replace with English equivalents. Do not leave mixed-language docs.

## Checklist before commit

```
- [ ] No Cyrillic or other non-English prose in changed files
- [ ] CLI --help strings in English
- [ ] README/CHANGELOG/AGENTS updates in English
- [ ] Commit message in English (conventional commits)
```

## Examples

Bad (in repo):
```python
print("Файл не найден")  # проверка пути
```

Good:
```python
print("File not found")  # path validation
```

Bad (README):
```markdown
## Установка
```

Good:
```markdown
## Install
```
