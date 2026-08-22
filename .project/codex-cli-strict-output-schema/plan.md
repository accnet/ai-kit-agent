# Plan — codex-cli-strict-output-schema

status: done
updated: 2026-08-22

## Goal

Make Codex CLI accept AI-Kit's structured output schemas while preserving the
kit's optional-field semantics and post-response validation.

## Approach

Adapt schemas only at the Codex transport boundary: recursively mark every
object property required for OpenAI strict structured outputs, represent
originally optional properties as nullable, and remove only those optional null
values before validating against the canonical AI-Kit schema. Keep Claude and
scripted provider behavior unchanged. Add an offline subprocess regression,
then retry the isolated real Codex/Terra delegation task.

## Risks

- Recursive conversion must preserve nested arrays and required fields.
- Null cleanup must never hide nulls supplied for canonically required fields.
- The live retry must stay inside the isolated fixture task scope.

## Out of scope

- Changing provider models, authentication, route defaults, or user project files.
- Relaxing canonical schema validation or task mutation-scope enforcement.

## Open questions

None.
