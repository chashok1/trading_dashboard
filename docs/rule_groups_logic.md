# Rule Groups Logic

Deep-dive on the rule-groups layer — how groups are defined, evaluated, and
how a fired action group becomes a synthetic candidate action in
`derive_actionable`. `CLAUDE.md` carries only a one-line pointer to this file
in its Lookup index; keep the detail here.

## Overview

Rule groups sit above composite rules in the engine hierarchy: atomic rules →
composite rules → rule groups → `drv_actionable`. A group bundles one or more
composite rules (and optionally nested logical groups) under AND/OR logic with
an optional precondition gate. When the group fires, it either produces an
`action_label` + `priority` (an `action` group) or just a boolean result
consumed by a parent group (a `logical` group). Action-group fires are
converted into synthetic `RULES:<code>` candidates that compete alongside
outlook-source signals in `derive_actionable`'s winner sort.

## Diagrams

- `docs/diagrams/4_rules_authoring_data_flow.svg` — **authoring data flow**:
  how rules and groups flow from the UI through the API into the reference
  tables and ultimately into a derive run. Reference only.
- `docs/diagrams/14_rule_group_logic.svg` — **decision logic**: the
  evaluation pipeline from fired composite IDs through `eval_rule_group` to
  the synthetic candidate and `drv_actionable`.

Keep the logic diagram in sync whenever this logic changes.

## Schema — ref_trig_rule_group and ref_trig_group_member

`ref_trig_rule_group` holds one row per group:

| Column | Type | Notes |
|---|---|---|
| `rule_group_code` | VARCHAR(50) PK | Short mnemonic, e.g. `SA-Strong-Signal` |
| `group_type` | VARCHAR(20) | `'action'` or `'logical'`; enforced by CHECK |
| `action_label` | VARCHAR(20) | Required when `group_type='action'`; NULL for logical |
| `priority` | INT | Lower number wins; 1 = Sell All, 5 = Hold |
| `category` | VARCHAR(50) | Optional display grouping |
| `intent_text` | TEXT | Free-text description of the group's purpose |
| `deprecated_at` | TIMESTAMP | NULL = active; set by soft-delete |
| `created_at` | TIMESTAMP | Default `now()` |

A DB CHECK constraint enforces: `action` groups must have `action_label`; `logical` groups must not.

`ref_trig_group_member` holds the ordered member list for each group:

| Column | Type | Notes |
|---|---|---|
| `rule_group_code` | VARCHAR(50) FK | References `ref_trig_rule_group` |
| `member_code` | VARCHAR(50) | Code of a composite rule or a nested logical group |
| `member_type` | VARCHAR(20) | `'composite'` or `'group'` |
| `logic_operator` | VARCHAR(5) | `'AND'` or `'OR'`; enforced by CHECK |
| `sequence` | INT | Evaluation order; PK is `(rule_group_code, member_code, sequence)` |

## group_type: action vs. logical

**`action` groups** are the end-goal objects. They carry an `action_label` and
a `priority` (1–5). When `eval_rule_group` returns
`(True, action_label, priority)`, the caller (`derive_actionable`) treats this
as a candidate action.

> **Action vocabulary (canonical, 2026-06-03).** The trading actions encoded in
> composite rule-codes and group `action_label`s are:
> `SA, SW, STM, SS` (sell-family) and `B, BS, BR, BW, BM, BMN` (buy-family), plus
> `HOLD`. Earlier drafts of this doc and `actionable_logic.md` also used an
> `ADD / REMOVE / INCREASE / REDUCE` sizing vocabulary — that is the
> *position-sizing* layer in `derive_actionable`, a separate concept from the
> rule-action labels here. Don't conflate the two.

