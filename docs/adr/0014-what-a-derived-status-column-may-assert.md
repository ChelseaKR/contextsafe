# ADR 0014 — What a derived column may assert about an item's state

Status: proposed; what the backlog's derived column asserts is the maintainer's call and is not made here
Date: 2026-09-05
Decision owners: technical owner for the backlog's shape and for `tools/claims_gate.py`
Review trigger: acceptance of this record, and the first backlog item whose acceptance statement has objective evidence

## Context

`make claims` derives a `Status` cell for every phase-table row in
`docs/13-BACKLOG.md` from the implementation notes in the same file (#98). The
column exists because the notes are chronological and had outgrown their shape:
an item's row was separated from its status by the notes for four other items,
and a reader could not find one item's state without reading nine notes about
others. Deriving the cell rather than typing it means it cannot drift from the
notes it indexes, and a row that stops carrying a cell is a finding for the same
reason.

The cell has exactly two possible values, and `tools/claims_gate.py` produces
them:

```python
def backlog_status(item: str, dates: dict[str, str]) -> str:
    date = dates.get(item)
    return "Open — no note" if date is None else f"Open — note {date}"
```

`Open` is a literal. Across the 57 phase rows today, 30 read `Open — no note`
and 27 read `Open — note <date>`. The word is not derived from anything; it is
typed into the gate.

**The consequence is dated rather than hypothetical: the day an item genuinely
closes, the gate will refuse the truthful cell.** Writing `Closed` in the table
fails `make claims`, and a test pins that it does —
`test_a_status_cell_that_disagrees_with_the_notes_is_a_finding` in
`tests/test_claims_gate.py` puts `Closed` in B-022's row and requires the
finding.

That was left deliberately, and the reason is this repository's own rule.
`docs/18-ASSURANCE-PROGRAM.md` exists to remove checks that state more than they
examined, and `DEFINITION_OF_DONE.md` says an item is done only when its
acceptance statement has objective evidence. A derived column asserting
"closed" from the existence of a dated note would be a gate inventing a claim
about completion out of a fact about a file. So the gate says `Open` and the
column's header says `Status`, and those two are not the same kind of statement.
What the column actually carries is an index to a note; what its header promises
is a state a reader can act on.

`docs/13-BACKLOG.md` is honest about this in prose — "The column has exactly two
values, and both begin with `Open`, because **no item in this backlog is
closed**" — which makes the header the only place still overstating. That is
what #111 asks to settle.

## The decision the maintainer must make

What a derived column in this repository may assert about an item's state.
Three options, from the issue, with what each costs.

### (1) Keep `Open` hard-coded and rename the column to what it is

The header becomes `Note` (or `Implementation note`), the cells become
`note 2026-09-04` and `no note`, and nothing in the table reads as a status
claim. The gate keeps deriving the same fact — which note names this item, and
when it was last written — and stops labelling it with a word about completion.

- **Cost:** 57 cells, seven table headers, the explanatory section at the top of
  `docs/13-BACKLOG.md`, the two derived strings in `tools/claims_gate.py`, the
  check name and its docstring, and the six tests in
  `tests/test_claims_gate.py` that carry a derived string. Mechanical, one pass,
  no new concept.
- **Cost carried:** the table then states no status at all. A reader asking
  whether B-026 is done still has to open its note. That is the true answer
  today, and the column never contained a better one — but the rename makes the
  absence visible where the header used to paper over it.
- **What it settles:** the day an item closes, nothing in the table has to
  change and no gate has to be argued with. The closure is stated in the note,
  where a person wrote it.

### (2) Give the notes a closed vocabulary for state

An implementation note declares the state it leaves each item in, from a closed
set, and the gate derives the cell from that word rather than from the note's
existence. `Open` and `Closed` become things an author asserted deliberately,
and the gate transcribes rather than invents.

- **Cost:** a grammar and a vocabulary — where the word sits in the note header,
  what happens when a note names several items in different states (the
  2026-09-04 "B-026 corrections" note names one item; a note naming three would
  need a word each), and which note wins when two disagree (the latest, on the
  same rule the dates already use).
- **Cost that decides the option:** the fail-closed path. A note with no state
  word must derive *indeterminate*, never `Open`, or the vocabulary re-creates
  the current defect with more machinery — and a third value means the column is
  no longer two-valued, which is most of what makes it readable. And an author's
  `Closed` is a completion claim in a published document, so the vocabulary has
  to say what a note must carry alongside it: `DEFINITION_OF_DONE.md` requires
  objective evidence against the acceptance statement, and a word in a note
  header is not that evidence. Without that constraint, option (2) moves the
  invented claim from the gate to a one-word edit.
- **What it settles:** the only option that lets the table state a closure at
  all.

### (3) Drop the column; the notes are the only status

- **Cost:** it gives back exactly what #98 bought. The row and its state are
  separated again by the notes for other items, and nothing re-derives anything,
  so the next drift has nothing standing in front of it. The 57 cells come out
  and `check_backlog_status` comes out with them.
- **What it settles:** nothing overstates, because nothing states.

## Recommendation

**Option (1) now, with option (2) as the answer the first genuine closure
asks for.**

The column's content is already a note index. The only thing wrong with it is
the word at the top, and the cheapest honest change is to make the header say
what the cells contain. That costs one mechanical pass, keeps the derivation
that prevents drift, and removes the dated failure: after the rename, an item
closing does not collide with a gate at all, because the table stopped claiming
to know.

Option (2) is the better end state and the wrong thing to build first. A closed
vocabulary for state, with an indeterminate default and a rule about what a
`Closed` note must carry, is a design worth doing once there is one real closure
to validate it against — and today there is none: every implementation note ends
by saying which acceptance conditions its item still fails. Building the
vocabulary now means specifying a fail-closed path with no instance to test it
on, and the first item to close would be the first thing it ever ran against.
Its entry condition is that closure.

Option (3) is recommended against, because it trades an overstated header for a
return of the drift the column was added to stop. It is the maintainer's to take
anyway; this record says only what it costs.

## The status cell was read by position, and that is fixed here

`check_backlog_status` used to read the row's cell as the **last** split cell:

```python
cells = [cell.strip() for cell in row.group("rest").split("|")]
stated = cells[-1] if cells else ""
```

That examines exactly one cell by position and never establishes the row's
shape. The `Status` column is column seven of seven in every phase table, so the
last cell and the status cell coincided — until a row lost a column, and then
which cell was examined depended on *which* column it lost. Measured on this
tree:

- a row that drops the `Status` cell but keeps an empty one splits to
  `[…, '3d', '']` and is a finding;
- a row that drops the `Status` column outright splits to `[…, '3d']` and was a
  finding, but the wrong one: it named the Estimate as the item's status;
- a row that drops **any other** column — deleting only the Estimate from
  B-022's row, leaving six cells — left `Open — note 2026-09-04` in the last
  position, and `tools/claims_gate.py` reported `claims: clean` at exit 0 over a
  row whose shape it had not looked at.

The third case is not a message defect. It is an instance of the class
`docs/18-ASSURANCE-PROGRAM.md` names — *a check reports a clean result over
content it did not examine* — inside the check this record is about. Nothing
else in the tree examined a backlog row's column count, so nothing else would
have caught it.

So it is fixed here rather than deferred, because the fix is independent of all
three options: every option that keeps the column needs the cell taken by the
`Status` header's index, and option (3) deletes a correct check as easily as a
wrong one. `backlog_status_cells` now finds each phase table's header row, reads
the cell at the index of that table's `Status` header, and treats a row too
short to reach it — or a table with no such header — as examined-nothing rather
than as agreement. Four tests in `tests/test_claims_gate.py` stand on it, one per
case above plus the empty cell, and each fails against the previous code.

What that fix does **not** do is answer #111. The cell is now read from the right
column; what the word in it may assert is still the open question, and the three
options above are untouched by the change.

## What this does not decide

- **Whether any backlog item is closed.** None is, and nothing here changes that
  or licenses a gate to say otherwise.
- **What evidence closing an item requires.** `DEFINITION_OF_DONE.md` owns that,
  and option (2) would have to cite it rather than restate it.
- **The `Uncovered` entry that goes with the column.** `tools/claims_gate.py`
  already records that whether an item's derived status reflects its actual
  progress is a judgment the notes make and the gate does not. That entry stays
  true under every option and is re-worded, not removed, under (1).
- **Anything about the other derived claims** in `make claims`. Coverage floors,
  the ADR index, the schema count and the verify-stage lists are values
  re-derived from the repository, not statements about completion, and this
  record does not touch them.

## Rejected alternatives

- **Let the gate accept either `Open` or `Closed` and check neither.** A cell
  the gate does not derive is a cell that drifts, which is the whole reason the
  column is derived. An accepted-either-way column is decoration.
- **Derive `Closed` from a note that names no remaining acceptance condition.**
  It reads a completion claim out of the absence of a sentence — a gate
  inventing the strongest possible claim from silence, which is the inverse of
  this repository's invariant.
- **Derive the state from the GitHub issue tracker.** The gate makes no network
  call by design, and the CI checkout is shallow; a claim about an item's state
  that a clean clone cannot re-derive is one this gate does not make.
