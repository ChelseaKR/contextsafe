"""Apply a validated mapping profile to an import result (B-026).

The importer has already converted the source whole and recorded, beside
every observation, the :class:`~contextsafe.mapping_profile.SourceToken` it
was read from. This module looks each token up in the profile's table and,
where a row matches, replaces the observation's value with the row's target;
where none matches, the observation keeps the verbatim token and the result
says so with a closed warning. Nothing is dropped, nothing is chosen between,
and no observation changes concept: a row's source and target concepts are
the same concept by the profile's own validation, and the token's concept is
the observation's, so the descriptor written here is an identity over the
concept with the profile's digest and version beside it.

Ambiguity survives the binding. Two observations that carried two tokens are
two observations after mapping, whatever their targets; the evaluator reports
them ambiguous. A sex parameter for clinical use keeps its order context and
supporting observations from the source, because the only thing a profile
may bind on it is the value.

Every observation carries the profile's SHA-256 and version in its mapping
block, and the converted document is re-validated by the observation
contract, so ``evaluate``'s input hash binds the profile that produced what
it evaluated.
"""

from dataclasses import replace

from contextsafe.contract_validation import contract_error
from contextsafe.importers.base import ImportResult, ImportWarningCode
from contextsafe.mapping_profile import (
    MappingProfile,
    MappingProfileErrorCode,
    SpcuValueBinding,
    TargetValue,
)
from contextsafe.models import (
    OBSERVATION_SET_SCHEMA_VERSION,
    MappingDescriptor,
    Observation,
    SemanticValue,
    SexParameterForClinicalUse,
)
from contextsafe.validation import parse_observations


def _bind(observed: SemanticValue, target: TargetValue) -> SemanticValue:
    """The value an observation carries after its row applies."""

    if isinstance(target, SpcuValueBinding):
        if not isinstance(observed, SexParameterForClinicalUse):
            raise contract_error(
                MappingProfileErrorCode.NOT_APPLICABLE.value,
                "$.rows",
                "a sex-parameter value binding applies only to a sex parameter",
            )
        return replace(observed, value=target.value)
    return target


def _rebound(
    observation: Observation, value: SemanticValue, profile: MappingProfile
) -> Observation:
    return replace(
        observation,
        value=value,
        mapping=MappingDescriptor(
            source_concept=observation.concept,
            target_concept=observation.concept,
            mapping_version=observation.mapping.mapping_version,
            profile_sha256=profile.sha256(),
            profile_version=profile.version,
        ),
    )


def apply_profile(result: ImportResult, profile: MappingProfile) -> ImportResult:
    """Return ``result`` with every matched token bound to its row's target.

    The profile must be for the result's format and the result must carry
    one source token per observation; otherwise nothing is applied and the
    call fails closed. The observations that come back carry the profile's
    digest and version, and the result's warnings no longer say the profile
    is unbound.
    """

    if profile.format != result.format_name:
        raise contract_error(
            MappingProfileErrorCode.FORMAT_MISMATCH.value,
            "$.format",
            "the profile is for a different format than the source",
        )
    if len(result.source_tokens) != len(result.observations):
        raise contract_error(
            MappingProfileErrorCode.NOT_APPLICABLE.value,
            "$.source_tokens",
            "the import result records no source token to bind",
        )
    rows = profile.index()
    bound: list[Observation] = []
    unbound = False
    for observation, token in zip(
        result.observations, result.source_tokens, strict=True
    ):
        if token.concept is not observation.concept:
            raise contract_error(
                MappingProfileErrorCode.NOT_APPLICABLE.value,
                "$.source_tokens",
                "a source token names a concept other than its observation's",
            )
        row = rows.get((token.concept, token.carrier, token.token))
        if row is None:
            unbound = True
            value = observation.value
        else:
            value = _bind(observation.value, row.target)
        bound.append(_rebound(observation, value, profile))
    validated = parse_observations(
        {
            "observations": [item.to_dict() for item in bound],
            "schema_version": OBSERVATION_SET_SCHEMA_VERSION,
        }
    )
    warnings = tuple(
        item
        for item in result.warnings
        if item is not ImportWarningCode.MAPPING_PROFILE_NOT_BOUND
    )
    if unbound:
        warnings = (*warnings, ImportWarningCode.MAPPING_PROFILE_ROW_UNMATCHED)
    return replace(
        result,
        observations=validated,
        warnings=warnings,
        profile_sha256=profile.sha256(),
        profile_version=profile.version,
    )