**`logical` groups** have no `action_label`. They exist solely to be
referenced as members of other groups under `member_type='group'`. Nesting
allows you to factor a reusable boolean sub-expression (e.g. "at least one
bearish signal fired") and compose it into multiple action groups without
repeating the member list. `eval_rule_group` evaluates them recursively and
returns only a boolean.

## eval_rule_group — AND/OR evaluation with short-circuit

`etl/rule_groups.py::eval_rule_group(session, group_code, composite_results,
all_group_results)` evaluates one group, returning
`(triggered: bool, action_label: str|None, priority: int|None)`.

`composite_results` is a `{composite_rule_code: True}` dict built by the
caller from `drv_stks.triggered_composite_ids` for the symbol being evaluated.
`all_group_results` is a memoisation cache keyed by `group_code`; it avoids
re-evaluating the same nested group for the same symbol.

**Evaluation steps:**

1. Cache hit → return immediately.
2. Fetch the group row from `ref_trig_rule_group` (skips deprecated rows).
3. Fetch members ordered by `sequence` from `ref_trig_group_member`.
4. For each member in sequence order:
   - `member_type='composite'` → look up `composite_results.get(member_code, False)`.
   - `member_type='group'` → recurse into `eval_rule_group` for that nested group.
5. **AND short-circuit**: if a member has `logic_operator='AND'` and is False,
   the group immediately returns `(False, None, None)` without evaluating
   further members.
6. After all members: if any operator is `'OR'`, the group fires if `any(member_results)`;
   if all operators are `'AND'`, it fires only if `all(member_results)` (the
   short-circuit above guarantees all are True at this point).
7. Fired → return `(True, action_label, priority)`; not fired → `(False, None, None)`.

Note: precondition gating is not a separate field in `ref_trig_rule_group`;
preconditions are expressed by adding a `member_type='composite'` member with
`logic_operator='AND'` at `sequence=1`. That member must fire before any
subsequent OR members matter.

## From a fired action group to a candidate in derive_actionable

`etl/derive_actionable.py` runs this loop per symbol:

1. Build `composite_results = {code: True for code in fired_composite_ids}` from
   `drv_stks.triggered_composite_ids` (a JSONB list of `{"rule_id": code, ...}` dicts).
2. Load all non-deprecated `group_type='action'` rows from `ref_trig_rule_group`
   whose `action_label` is in `ACTION_RANK` (i.e. a real tradeable action).
3. Call `eval_rule_group` for each. Fired groups are collected in
   `triggered_groups` (written to `drv_actionable.triggered_group_ids` as JSONB)
   and also added to `group_candidates` as synthetic action dicts with
   `source_code = f"RULES:{group_code}"` and `_group_prio = priority`.
4. `group_candidates` are merged with outlook-source candidates into a single
   list. The combined list is sorted by `(-ACTION_RANK[action], priority_asc)`.
   - Most aggressive action wins (REMOVE 4 > REDUCE 3 > INCREASE 2 > ADD 1 > HOLD 0).
   - Ties within the same aggression level break by the numeric priority
     (`ref_trig_rule_group.priority` for groups; `ref_outlook_source.investment_priority`
     for outlook sources). Lower number wins.
5. The winner's `source_code`, `action`, and priority become `drv_actionable.winning_source`,
   `consolidated_action`, and `winning_priority` for the symbol. A `RULES:`-prefixed
   `winning_source` tells the UI that a rule group drove the action.

`resolve_final_action` in `rule_groups.py` is a utility used outside the
derive path to pick the highest-priority group from a pre-filtered list.

## Authoring screen — /groups

`web/groups.html` exposes full CRUD backed by the API routes in
`api/routers/rules.py`:

| Operation | Endpoint |
|---|---|
| List all groups | `GET /api/rules/groups` |
| Get one group with members | `GET /api/rules/groups/{code}` |
| Create | `POST /api/rules/groups` |
| Update metadata + replace members | `PUT /api/rules/groups/{code}` |
| Soft-delete (set `deprecated_at`) | `DELETE /api/rules/groups/{code}` |
| Test against a snapshot date | `GET /api/rules/groups/{code}/test?date=YYYY-MM-DD` |

The modal form includes a **Logic Preview** box that renders
`IF (member1 AND member2 OR member3) THEN action (Priority N)` live as members
are added, and a **Test** panel that calls the test endpoint and shows how many
symbols in `drv_stks` would trigger for the chosen date.

The UI currently only supports `member_type='composite'` members; nested
logical groups can be wired at the DB level but the form does not expose a
group-member picker.

## Derive lifecycle

Rule-group evaluation runs inside `derive_actionable` (stage 2 of the derive
cascade), after `drv_stks` has been written for the same date. Re-running
derive for date D is idempotent: `drv_actionable` for D is deleted before
the loop runs, so group fires are recomputed cleanly.

After editing group definitions in the authoring screen, trigger a re-derive
via the File Monitor's "Run Missing Derives" button or call
`derive_actionable` directly for the affected dates.
