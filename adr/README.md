# Architecture decision records

This directory preserves the durable architectural decisions behind this
project. Read the accepted records that affect an area before changing it.

Create an ADR for a decision that changes a layer boundary, public interface,
security or deployment model, data lifecycle, or a long-lived dependency. Do
not create one for routine implementation details or temporary tasks.

Use zero-padded, never-reused filenames:

```text
0001-short-decision-title.md
```

Use this template:

```markdown
# ADR 0001: Short decision title

- Status: Proposed | Accepted | Superseded by ADR NNNN
- Date: YYYY-MM-DD

## Context

What problem requires a durable decision?

## Decision

What is the chosen approach?

## Consequences

What becomes easier, harder, required or deliberately out of scope?

## Alternatives considered

What credible alternatives were rejected, and why?
```

Accepted ADRs are historical records: do not rewrite their decision. When a
decision changes, add a new ADR and mark the older record as superseded.
