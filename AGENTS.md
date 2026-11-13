# AGENTS.md

Implementation workflow notes for AI coding agents working on minitile. The spec itself is in
[SPEC.md](SPEC.md).

## How to use this spec

- Implement only what has an APPROVED spec section in SPEC.md. If requested work has no approved
  section, stop and ask. Sections marked PROPOSED must not be implemented.
- Work in the order of **Section 10 (Implementation steps)**. Each step ends with passing tests,
  `ruff check`, `ruff format --check` and `mypy --strict` clean, and one commit.
- Formulas and definitions in this spec are the source of truth. If something is ambiguous or seems
  wrong, **stop and ask** instead of guessing or silently changing the definition.
- Prefer small, pure functions. No global state. All randomness goes through a seeded `random.Random`.
- Do not add dependencies beyond Section 2 without asking.
