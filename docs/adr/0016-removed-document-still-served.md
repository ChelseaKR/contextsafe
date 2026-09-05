# ADR 0016 — The removed business document the host still serves: purge request, or accept as public

Status: proposed; **no option below is chosen by this record.** The decision is the maintainer's alone and is recorded only when she records it
Date: 2026-09-05
Decision owner: the maintainer. No review by anyone else has happened, been requested, or been scheduled, and nothing here says otherwise
Review trigger: the decision itself; any change to the repository's visibility or ownership; any re-run of the checker whose verdict differs from the one dated below

## Context

[`docs/PUBLICATION-READINESS.md`](../PUBLICATION-READINESS.md) §6 records a
business document that a delete commit removed from every branch and that the
host still serves by explicit commit id, over the API and over the web, without
authentication. That section names the commit and the path; **this record
deliberately does not restate either, and does not describe the document's
contents.** §6 already says that printing the ids is itself part of the exposure
surface, and a second document repeating them would double the pointer without
adding anything a reader of §6 needs.

Three facts frame the decision, and all three are in the audit already:

- **A history rewrite does not reach it.** The commits are unreachable from any
  ref and a fresh clone cannot resolve them, which is exactly what made this
  look closed once. The host keeps unreachable objects and serves them by
  explicit id until it garbage-collects, and a repository owner cannot trigger
  that.
- **The exposure is competitive, not clinical or personal.** §6 established that
  the document carries no patient data, no customer name, no third-party
  confidential information, and no employer material. What is exposed is
  negotiating position. That does not make it harmless; it makes it a different
  kind of harm from the ones the rest of this corpus is built around, and it is
  why this is the maintainer's call alone rather than a governance question.
- **It was recorded as closed once, wrongly.** The 2026-08-29 update at the top
  of the audit is explicit: the `git show` in §6 fails for a reader who only
  cloned, that failure was read as absence, and the finding was briefly written
  down as closed while it was live. That is the defect class
  [`docs/18-ASSURANCE-PROGRAM.md`](../18-ASSURANCE-PROGRAM.md) names — a check
  reporting a clean result over content it did not examine — and the direction
  of the error is the dangerous one.

**Measured again on 2026-09-05, and this is a measurement rather than a memory.**
`tools/publication-exposure-check.sh`, run against the ref and path §6 names,
returned `verdict: STILL SERVED`: the contents API, the web blob view, and the
raw host each answered 200 at that ref, and each answered a positive control in
the same run, so the positives are not an artifact of a probe that was talking
to the wrong repository. The same run read `forks_count: 1` from the
repository's own metadata, where §6's recommendation was written when there were
none. Whether that fork serves this object is checkable with the same script by
pointing `--repo` at it; this record does not, and does not name it, because a
statement about somebody else's repository is an instance statement under
[publication policy §4](../17-PUBLICATION-POLICY.md) and would be one more
pointer besides.

Running it, with the two values read out of §6 rather than repeated here:

```sh
tools/publication-exposure-check.sh \
  --ref  <the commit §6 names> \
  --path <the path §6 names> \
  --output <a file to append the dated record to>
```

Exit 0 is every content surface absent, with the commit probe not resolving the
ref either and each surface serving its own positive control; 1 is still served;
2 is a run that established neither and must be written down as *not
established* rather than as closed; 64 is a usage error, which is a refusal to
start rather than a fourth answer. No probe of the subject reads a response
body — each is a status probe discarded to `/dev/null` — so running it cannot be
the thing that copies the content anywhere; one further request reads the
repository's own metadata for the fork count, and that body is scanned for a
single integer and never printed or recorded.

A detail that decides whether the tool can ever say "gone": the commits endpoint
answers **422**, not 404, for a ref it cannot resolve, so the commit probe is
read in its own vocabulary. Reading 422 as "could not classify" would have made
exit 0 unreachable against this host, and the closure criterion for option A
below unsatisfiable.

### What is no longer on the table

§6 laid out three options — publish as-is, rewrite history, or publish a fresh
repository from the current tree — and it laid them out while the repository was
private. Publication retired the second and third: the history is public, the
rewrite would not reach the objects the host serves by id, and a fresh
repository does not un-publish the one that exists. What is left is the pair
below.

There is also an asymmetry worth stating, because it makes one option cheaper
than it looks. [Publication policy §2](../17-PUBLICATION-POLICY.md) classifies
material by whether it shortens the work of someone trying to find trans and
nonbinary people in a health data extract; a pricing document is not method,
locator, or instance material in that sense, so the policy's classes do not
decide this and the policy's interim rule — Class 2 may not be published while
either governance chair seat is unfilled — has nothing to bite on. Meanwhile
[§7, item 3](../17-PUBLICATION-POLICY.md) already states this project's own
position on removal: git history, forks, archives, and search caches persist, removal is
a forward-looking signal rather than an undo, and this repository's audit is the
example it cites. The policy prefers "leave and own it" and reserves removal for
material whose continued presence is actively harmful.

## The decision the maintainer must make

Two options. The third row is not an option; it is what happens if no decision
is recorded, and it is priced here because doing nothing is also a choice with a
cost.

