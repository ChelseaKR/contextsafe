"""The rendered receipt page: what it must contain, and what it must not.

The page is the first thing in this repository a person rather than a program
reads, so the assertions here are about a reader: every hash and mandated
limitation survives the render, status is never colour alone, an unreviewed
translation is visibly unreviewed and shows its original, and nothing on the
page reaches the network or runs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from html import escape
from pathlib import Path
from typing import Any

import pytest

from contextsafe import html_receipt
from contextsafe.canonical import canonical_json, sha256_json
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import evaluate
from contextsafe.html_receipt import PAGE_KIND, render_receipt_page
from contextsafe.i18n import SOURCE_LOCALE, load_catalog, source_catalog
from contextsafe.models import DivergenceStatus, EvidenceState, OutcomeReason
from contextsafe.receipt import build_receipt_document
from contextsafe.validation import parse_bundle

FAULTS = Path(__file__).resolve().parent / "fixtures" / "seeded-faults"

_STATUSES = ("pass", "fail", "indeterminate", "blocked", "not_applicable")

_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "schemas"
    / "contextsafe-receipt-v0.3.schema.json"
)

_UNNEEDED_RESULT_FIELDS = (
    "evidence_sha256s",
    "expected_sha256",
    "observed_sha256s",
    "rule_version",
)
"""Result fields the JSON carries and the page does not present (A-036)."""


def _sealed(document: dict[str, Any]) -> dict[str, Any]:
    """Recompute ``payload_sha256`` after a test edits the payload.

    The renderer refuses a document whose hash does not cover its payload, so a
    test that edits the payload to exercise some other refusal has to re-seal
    it first, or every such test would be testing the hash check.
    """

    document["payload_sha256"] = sha256_json(document["payload"])
    return document


@pytest.fixture
def document(
    case_json: dict[str, Any],
    observations_json: dict[str, Any],
    rules_json: dict[str, Any],
) -> dict[str, Any]:
    """Return the reference receipt document the page is rendered from."""

    bundle = parse_bundle(case_json, observations_json, rules_json)
    return build_receipt_document(bundle, evaluate(bundle))


def test_the_page_is_script_free_and_self_contained(document: dict[str, Any]) -> None:
    """No script, no handler attribute, and nothing fetched from anywhere."""

    page = render_receipt_page(_sealed(document))
    lowered = page.lower()
    assert "<script" not in lowered
    assert "javascript:" not in lowered
    assert re.search(r"\son[a-z]+\s*=", lowered) is None
    assert "http://" not in lowered
    assert "https://" not in lowered
    assert "<link" not in lowered
    assert "<iframe" not in lowered
    assert "<img" not in lowered
    assert "url(" not in lowered


def test_the_page_names_the_payload_it_was_rendered_from(
    document: dict[str, Any],
) -> None:
    """A gate must be able to prove which receipt it audited."""

    page = render_receipt_page(_sealed(document))
    assert f'data-cs-page="{PAGE_KIND}"' in page
    assert f'data-cs-payload-sha256="{document["payload_sha256"]}"' in page
    assert f'data-cs-case-id="{document["payload"]["case_id"]}"' in page


def test_every_hash_and_limitation_survives_the_render(
    document: dict[str, Any],
) -> None:
    """The renderer may reformat the receipt; it may not drop part of it."""

    page = render_receipt_page(_sealed(document))
    payload = document["payload"]
    for value in payload["hashes"].values():
        assert value in page
    assert document["payload_sha256"] in page
    for limitation in payload["limitations"]:
        assert limitation in page
    for result in payload["results"]:
        assert result["rule_id"] in page


def test_status_is_never_colour_alone(document: dict[str, Any]) -> None:
    """Every status cell carries its word and a symbol, not just a class."""

    page = render_receipt_page(_sealed(document))
    catalog = source_catalog()
    cells = re.findall(r'data-cs-status="([a-z_]+)">(.*?)</t[hd]>', page, flags=re.S)
    assert cells
    for status, markup in cells:
        assert status in _STATUSES
        assert 'class="status-symbol"' in markup
        assert catalog.message(f"status.{status}").text in markup
    stripped = re.sub(r"<style>.*?</style>", "", page, flags=re.S)
    for status in _STATUSES:
        assert catalog.message(f"status.{status}").text in stripped


def _print_block(page: str) -> str:
    style = re.search(r"<style>(.*?)</style>", page, flags=re.S)
    assert style is not None
    print_block = re.search(r"@media print \{(.*?)\n\}", style.group(1), flags=re.S)
    assert print_block is not None
    return print_block.group(1)


def test_the_stylesheet_covers_print_and_never_hides_a_disclosure(
    document: dict[str, Any],
) -> None:
    """The page has to survive being printed, disclosures included."""

    page = render_receipt_page(_sealed(document))
    body = _print_block(page)
    assert "display: none" not in body.replace(".skip-link { display: none; }", "")
    assert "visibility: hidden" not in body
    assert ".notice" in body


def test_print_repeats_table_headers_and_orphans_nothing(
    document: dict[str, Any],
) -> None:
    """B-038: headers repeat, and a finding stays with its reason.

    Each table has a ``<thead>`` for the header group to repeat from; a result
    row, a limitation with its source original, and the translation notice are
    each kept on one page; a heading or caption is kept with what follows it.
    """

    page = render_receipt_page(_sealed(document), locale="es-US")
    assert page.count("<table>") == page.count("<thead>") == 4
    body = _print_block(page)
    assert "thead { display: table-header-group; }" in body
    keep_together = re.search(r"^\s*([^{\n]+)\{ break-inside: avoid; \}", body, re.M)
    assert keep_together is not None
    kept = {part.strip() for part in keep_together.group(1).split(",")}
    assert {"tr", "li", ".notice", ".source-text"} <= kept
    keep_with_next = re.search(r"^\s*([^{\n]+)\{ break-after: avoid; \}", body, re.M)
    assert keep_with_next is not None
    heads = {part.strip() for part in keep_with_next.group(1).split(",")}
    assert {"h1", "h2", "h3", "caption"} <= heads


def test_a_reviewed_locale_carries_no_translation_notice(
    document: dict[str, Any],
) -> None:
    """A notice that fires when it should not is a notice readers ignore."""

    page = render_receipt_page(_sealed(document), locale=SOURCE_LOCALE)
    assert 'data-cs-notice="machine-translation"' not in page
    assert 'data-cs-translation-review="source"' in page
    assert 'data-cs-review="machine"' not in page


def test_an_unreviewed_locale_says_so_in_both_languages(
    document: dict[str, Any],
) -> None:
    """The reader who cannot trust the translation gets the notice anyway."""

    page = render_receipt_page(_sealed(document), locale="es-US")
    assert 'data-cs-notice="machine-translation"' in page
    assert 'data-cs-translation-review="machine"' in page
    spanish = load_catalog("es-US").message("translation.unreviewed.body").text
    english = source_catalog().message("translation.unreviewed.body").text
    assert spanish in page
    assert english in page
    assert 'lang="es-US"' in page
    assert 'lang="en-US"' in page


def test_every_mandated_disclosure_shows_its_original_when_unreviewed(
    document: dict[str, Any],
) -> None:
    """A machine translation of a safety sentence never stands alone."""

    page = render_receipt_page(_sealed(document), locale="es-US")
    for limitation in document["payload"]["limitations"]:
        assert limitation in page
    spanish = load_catalog("es-US")
    for index in range(1, 5):
        assert spanish.message(f"limitation.{index}").text in page
    assert page.count('class="source-text"') >= len(document["payload"]["limitations"])


def test_unreviewed_strings_are_marked_individually(
    document: dict[str, Any],
) -> None:
    """Per-string marking, so one sentence can be judged on its own."""

    page = render_receipt_page(_sealed(document), locale="es-US")
    assert page.count('data-cs-review="machine"') > 20
    assert page.count('data-cs-review="source"') >= 5


def test_receipt_wording_with_no_catalog_entry_is_labelled(
    document: dict[str, Any],
) -> None:
    """A reworded limitation loses its translation rather than keeping a stale one."""

    document["payload"]["limitations"] = ["A limitation nobody has translated."]
    page = render_receipt_page(_sealed(document), locale="es-US")
    assert "A limitation nobody has translated." in page
    assert (
        load_catalog("es-US")
        .message("translation.unavailable")
        .text.replace("{locale}", "en-US")
        in page
    )


def test_the_render_is_deterministic_in_process(document: dict[str, Any]) -> None:
    """Same receipt, same locale, same bytes."""

    assert render_receipt_page(
        _sealed(document), locale="es-US"
    ) == render_receipt_page(document, locale="es-US")


def test_the_render_is_deterministic_across_environments(
    tmp_path: Path, document: dict[str, Any]
) -> None:
    """Time zone, locale, and hash seed must not reach the rendered bytes."""

    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(canonical_json(document).encode("utf-8") + b"\n")
    outputs: list[bytes] = []
    environments = (
        {"TZ": "UTC", "LC_ALL": "C", "PYTHONHASHSEED": "0"},
        {"TZ": "Pacific/Kiritimati", "LC_ALL": "tr_TR.UTF-8", "PYTHONHASHSEED": "1"},
        {"TZ": "America/Sao_Paulo", "LC_ALL": "es_ES.UTF-8", "PYTHONHASHSEED": "2"},
    )
    for overrides in environments:
        environ = {**os.environ, **overrides}
        target = tmp_path / f"page-{overrides['PYTHONHASHSEED']}.html"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "contextsafe",
                "render",
                "--receipt",
                str(receipt),
                "--lang",
                "es-US",
                "--output",
                str(target),
            ],
            check=True,
            capture_output=True,
            env=environ,
        )
        assert completed.stdout == b""
        outputs.append(target.read_bytes())
    assert len(set(outputs)) == 1
    assert outputs[0].startswith(b"<!DOCTYPE html>")


def test_the_page_escapes_receipt_values(document: dict[str, Any]) -> None:
    """Receipt content is data, and a page must not let it become markup."""

    document["payload"]["case_id"] = '<script>alert("x")</script>'
    page = render_receipt_page(_sealed(document))
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ({"payload": []}, "invalid_receipt_document"),
        ({"envelope": "no"}, "invalid_receipt_document"),
        ({"payload_sha256": 7}, "invalid_receipt_document"),
        ({"schema_version": None}, "invalid_receipt_document"),
    ],
)
def test_a_malformed_document_fails_closed(
    document: dict[str, Any], mutation: dict[str, Any], code: str
) -> None:
    """The renderer never guesses at a document it does not understand."""

    document.update(mutation)
    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(document)
    assert excinfo.value.code == code


def test_a_signed_looking_envelope_is_refused(document: dict[str, Any]) -> None:
    """No signing path exists, so no page may look like it verified one."""

    document["envelope"]["signature_status"] = "signed"
    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(_sealed(document))
    assert excinfo.value.code == "invalid_receipt_document"


def test_a_trusted_time_claim_is_refused(document: dict[str, Any]) -> None:
    """Nor may a page imply the timestamp came from anywhere trustworthy."""

    document["envelope"]["trusted_time"] = True
    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(_sealed(document))
    assert excinfo.value.code == "invalid_receipt_document"


def test_a_declared_timestamp_renders_as_declared(document: dict[str, Any]) -> None:
    """The envelope is shown, and shown as untrusted."""

    document["envelope"]["claimed_generated_at"] = "2026-08-15T00:00:00Z"
    page = render_receipt_page(_sealed(document))
    assert "2026-08-15T00:00:00Z" in page
    assert source_catalog().message("envelope.explainer").text in page


@pytest.mark.parametrize("field", ["status", "concept", "checkpoint", "reason"])
@pytest.mark.parametrize("value", ["invented", "CSYN-SECRET-NAME"])
def test_an_unpublished_enum_value_fails_closed(
    document: dict[str, Any], field: str, value: str
) -> None:
    """A value with no published label must stop the page, not be printed raw.

    The rejection is the renderer's own, by pointer, before the value could
    become a catalog key: the catalog's unknown-key error names the key it was
    asked for, and that path would carry the value onto stderr.
    """

    document["payload"]["results"][0][field] = value
    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(_sealed(document))
    assert excinfo.value.code == "invalid_receipt_document"
    assert excinfo.value.path == f"$.payload.results[0].{field}"
    _assert_never_named(excinfo.value, value)


def _assert_never_named(error: ContextSafeError, value: str) -> None:
    assert value not in error.path
    assert value not in error.message
    assert value not in str(error)
    assert value not in canonical_json(error.to_dict())


def test_a_non_boolean_scope_or_count_fails_closed(document: dict[str, Any]) -> None:
    """Scope and summary are typed; a string there is a contract break."""

    document["payload"]["scope"]["synthetic_fixture_only"] = "yes"
    with pytest.raises(ContextSafeError):
        render_receipt_page(_sealed(document))
    document["payload"]["scope"]["synthetic_fixture_only"] = True
    document["payload"]["summary"]["pass"] = "many"  # noqa: S105 - not a password
    with pytest.raises(ContextSafeError):
        render_receipt_page(_sealed(document))


@pytest.mark.parametrize("count", [1, "many"])
def test_an_unpublished_summary_key_is_refused_without_being_named(
    document: dict[str, Any], count: object
) -> None:
    """A summary key is receipt content and may not enter a pointer unchecked.

    The key is held to the published status set before either the count check
    or the label lookup can put it into an error's path.
    """

    document["payload"]["summary"]["CSYN-SECRET-NAME"] = count
    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(_sealed(document))
    assert excinfo.value.code == "invalid_receipt_document"
    assert excinfo.value.path == "$.payload.summary"
    _assert_never_named(excinfo.value, "CSYN-SECRET-NAME")


def test_rendering_a_mismatched_catalog_is_refused(document: dict[str, Any]) -> None:
    """Auditing one catalog and rendering another is the bug this prevents."""

    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(
            document, locale="es-US", catalog=load_catalog(SOURCE_LOCALE)
        )
    assert excinfo.value.code == "catalog_locale_mismatch"


def test_the_cli_renders_and_reports_a_bad_receipt(
    tmp_path: Path, document: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """``contextsafe render`` is the surface a first-time reader uses."""

    from contextsafe.cli import EXIT_CONTRACT_ERROR, EXIT_SUCCESS, main

    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(canonical_json(document).encode("utf-8") + b"\n")
    target = tmp_path / "page.html"
    assert main(["render", "--receipt", str(receipt), "--output", str(target)]) == (
        EXIT_SUCCESS
    )
    assert target.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")

    not_an_object = tmp_path / "list.json"
    not_an_object.write_text("[]", encoding="utf-8")
    assert main(["render", "--receipt", str(not_an_object)]) == EXIT_CONTRACT_ERROR
    assert "invalid_receipt_document" in capsys.readouterr().err


@pytest.mark.parametrize("locale", ["en-US", "es-US"])
@pytest.mark.parametrize("reason", list(OutcomeReason))
def test_every_published_reason_has_a_label_in_every_shipped_locale(
    document: dict[str, Any], locale: str, reason: OutcomeReason
) -> None:
    """A reason the receipt contract admits must render, never fail closed.

    The renderer refuses a reason with no catalog entry, which is right for an
    unpublished value and would be a defect for a published one: every member
    of ``OutcomeReason`` therefore needs a label in every catalog that ships.
    """

    document["payload"]["results"][0]["reason"] = reason.value
    page = render_receipt_page(_sealed(document), locale=locale)
    label = load_catalog(locale).message(f"reason.{reason.value}").text
    assert escape(label) in page
    assert reason.value not in page


# --- the divergence section (B-031) -----------------------------------------


def _fault_document(name: str) -> dict[str, Any]:
    raw = json.loads((FAULTS / f"{name}.json").read_text(encoding="utf-8"))
    bundle = parse_bundle(raw["case"], raw["observations"], raw["rules"])
    return build_receipt_document(bundle, evaluate(bundle))


def _divergence_section(page: str) -> str:
    start = page.index('<section aria-labelledby="divergence">')
    return page[start : page.index("</section>", start)]


def test_the_divergence_section_renders_every_field_and_boundary(
    document: dict[str, Any],
) -> None:
    """One row per concept in each table, one evidence cell per boundary."""

    section = _divergence_section(render_receipt_page(_sealed(document)))
    catalog = source_catalog()
    assert catalog.message("section.divergence.heading").text in section
    assert catalog.message("divergence.explainer").text in section
    assert section.count("<tr>") == 2 * 5 + 2
    assert section.count("data-cs-evidence=") == 20
    assert section.count("data-cs-divergence=") == 10
    for checkpoint in ("registration", "ehr", "interface", "lis_return"):
        assert catalog.message(f"checkpoint.{checkpoint}").text in section
    for concept in document["payload"]["divergence"]["concepts"]:
        assert catalog.message(f"concept.{concept['concept']}").text in section
    assert 'data-cs-evidence="observed"' in section
    assert 'data-cs-evidence="unobserved"' in section
    assert 'data-cs-divergence="agreed_where_observed"' in section
    assert 'data-cs-divergence="unobserved"' in section


def test_an_unobserved_boundary_is_never_named_on_the_page() -> None:
    """F-025 rendered: the divergence reads as between the observed sides."""

    page = render_receipt_page(_fault_document("F-025"))
    section = _divergence_section(page)
    catalog = source_catalog()
    registration = catalog.message("checkpoint.registration").text
    interface = catalog.message("checkpoint.interface").text
    ehr = catalog.message("checkpoint.ehr").text
    assert f"Diverged at {interface}" in section
    assert f"Diverged between {registration} and {interface}" in section
    assert f"Diverged at {ehr}" not in section
    assert f"between {ehr}" not in section
    assert f"and {ehr}" not in section
    first_table = section[section.index("<table>", section.index("</table>")) :]
    assert 'data-cs-divergence="diverged"' in first_table


def test_an_omitted_boundary_reads_as_not_observed_never_as_agreement() -> None:
    """F-023 rendered: the laboratory return is not observed, and says so."""

    page = render_receipt_page(_fault_document("F-023"))
    section = _divergence_section(page)
    catalog = source_catalog()
    assert catalog.message("evidence.unobserved").text in section
    assert (
        catalog.message("divergence.from_expected.agreed_where_observed").text
        in section
    )
    lis = catalog.message("checkpoint.lis_return").text
    assert f"Diverged at {lis}" not in section
    assert f"and {lis}" not in section


def test_an_ambiguous_boundary_renders_as_indeterminate(
    document: dict[str, Any],
) -> None:
    entry = document["payload"]["divergence"]["concepts"][0]
    entry["checkpoints"][1]["state"] = "ambiguous"
    entry["from_expected"] = {"at": "ehr", "status": "indeterminate"}
    entry["from_previous"] = {"after": None, "at": "ehr", "status": "indeterminate"}
    section = _divergence_section(render_receipt_page(_sealed(document)))
    catalog = source_catalog()
    ehr = catalog.message("checkpoint.ehr").text
    assert catalog.message("evidence.ambiguous").text in section
    assert (
        catalog.message(
            "divergence.indeterminate.at",
        ).text.replace("{checkpoint}", ehr)
        in section
    )
    entry["from_previous"] = {
        "after": "registration",
        "at": "ehr",
        "status": "indeterminate",
    }
    section = _divergence_section(render_receipt_page(_sealed(document)))
    assert 'data-cs-divergence="indeterminate"' in section
    assert f"and {ehr}" in section


def test_the_divergence_explainer_shows_its_original_when_unreviewed(
    document: dict[str, Any],
) -> None:
    """The sentence that says what is never blamed is safety text."""

    section = _divergence_section(
        render_receipt_page(_sealed(document), locale="es-US")
    )
    assert load_catalog("es-US").message("divergence.explainer").text in section
    assert source_catalog().message("divergence.explainer").text in section
    assert 'class="source-text"' in section
    assert section.count('data-cs-review="machine"') > 20


@pytest.mark.parametrize("locale", ["en-US", "es-US"])
def test_every_evidence_state_and_divergence_status_has_a_label(
    document: dict[str, Any], locale: str
) -> None:
    """The renderer refuses an unlabelled value, so every published one needs one."""

    catalog = load_catalog(locale)
    entry = document["payload"]["divergence"]["concepts"][0]
    for state in EvidenceState:
        entry["checkpoints"][0]["state"] = state.value
        page = render_receipt_page(_sealed(document), locale=locale)
        assert escape(catalog.message(f"evidence.{state.value}").text) in page
    for status in DivergenceStatus:
        located = status in (DivergenceStatus.DIVERGED, DivergenceStatus.INDETERMINATE)
        entry["from_expected"] = {
            "at": "interface" if located else None,
            "status": status.value,
        }
        entry["from_previous"] = {
            "after": "registration" if located else None,
            "at": "interface" if located else None,
            "status": status.value,
        }
        page = render_receipt_page(_sealed(document), locale=locale)
        assert f'data-cs-divergence="{status.value}"' in page


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda entry: entry["checkpoints"][0].update({"state": "assumed"}),
            "invalid_receipt_document",
        ),
        (
            lambda entry: entry["checkpoints"][0].update({"state": "agreed"}),
            "invalid_receipt_document",
        ),
        (
            lambda entry: entry["from_expected"].update({"status": "passed"}),
            "invalid_receipt_document",
        ),
        (
            lambda entry: entry["from_previous"].update({"status": "inferred"}),
            "invalid_receipt_document",
        ),
        (
            lambda entry: entry["from_expected"].update({"at": "display"}),
            "invalid_receipt_document",
        ),
        (
            lambda entry: entry["from_previous"].update({"after": "gap"}),
            "invalid_receipt_document",
        ),
        (
            lambda entry: entry["from_previous"].update({"at": "display"}),
            "invalid_receipt_document",
        ),
        (
            lambda entry: entry.update({"concept": "display"}),
            "invalid_receipt_document",
        ),
        (lambda entry: entry["checkpoints"].reverse(), "invalid_receipt_document"),
        (lambda entry: entry["checkpoints"].pop(), "invalid_receipt_document"),
        (
            lambda entry: entry.update({"checkpoints": "none"}),
            "invalid_receipt_document",
        ),
        (
            lambda entry: entry.update({"from_expected": None}),
            "invalid_receipt_document",
        ),
    ],
)
def test_an_unpublished_divergence_value_fails_closed(
    document: dict[str, Any], mutate: Any, code: str
) -> None:
    """The page never prints a state, status, or boundary it cannot name."""

    mutate(document["payload"]["divergence"]["concepts"][0])
    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(_sealed(document))
    assert excinfo.value.code == code
    for word in ("display", "gap", "assumed", "agreed", "passed", "inferred"):
        _assert_never_named(excinfo.value, word)


_LEAK = "CSYN-SECRET-NAME"
"""A synthetic-namespace token shaped like the free text a receipt must not carry."""


def _put_token(field: str) -> Any:
    def mutate(payload: dict[str, Any]) -> None:
        divergence = payload["divergence"]
        if field == "pathway":
            divergence["pathway"][0] = _LEAK
        elif field == "concept":
            divergence["concepts"][0]["concept"] = _LEAK
        elif field == "from_previous.after":
            divergence["concepts"][0]["from_previous"].update(
                {"after": _LEAK, "at": "interface", "status": "diverged"}
            )
        else:
            scope, _, name = field.partition(".")
            divergence["concepts"][0][scope][name] = _LEAK
            divergence["concepts"][0][scope]["status"] = "diverged"

    return mutate


@pytest.mark.parametrize(
    ("field", "pointer"),
    [
        ("pathway", "$.payload.divergence.pathway[0]"),
        ("concept", "$.payload.divergence.concepts[0].concept"),
        ("from_expected.at", "$.payload.divergence.concepts[0].from_expected.at"),
        ("from_previous.at", "$.payload.divergence.concepts[0].from_previous.at"),
        (
            "from_previous.after",
            "$.payload.divergence.concepts[0].from_previous.after",
        ),
    ],
)
def test_a_rejected_divergence_value_never_reaches_the_error(
    tmp_path: Path,
    document: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    field: str,
    pointer: str,
) -> None:
    """Free text in a boundary or concept field is refused by pointer only.

    Every site that composes a catalog key from receipt content checks the
    value against the published set first; the safety-negative here is that
    the token appears in neither the error object nor the CLI's stderr.
    """

    from contextsafe.cli import EXIT_CONTRACT_ERROR, main

    _put_token(field)(document["payload"])
    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(_sealed(document))
    assert excinfo.value.code == "invalid_receipt_document"
    assert excinfo.value.path == pointer
    _assert_never_named(excinfo.value, _LEAK)

    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(canonical_json(document).encode("utf-8") + b"\n")
    assert main(["render", "--receipt", str(receipt)]) == EXIT_CONTRACT_ERROR
    captured = capsys.readouterr()
    assert _LEAK not in captured.err
    assert _LEAK not in captured.out
    assert json.loads(captured.err)["error"]["code"] == "invalid_receipt_document"


def test_a_receipt_without_a_divergence_section_is_refused(
    document: dict[str, Any],
) -> None:
    del document["payload"]["divergence"]
    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(_sealed(document))
    assert excinfo.value.code == "invalid_receipt_document"
    assert excinfo.value.path == "$.payload"


def test_a_hash_that_does_not_cover_the_payload_is_refused(
    document: dict[str, Any],
) -> None:
    """A-036: the page's hash must be the hash of what is under it.

    The document's own ``payload_sha256`` is not trusted; it is recomputed.
    A payload edited after sealing, or a hash edited on its own, is a refusal
    rather than a page that vouches for content it does not cover.
    """

    document["payload"]["summary"]["pass"] = 4
    document["payload"]["summary"]["fail"] = 1
    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(document)
    assert excinfo.value.code == "receipt_payload_hash_mismatch"
    assert excinfo.value.path == "$.payload_sha256"
    resealed = _sealed(document)
    assert "1" in render_receipt_page(resealed)
    resealed["payload_sha256"] = "0" * 64
    with pytest.raises(ContextSafeError) as again:
        render_receipt_page(resealed)
    assert again.value.code == "receipt_payload_hash_mismatch"


@pytest.mark.parametrize(
    "pointer",
    [
        (),
        ("envelope",),
        ("payload",),
        ("payload", "hashes"),
        ("payload", "scope"),
        ("payload", "summary"),
        ("payload", "results", 0),
    ],
)
def test_a_field_the_contract_does_not_publish_is_refused(
    document: dict[str, Any], pointer: tuple[str | int, ...]
) -> None:
    """F-027: an unnecessary field is never rendered around, only refused.

    The injected value is a synthetic token that must appear neither on any
    page nor in the rejection, which names a location and never content.
    """

    target: Any = document
    for step in pointer:
        target = target[step]
    target["legal_name"] = "CSYN-FIXTURE-LEGAL-NAME"
    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(_sealed(document))
    assert excinfo.value.code == "invalid_receipt_document"
    assert "CSYN" not in str(excinfo.value)
    assert "legal_name" not in str(excinfo.value)


def test_a_missing_contract_field_is_refused_too(document: dict[str, Any]) -> None:
    """Closed means exactly the published set, not a subset of it."""

    del document["payload"]["results"][0]["rule_version"]
    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(_sealed(document))
    assert excinfo.value.code == "invalid_receipt_document"
    assert excinfo.value.path == "$.payload.results[0]"


def test_a_summary_missing_a_status_is_refused(document: dict[str, Any]) -> None:
    """A status silently dropped from the summary would read as zero."""

    del document["payload"]["summary"]["blocked"]
    with pytest.raises(ContextSafeError) as excinfo:
        render_receipt_page(_sealed(document))
    assert excinfo.value.code == "invalid_receipt_document"
    assert excinfo.value.path == "$.payload.summary"


def test_result_fields_the_page_does_not_need_never_reach_it(
    document: dict[str, Any],
) -> None:
    """A-036: expected, observed, and evidence hashes stay in the JSON.

    Each is replaced with a distinct synthetic digest so the assertion cannot
    pass because two hashes happened to coincide with one the page does show.
    """

    for index, result in enumerate(document["payload"]["results"]):
        result["expected_sha256"] = f"{index:02d}e" * 21 + "e"
        result["observed_sha256s"] = [f"{index:02d}b" * 21 + "b"]
        result["evidence_sha256s"] = [f"{index:02d}c" * 21 + "c"]
        result["rule_version"] = f"9.{index}.9"
    page = render_receipt_page(_sealed(document))
    for result in document["payload"]["results"]:
        for name in _UNNEEDED_RESULT_FIELDS:
            values = result[name] if isinstance(result[name], list) else [result[name]]
            for value in values:
                assert value not in page, name
        assert result["rule_id"] in page


def test_the_closed_field_sets_match_the_published_contract() -> None:
    """The renderer mirrors the schema's closed objects; pin that they agree."""

    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    defs = schema["$defs"]
    assert set(schema["properties"]) == html_receipt._DOCUMENT_FIELDS
    assert (
        set(defs["untrusted_envelope"]["properties"]) == html_receipt._ENVELOPE_FIELDS
    )
    payload = defs["deterministic_payload"]["properties"]
    assert set(payload) == html_receipt._PAYLOAD_FIELDS
    assert set(payload["hashes"]["properties"]) == set(html_receipt._HASH_ORDER)
    assert set(payload["scope"]["properties"]) == html_receipt._SCOPE_FIELDS
    assert set(payload["summary"]["properties"]) == set(html_receipt._STATUS_SYMBOLS)
    assert set(defs["outcome"]["properties"]) == html_receipt._RESULT_FIELDS
    for name in ("untrusted_envelope", "deterministic_payload", "outcome"):
        assert defs[name]["additionalProperties"] is False
        assert set(defs[name]["required"]) == set(defs[name]["properties"])
