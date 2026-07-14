# Accessibility and internationalization

Status: v1 implementation requirements  
Owners: accessibility lead and language lead  
Standard: WCAG 2.2 AA for all rendered HTML

## 1. Users and contexts

Receipts are used by clinical, laboratory, technical, executive, security, and community reviewers. Users may navigate with a keyboard, screen reader, magnifier, high-contrast settings, speech input, or print; may have cognitive fatigue; and may not be fluent in English or health-IT terminology.

Accessibility is a release property, not a later interface polish task. A safety finding that cannot be perceived or understood is not delivered.

## 2. V1 surfaces

| Surface | V1 language | Accessibility contract |
|---|---|---|
| Static HTML receipt | complete EN and ES | WCAG 2.2 AA; works without script |
| Print stylesheet | complete EN and ES | preserves headings, statuses, URLs/IDs, and page breaks |
| JSON receipt | locale-neutral codes plus localized display catalog version | documented schema; no meaning only in translated prose |
| CLI help/errors | complete EN; P1 complete ES | keyboard/terminal native, no color dependence, JSON errors |
| Execution guide | EN; P1 ES | semantic Markdown/HTML and accessible documents |
| Legal/contract artifacts | professionally prepared per engagement | outside software locale promise |

PDF is not a v1 product output. Print-to-PDF may be used by a customer, but ContextSafe does not claim that an arbitrary generated PDF is accessible.

## 3. WCAG 2.2 AA requirements

- Semantic landmarks and one hierarchical H1.
- Skip link to results.
- Logical heading order and document title naming partner profile, run, and locale.
- Native tables with captions, column/row headers, and simple structures; provide a linear finding list for complex comparisons.
- Status always expressed by text and icon shape, never color alone.
- Minimum 4.5:1 text and 3:1 large-text/non-text contrast.
- Visible focus that is not obscured.
- Complete keyboard operation with no traps.
- Reflow at 320 CSS pixels and 400% zoom without loss or two-dimensional scrolling except genuinely tabular content.
- Text spacing overrides without clipping.
- Target size at least 24 by 24 CSS pixels where pointer targets exist.
- Consistent help and identification.
- Error messages name the field, problem, and safe recovery.
- Language of page and language changes marked.
- Motion absent; no time limits, autoplay, blinking, or flashing.
- External links labeled; repeated raw hashes can be shortened visually while full values remain accessible.
- SVG or icon status has hidden decorative graphics and visible text.
- Print output repeats table headers and does not orphan a finding from its evidence summary.

Because output is static, scripts are optional enhancement only. Verification, filters, or disclosure widgets must have fully available no-script equivalents.

## 4. Information architecture

Receipt order:

1. Scope and limitations.
2. Release-decision summary.
3. Coverage and unresolved gaps.
4. Critical/high findings.
5. All findings and outcomes.
6. Evidence/provenance.
7. Reviews and dispositions.
8. Versions, signatures, and verification instructions.

Never lead with a percentage that hides blocked or indeterminate results. Show counts for pass, fail, indeterminate, blocked, not applicable, and unobserved. No red/green-only “score.”

## 5. Language and content rules

- Use “name to use,” not “preferred name,” when referring to the Gender Harmony concept.
- Use “pronouns,” not “preferred pronouns.”
- Use “transgender and nonbinary people” unless a reviewer selects another self-description.
- Describe data, not identity assumptions: “RSG X was observed” rather than “patient is X.”
- Do not use “biological sex,” “born a man/woman,” “normal patient,” “gender change,” or anatomy as a proxy for identity.
- Distinguish “legal test name,” “name to use,” and “prior name” by context.
- Use “reference interval” for the laboratory artifact and explain “reference range” as a familiar synonym.
- Explain GI, SPCU, RSG, NtU, EHR, LIS, FHIR, and HL7 on first use.
- Use direct status language: “Failed: the returned result had no required abnormal flag.”
- Separate observed fact, expected behavior, clinical rationale, and limitation.
- Avoid blame: systems and configured workflows fail assertions, not individual registration staff.

