# Domain modeling

`domain/` holds the business vocabulary and the decisions made with it: types
and pure functions, no I/O. This file owns *what* to model and where behavior
goes. Type idioms (dataclass options, Pydantic at trust boundaries, `StrEnum`
versus `Literal`, named outcomes) are owned by `python-code-conventions`
(fallback: `../../python-code-conventions/SKILL.md`, "Data containers", "Closed vocabularies", "Outcome contracts").

## What lives here

| Kind | Example | Shape |
| --- | --- | --- |
| Value | `Money`, `Selection`, `EmailAddress` | Frozen dataclass whose construction enforces its rules |
| Identifier | `ClaimId` | `NewType` over `UUID` or `str` when it has no rules of its own |
| Record | `Claim` | Frozen dataclass of what the business knows about one thing |
| State | `ClaimStatus`, or a closed union of state types | `StrEnum` when every state has the same fields; a union when fields depend on the state |
| Policy | `ApprovalPolicy` | Frozen dataclass of settings-derived limits, built by bootstrap |
| Observation | `ClaimObservation` | What a decision needs to see, mapped from storage |
| Decision | `ApprovalDecision` | What to write and what happened, returned by a pure function |
| Business error | `ClaimNotPendingError` | Raised by a decision or a constructor, mapped to a public error in `api/` |

One module per business concept (`domain/claims.py` holds the claim's types,
decisions, and errors) following flat-first growth
([boundaries.md](boundaries.md#flat-first-growth-across-boundaries)). Do not
split into `entities.py`, `value_objects.py`, `services.py`: those group by
pattern, and every change would touch all of them.

## Make invalid values impossible to build

Validate where a value is constructed, so every holder of a value can trust it.

- An invariant that needs only the value's own fields goes in `__post_init__`
  and raises a domain error.
- A value that needs outside input to build (a policy, a default) gets one
  named constructor, such as `normalize(request, policy) -> Selection`, and the
  docstring says it is the only way to build one.
- When some fields exist only in some states, model the states as a closed
  union instead of a status plus nullable fields:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Pending:
    submitted_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class Approved:
    approved_by: UserId
    approved_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class Rejected:
    rejected_by: UserId
    reason: str


type ClaimState = Pending | Approved | Rejected
```

With the union, an approved claim without an approver cannot exist, and a
`match` with `assert_never` makes every consumer handle each state. A status
enum is enough when no field depends on it.

Wrap a primitive only when it has rules (normalization, range, format) or when
two primitives of the same type are easy to swap (`ClaimId` versus `UserId`).
Do not wrap every `str`.

## Decisions: observation in, decision out

Every business rule that chooses a status, an outcome, an error, a delay, or a
message is a pure function:

```python
def decide_approval(
    *, observed: ClaimObservation, actor: Actor, policy: ApprovalPolicy, now: datetime
) -> ApprovalDecision: ...
```

- Inputs are values: the observation, the actor, the policy, and `now` or ids
  when the rule depends on them ([boundaries.md](boundaries.md#nondeterminism)).
- The output says what to write and what happened; the caller applies it and
  does not re-derive any of it. Invariants of the decision itself go in its
  `__post_init__`.
- A forbidden transition raises a domain error or returns a named outcome;
  choose by whether callers treat it as a failure or as a normal result.

The same function is called by a repository inside a transaction or by an
action inside a unit of work ([persistence.md](persistence.md)); the decision
does not know which. It is tested with plain unit tests and no doubles.

## Methods or functions

- A method is fine for behavior that reads only the value's own fields and
  involves nothing else: `money.add(other)`, `claim.is_editable`.
- A decision that involves policy, time, an actor, or several records is a
  module function next to the types, not a method on one of them.
- Values are frozen. A "change" returns a new value (`dataclasses.replace`,
  after which the constructor's checks run again); nothing in `domain/`
  mutates its inputs.

## Signs the logic is in the wrong place

- An action or a repository contains `if claim.status == ...` or picks a status,
  error code, retry delay, or message: move the choice into a decision function.
- The same check appears in two actions: it is a domain rule; give it a name.
- A domain function needs a database row, a request, a model response, or
  settings: pass the values it needs instead.
- A test must fake a port to check a value computed without I/O: the
  computation belongs in `domain/` and gets its own test.

Records with functions beside them are not a problem to fix; business rules
scattered across actions, routes, and repositories are.