| Option | What it costs | What it buys | What it cannot reach |
|---|---|---|---|
| **A. Ask the host to purge the unreachable objects** | A support request that names the repository and the ids and, by asking, tells a third party which of this project's material its maintainer considers sensitive. No SLA and no guarantee: the host may decline, may require work first, and purging inside a fork network is a coordination problem rather than a button. Afterwards it has to be verified rather than believed, because "it has been purged" is the same class of claim that already went wrong here once | The content stops being served from this repository by explicit id, and the audit's printed ids stop resolving. This is the only option that changes what the host serves | A clone already taken; a fork; a search or proxy cache; a mirror; a web archive; anyone who has already read it |
| **B. Accept it as public and stop tracking it as an exposure** | The exposure §6 describes stays live and permanent, and every prospect can read the negotiating floor before the first conversation. It also costs a sentence that is uncomfortable to write: the audit's §6 and row 9 of its technical-gates table must say *accepted*, dated, and must not say *closed* | Nothing further to do, nothing to verify, no third party told what the maintainer considers sensitive, and no open finding that a reader has to re-derive. It converts an open exposure into a recorded decision, which is the state this corpus is built to hold | Exactly the same list as option A, plus the content itself, which stays served |
| *(no decision)* | The finding stays open and correct, and the checker has to be re-run for anyone to know whether it still holds. That is honest, and it is also the state in which the last wrong "closed" was written | Optionality: A stays available, and B remains available after A | The same list |

**Neither option reaches a fork, a clone somebody already took, a search or
proxy cache, a mirror, or a web archive.** That is not a detail of A; it is the
sentence that makes the two options closer together than they look. A buys the
removal of one serving path out of several, and buys it at an uncertain price;
B buys the end of the tracking. Nothing available buys the content back.

## Recommendation, which is not the decision

**B, on the evidence as it stands on 2026-09-05, with three conditions.**

The reasoning, so that disagreeing with it is cheap:

1. **A's cost is paid in a certainty it cannot deliver.** Its outcome is not the
   maintainer's to control, its timing is not either, and the best result it can
   produce is what the checker can then observe: *not served on these surfaces
   today*. The surfaces it cannot see are the same before and after.
2. **The harm is commercial, and the commercial answer is not technical.** If
   the figures are still the ones she intends to quote, the mitigation is to
   change what she quotes or to treat them as a public list price. If they are
   stale, the exposure is a footnote. Either way, a purge request does not
   change which of those two is true.
3. **This project's own policy already leans this way.** §7's third item
   prefers "leave and own it" and reserves removal for material whose continued
   presence is actively harmful. Nothing in §6 argues this content is that.
4. **An accepted exposure recorded as accepted is consistent with everything
   else here.** A repository whose gates exist to say what they did not examine
   should be able to say "this is public, deliberately". It is the "closed" that
   was not closed which broke faith with the reader, not the exposure.

The conditions, because B without them is just the no-decision row:

- **Record it as accepted, with the date, in §6 and in row 9 of the
  technical-gates table, using the word *accepted* and never the word
  *closed*.** They are not the same claim: the material is still served either
  way.
- **Re-run `tools/publication-exposure-check.sh` at the moment of the decision**
  and paste its dated record beside the entry, so what is recorded is a
  measurement of that day rather than a recollection of this one.
- **Leave the checker in the tree.** B stops the tracking; it does not stop the
  question being askable. If the answer ever changes — a purge somebody else
  triggers, a transfer, a takedown — a dated re-run is how anyone finds out.

**Choosing B does not consume A.** If the maintainer reads the negotiating floor
as actively costly, A remains available afterwards at the same price it costs
today, and the draft below is what she would send.

## Draft support request — NOT SENT

**This is a draft. Nobody has been contacted, no support request has been
opened, and no third party has been told anything about this repository by this
work.** It is here so that choosing A costs a copy-paste and a review rather
than a blank page. It names no content, because a request quoting the document
would put the content in a second place.

> Subject: Request to purge unreachable objects in a public repository
>
> Repository: `ChelseaKR/contextsafe` (public).
>
> A document was deleted from this repository in an ordinary delete commit. The
> commits containing it are unreachable from every ref, and a fresh clone cannot
> resolve them, but they are still served by explicit commit id through the
> REST contents API, the web blob view, and `raw.githubusercontent.com`. I am
> the owner and I am asking whether those unreachable objects can be purged from
> the repository and from its fork network.
>
> I can supply the commit ids and the path privately on request. I would like to
> know: (1) whether a purge is possible for this repository; (2) what I must do
> first, if anything, on my side; (3) whether the purge covers repositories in
> the same fork network, and what happens to a fork if it does not; and (4) how
> I can verify afterwards, since I have a check that queries the three serving
> surfaces and I would like to run it against a state you consider final.
>
> I understand that a purge cannot reach clones already taken, third-party
> mirrors, caches, or web archives, and I am not asking it to.

## Consequences

- **If A is chosen:** the request above is sent, the outcome is recorded with a
  date, and `tools/publication-exposure-check.sh` is re-run afterwards — a
  purge is not closed until a run says `NOT SERVED`, with its controls served
  and its commit probe no longer resolving the ref.
  §6 and row 9 of the technical-gates table are updated with that dated
  verdict, and this record is marked accepted, naming A.
- **If B is chosen:** §6 and row 9 gain a dated *accepted* line, the finding
  stops being tracked as open, and this record is marked accepted, naming B.
  Nothing is deleted and nothing is rewritten.
- **Either way, the checker stays.** It answers one question about a live host
  and it is not a gate over this tree, which is why it is not a `make` target
  and not part of `make verify`: it needs the network and a specific remote,
  `make verify` must stay exactly what CI runs, and its answer is stale the
  moment it prints.

## What this record does not do

- **It does not decide.** Neither option is chosen here, and no status anywhere
  in this repository has been moved to closed on the strength of it.
- **It does not contact anyone.** The draft above is unsent, and no support
  request, issue, or message exists.
- **It does not rewrite history**, remove any commit, or change what the host
  serves.
- **It does not restate the ref, the path, or anything the document contains**,
  and it prints no commit id the audit does not already print.
- **It claims no review.** No legal, security, clinical, community, or
  communications review of this exposure or of the draft above has happened.
- **It does not close §6.** §6's schemas half — the split `$id` identity — is a
  separate open item in that section and is untouched here.