The bilingual glossary is governed with the case pack. Community reviewers can block stigmatizing or misleading language.

## 6. EN/ES architecture

- Source strings use stable semantic keys, not English prose as keys.
- ICU/MessageFormat-compatible plural/select rules.
- BCP 47 locales en-US and es-US in v1.
- Dates use unambiguous localized long form; machine timestamps remain ISO 8601.
- Numbers and units remain clinically exact; localization does not change decimal semantics in canonical JSON.
- Status and clinical codes remain locale-neutral identifiers with localized labels.
- Placeholders are named and type checked.
- Catalog parity, placeholder parity, and no-untranslated-key checks block release.
- Pseudolocale expands text by at least 35%, adds diacritics, and exposes concatenation/layout defects.
- No string concatenation or hard-coded user-facing strings.

Spanish is human-translated by a healthcare-qualified translator and independently reviewed by a Spanish-speaking trans/community reviewer. Machine translation may assist drafting only if contractually permitted and is never the released authority.

## 7. Accessibility test matrix

Automated on every change:

- axe-core: zero serious/critical and zero known WCAG 2.2 AA violations.
- pa11y or equivalent on summary, all-status, long-evidence, and ES fixtures.
- HTML validity and heading/table/link checks.
- catalog parity and pseudolocale.
- contrast and no-color snapshot assertions.
- print stylesheet structural check.

Manual before pilot and every major/minor release:

| Environment | Tasks |
|---|---|
| NVDA + current Firefox on Windows | scope, jump to high finding, inspect evidence, read table, verify receipt |
| VoiceOver + current Safari on macOS | same workflow plus rotor headings/landmarks |
| Keyboard-only, Windows and macOS | all links/disclosures; focus order; no traps |
| 400% zoom and 320 CSS px | complete receipt without lost content |
| Windows High Contrast | distinguish every status and focus state |
| EN and ES cognitive walkthrough | each participant completes four core tasks and five questions; each locale cohort collectively covers every primary persona |
| Print preview | limitations, finding IDs, statuses, and URLs remain associated |

If customer policy requires JAWS, add it before that engagement; it is not a reason to skip NVDA/VoiceOver baseline testing.

## 8. Acceptance targets

- 100% P0 WCAG checks pass.
- Zero open severity-1 or severity-2 accessibility defects.
- At least 90% of participant-task attempts succeed independently in each locale; the denominator is participant × four predeclared core tasks, and no core task may fail for more than one participant in a locale.
- Median task completion within two minutes for a high-priority finding.
- At least 90% of the participant × five predeclared comprehension answers are correct in each locale, and every participant answers at least 4/5 correctly. Recruit at least five qualified participants per locale; each locale cohort collectively covers PER-01–PER-07, with one participant covering at most two roles only when they genuinely perform both. Record role, locale, assistive-technology needs, attempts, answers, help requested, and exclusions before scoring.
- Zero placeholder or untranslated-key defects in released EN/ES receipts.

An accessibility waiver requires user impact, workaround, owner, expiry, and approval from the accessibility lead and clinical safety chair. No waiver is allowed for inability to perceive status, limitation, evidence, or unresolved risk.

## 9. Community review

At least two trans/nonbinary reviewers inspect:

- case names and synthetic identity presentation;
- terms for declined, unknown, absent, and unsupported;
- deadname exposure scenarios;
- receipt limitations and claim wording;
- Spanish glossary where language expertise applies;
- whether any field or scenario encourages unnecessary collection.

Feedback is logged by issue, decision, rationale, version, and compensation. Sensitive reviewer identity is not exposed in public artifacts without consent.

## 10. Maintenance

Re-run automated gates on every template/catalog change and manual review on every major receipt restructure. Review terminology every six months and when HL7 artifacts or community guidance change. Correct harmful language as a safety patch and notify affected customers when prior receipts could be misunderstood.
