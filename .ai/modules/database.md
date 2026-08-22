---
name: database
description: Database planning, migration, and data-access rules. Load for any schema or data change.
---

# Module: Database

## Purpose
Standards for schema changes, migrations, and data access, independent of engine (engine specifics come from existing schema + .ai/knowledge/conventions.md).

## When to Load
Any task owned by the Database agent, or any task that changes the database — schema OR data.

## Standards
- **Plan first (mandatory)**: any database change (schema OR data: migration, DDL, bulk/data update, seed) requires a task in `.project/<feature>/tasks.md` (or a `features/<feature>/`) before touching the DB — never the trivial fast path (rules.yaml: `db_changes_require_plan`, Gate G1)
- **Migrations**: every change ships as up + down; down is tested, not decorative
- **Integrity**: FK, unique, not-null, and checks live in the database; application checks are a second layer, not a substitute
- **Naming**: follow the existing schema's conventions exactly (case, plurality, prefixes)
- **Indexes**: every query pattern this feature introduces has a covering index or a written reason why not
- **Destructive ops**: dropping/renaming columns or tables, bulk deletes → explicit user approval + backup step first
- **Large tables**: batched migration plan; no unbounded locks

## Checklist (per task)
- [ ] Up and down migrations both run clean
- [ ] Constraints at DB level
- [ ] Index coverage checked against new queries
- [ ] Naming consistent with existing schema
- [ ] Destructive steps approved and backed up

## Output
Migration files + schema notes in `.project/<feature>/architecture.md`.
