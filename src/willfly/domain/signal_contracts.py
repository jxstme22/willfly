"""Versioned contracts for brain predictions, proposals and manual feedback.

These records describe decision support, not transactions. A prediction is a
research artifact, a proposal may be qualified only by a later gate, and a
manual action is an externally performed event reported back to Willfly. No
record in this module contains a signing key or an execution method.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, ClassVar, Mapping


SIGNAL_SCHEMA_VERSION = "signal-contract-v0.1.0"
_UINT_STRING = re.compile(r"^(0|[1-9][0-9]*)$")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _timestamp(value: Any, field: str) -> str:
    value = _text(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be RFC-3339 text") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return value


def _uint(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _positive_uint(value: Any, field: str) -> int:
    value = _uint(value, field)
    if value == 0:
        raise ValueError(f"{field} must be positive")
    return value


def _optional_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer or null")
    return value


def _uint_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or _UINT_STRING.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical unsigned integer string")
    return value


def _refs(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must be a non-empty list of text references")
    return tuple(value)


def _exact(data: Mapping[str, Any], allowed: set[str], name: str) -> None:
    if not isinstance(data, Mapping):
        raise ValueError(f"{name} must be an object")
    extra = set(data) - allowed
    if extra:
        raise ValueError(f"{name} has unsupported fields: {', '.join(sorted(extra))}")


@dataclass(frozen=True)
class InstrumentIdentity:
    """Stable token or pool identity used by every signal record."""

    schema_version: ClassVar[str] = SIGNAL_SCHEMA_VERSION
    chain_id: int
    kind: str
    identifier: str
    quote_asset: str | None = None
    protocol: str | None = None

    def __post_init__(self) -> None:
        _positive_uint(self.chain_id, "chain_id")
        if self.kind not in {"token", "pool"}:
            raise ValueError("instrument kind must be token or pool")
        _text(self.identifier, "identifier")
        _optional_text(self.quote_asset, "quote_asset")
        if self.kind == "pool":
            _text(self.protocol, "protocol")
        elif self.protocol is not None:
            raise ValueError("token instruments cannot claim a pool protocol")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "chain_id": self.chain_id,
            "kind": self.kind,
            "identifier": self.identifier,
            "quote_asset": self.quote_asset,
            "protocol": self.protocol,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InstrumentIdentity":
        _exact(data, {"schema_version", "chain_id", "kind", "identifier", "quote_asset", "protocol"}, "instrument")
        if data.get("schema_version") != SIGNAL_SCHEMA_VERSION:
            raise ValueError("instrument schema version is unsupported")
        return cls(
            _positive_uint(data.get("chain_id"), "chain_id"),
            _text(data.get("kind"), "kind"),
            _text(data.get("identifier"), "identifier"),
            _optional_text(data.get("quote_asset"), "quote_asset"),
            _optional_text(data.get("protocol"), "protocol"),
        )


@dataclass(frozen=True)
class PortfolioContext:
    """As-of portfolio facts available to a proposal; never a private key."""

    schema_version: ClassVar[str] = SIGNAL_SCHEMA_VERSION
    as_of_time: str
    position_state: str
    wallet_scope: str
    quality_state: str
    available_capital_atomic: str | None = None
    open_position_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _timestamp(self.as_of_time, "as_of_time")
        if self.position_state not in {"flat", "spot_open", "lp_open", "mixed", "unknown"}:
            raise ValueError("unsupported position_state")
        if self.wallet_scope not in {"none", "public_only", "unknown"}:
            raise ValueError("unsupported wallet_scope")
        if self.quality_state not in {"healthy", "stale", "degraded", "unknown"}:
            raise ValueError("unsupported quality_state")
        if self.available_capital_atomic is not None:
            _uint_string(self.available_capital_atomic, "available_capital_atomic")
        if any(not isinstance(ref, str) or not ref.strip() for ref in self.open_position_refs):
            raise ValueError("open_position_refs must contain non-empty text")
        if any(not isinstance(ref, str) or not ref.strip() for ref in self.source_refs):
            raise ValueError("source_refs must contain non-empty text")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "as_of_time": self.as_of_time,
            "position_state": self.position_state,
            "wallet_scope": self.wallet_scope,
            "quality_state": self.quality_state,
            "available_capital_atomic": self.available_capital_atomic,
            "open_position_refs": list(self.open_position_refs),
            "source_refs": list(self.source_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PortfolioContext":
        _exact(
            data,
            {"schema_version", "as_of_time", "position_state", "wallet_scope", "quality_state", "available_capital_atomic", "open_position_refs", "source_refs"},
            "portfolio_context",
        )
        if data.get("schema_version") != SIGNAL_SCHEMA_VERSION:
            raise ValueError("portfolio context schema version is unsupported")
        open_position_refs = data.get("open_position_refs")
        source_refs = data.get("source_refs")
        if not isinstance(open_position_refs, list) or not isinstance(source_refs, list):
            raise ValueError("portfolio context references must be lists")
        return cls(
            _timestamp(data.get("as_of_time"), "as_of_time"),
            _text(data.get("position_state"), "position_state"),
            _text(data.get("wallet_scope"), "wallet_scope"),
            _text(data.get("quality_state"), "quality_state"),
            None if data.get("available_capital_atomic") is None else _uint_string(data.get("available_capital_atomic"), "available_capital_atomic"),
            tuple(open_position_refs),
            tuple(source_refs),
        )


@dataclass(frozen=True)
class PredictionTarget:
    schema_version: ClassVar[str] = SIGNAL_SCHEMA_VERSION
    target_id: str
    market: str
    action: str
    metric: str
    horizons_seconds: tuple[int, ...]
    qualification_gate: str

    def __post_init__(self) -> None:
        _text(self.target_id, "target_id")
        if self.market not in {"spot", "lp"}:
            raise ValueError("target market must be spot or lp")
        if self.action not in {"entry", "hold", "exit"}:
            raise ValueError("target action must be entry, hold or exit")
        if self.metric not in {"net_return_bps", "adverse_excursion_bps", "exit_failure_risk", "liquidity_deterioration_bps"}:
            raise ValueError("unsupported target metric")
        if not self.horizons_seconds or any(_positive_uint(value, "horizon_seconds") != value for value in self.horizons_seconds):
            raise ValueError("target horizons must be positive")
        if tuple(sorted(set(self.horizons_seconds))) != self.horizons_seconds:
            raise ValueError("target horizons must be sorted and unique")
        _text(self.qualification_gate, "qualification_gate")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target_id": self.target_id,
            "market": self.market,
            "action": self.action,
            "metric": self.metric,
            "horizons_seconds": list(self.horizons_seconds),
            "qualification_gate": self.qualification_gate,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PredictionTarget":
        _exact(data, {"schema_version", "target_id", "market", "action", "metric", "horizons_seconds", "qualification_gate"}, "prediction_target")
        if data.get("schema_version") != SIGNAL_SCHEMA_VERSION:
            raise ValueError("prediction target schema version is unsupported")
        horizons = data.get("horizons_seconds")
        if not isinstance(horizons, list):
            raise ValueError("horizons_seconds must be a list")
        return cls(
            _text(data.get("target_id"), "target_id"),
            _text(data.get("market"), "market"),
            _text(data.get("action"), "action"),
            _text(data.get("metric"), "metric"),
            tuple(horizons),
            _text(data.get("qualification_gate"), "qualification_gate"),
        )


@dataclass(frozen=True)
class Confidence:
    """Confidence with explicit calibration semantics; no fake probability."""

    schema_version: ClassVar[str] = SIGNAL_SCHEMA_VERSION
    kind: str
    score: int | None = None
    probability_bps: int | None = None
    calibration_ref: str | None = None

    def __post_init__(self) -> None:
        _optional_text(self.calibration_ref, "calibration_ref")
        if self.kind == "unavailable":
            if any(value is not None for value in (self.score, self.probability_bps, self.calibration_ref)):
                raise ValueError("unavailable confidence cannot contain a score or probability")
        elif self.kind == "uncalibrated_score":
            if self.score is None or not isinstance(self.score, int) or isinstance(self.score, bool):
                raise ValueError("uncalibrated confidence requires an integer score")
            if self.probability_bps is not None or self.calibration_ref is not None:
                raise ValueError("uncalibrated confidence cannot claim a probability")
        elif self.kind == "calibrated_probability":
            if self.probability_bps is None or not isinstance(self.probability_bps, int) or isinstance(self.probability_bps, bool) or not 0 <= self.probability_bps <= 10_000:
                raise ValueError("calibrated probability must be an integer from 0 to 10000 basis points")
            if self.score is not None or not self.calibration_ref:
                raise ValueError("calibrated probability requires a calibration reference and no raw score")
        else:
            raise ValueError("unsupported confidence kind")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "score": self.score,
            "probability_bps": self.probability_bps,
            "calibration_ref": self.calibration_ref,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Confidence":
        _exact(data, {"schema_version", "kind", "score", "probability_bps", "calibration_ref"}, "confidence")
        if data.get("schema_version") != SIGNAL_SCHEMA_VERSION:
            raise ValueError("confidence schema version is unsupported")
        return cls(
            _text(data.get("kind"), "kind"),
            _optional_int(data.get("score"), "score"),
            _optional_int(data.get("probability_bps"), "probability_bps"),
            _optional_text(data.get("calibration_ref"), "calibration_ref"),
        )


@dataclass(frozen=True)
class PredictionRecord:
    schema_version: ClassVar[str] = SIGNAL_SCHEMA_VERSION
    prediction_id: str
    contract_version: str
    target_id: str
    horizon_seconds: int
    instrument: InstrumentIdentity
    created_at: str
    evidence_cutoff: str
    expires_at: str
    model_id: str
    model_version: str
    expected_value_bps: int | None
    uncertainty_bps: int | None
    confidence: Confidence
    portfolio_context: PortfolioContext
    source_refs: tuple[str, ...]
    state: str = "research_prediction"

    def __post_init__(self) -> None:
        if self.contract_version != SIGNAL_SCHEMA_VERSION:
            raise ValueError("prediction contract version is unsupported")
        _text(self.prediction_id, "prediction_id")
        _text(self.target_id, "target_id")
        _positive_uint(self.horizon_seconds, "horizon_seconds")
        created = _timestamp(self.created_at, "created_at")
        cutoff = _timestamp(self.evidence_cutoff, "evidence_cutoff")
        expiry = _timestamp(self.expires_at, "expires_at")
        if datetime.fromisoformat(cutoff.replace("Z", "+00:00")) > datetime.fromisoformat(created.replace("Z", "+00:00")):
            raise ValueError("evidence_cutoff cannot be after created_at")
        if datetime.fromisoformat(expiry.replace("Z", "+00:00")) <= datetime.fromisoformat(created.replace("Z", "+00:00")):
            raise ValueError("expires_at must be after created_at")
        _text(self.model_id, "model_id")
        _text(self.model_version, "model_version")
        _optional_int(self.expected_value_bps, "expected_value_bps")
        if self.uncertainty_bps is not None:
            _uint(self.uncertainty_bps, "uncertainty_bps")
        _refs(list(self.source_refs), "source_refs")
        if self.state not in {"research_prediction", "invalidated", "expired"}:
            raise ValueError("unsupported prediction state")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "prediction_id": self.prediction_id,
            "contract_version": self.contract_version,
            "target_id": self.target_id,
            "horizon_seconds": self.horizon_seconds,
            "instrument": self.instrument.to_dict(),
            "created_at": self.created_at,
            "evidence_cutoff": self.evidence_cutoff,
            "expires_at": self.expires_at,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "expected_value_bps": self.expected_value_bps,
            "uncertainty_bps": self.uncertainty_bps,
            "confidence": self.confidence.to_dict(),
            "portfolio_context": self.portfolio_context.to_dict(),
            "source_refs": list(self.source_refs),
            "state": self.state,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PredictionRecord":
        _exact(data, {"schema_version", "prediction_id", "contract_version", "target_id", "horizon_seconds", "instrument", "created_at", "evidence_cutoff", "expires_at", "model_id", "model_version", "expected_value_bps", "uncertainty_bps", "confidence", "portfolio_context", "source_refs", "state"}, "prediction")
        if data.get("schema_version") != SIGNAL_SCHEMA_VERSION:
            raise ValueError("prediction schema version is unsupported")
        return cls(
            _text(data.get("prediction_id"), "prediction_id"),
            _text(data.get("contract_version"), "contract_version"),
            _text(data.get("target_id"), "target_id"),
            _positive_uint(data.get("horizon_seconds"), "horizon_seconds"),
            InstrumentIdentity.from_dict(data.get("instrument")),
            _timestamp(data.get("created_at"), "created_at"),
            _timestamp(data.get("evidence_cutoff"), "evidence_cutoff"),
            _timestamp(data.get("expires_at"), "expires_at"),
            _text(data.get("model_id"), "model_id"),
            _text(data.get("model_version"), "model_version"),
            _optional_int(data.get("expected_value_bps"), "expected_value_bps"),
            _optional_int(data.get("uncertainty_bps"), "uncertainty_bps"),
            Confidence.from_dict(data.get("confidence")),
            PortfolioContext.from_dict(data.get("portfolio_context")),
            _refs(data.get("source_refs"), "source_refs"),
            _text(data.get("state"), "state"),
        )


_EXIT_KINDS = {"sell_token", "remove_liquidity", "collect_fees", "convert_residual"}


@dataclass(frozen=True)
class SignalProposal:
    schema_version: ClassVar[str] = SIGNAL_SCHEMA_VERSION
    proposal_id: str
    prediction_id: str
    target_id: str
    horizon_seconds: int
    market: str
    action: str
    exit_kind: str | None
    instrument: InstrumentIdentity
    created_at: str
    expires_at: str
    model_version: str
    confidence: Confidence
    portfolio_context: PortfolioContext
    evidence_refs: tuple[str, ...]
    proposal_state: str = "research_only"
    execution_scope: str = "manual_only"

    def __post_init__(self) -> None:
        _text(self.proposal_id, "proposal_id")
        _text(self.prediction_id, "prediction_id")
        _text(self.target_id, "target_id")
        _positive_uint(self.horizon_seconds, "horizon_seconds")
        if self.market not in {"spot", "lp"}:
            raise ValueError("proposal market must be spot or lp")
        if self.action not in {"enter", "hold", "exit", "abstain"}:
            raise ValueError("unsupported proposal action")
        if self.action == "exit":
            if self.exit_kind not in _EXIT_KINDS:
                raise ValueError("exit proposals require a supported exit_kind")
            if self.market == "spot" and self.exit_kind not in {"sell_token", "convert_residual"}:
                raise ValueError("spot exits cannot remove LP liquidity or collect LP fees")
            if self.market == "lp" and self.exit_kind == "sell_token":
                raise ValueError("LP exits must identify liquidity or residual handling")
        elif self.exit_kind is not None:
            raise ValueError("only exit proposals may contain exit_kind")
        if self.market == "spot" and self.instrument.kind != "token":
            raise ValueError("spot proposals require a token instrument")
        if self.market == "lp" and self.instrument.kind != "pool":
            raise ValueError("LP proposals require a pool instrument")
        _timestamp(self.created_at, "created_at")
        _timestamp(self.expires_at, "expires_at")
        created = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        if expiry <= created:
            raise ValueError("proposal expires_at must be after created_at")
        _text(self.model_version, "model_version")
        _refs(list(self.evidence_refs), "evidence_refs")
        if self.proposal_state not in {"research_only", "qualified_manual_proposal", "expired", "invalidated"}:
            raise ValueError("unsupported proposal_state")
        if self.execution_scope != "manual_only":
            raise ValueError("signal proposals are manual_only")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "prediction_id": self.prediction_id,
            "target_id": self.target_id,
            "horizon_seconds": self.horizon_seconds,
            "market": self.market,
            "action": self.action,
            "exit_kind": self.exit_kind,
            "instrument": self.instrument.to_dict(),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "model_version": self.model_version,
            "confidence": self.confidence.to_dict(),
            "portfolio_context": self.portfolio_context.to_dict(),
            "evidence_refs": list(self.evidence_refs),
            "proposal_state": self.proposal_state,
            "execution_scope": self.execution_scope,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalProposal":
        _exact(data, {"schema_version", "proposal_id", "prediction_id", "target_id", "horizon_seconds", "market", "action", "exit_kind", "instrument", "created_at", "expires_at", "model_version", "confidence", "portfolio_context", "evidence_refs", "proposal_state", "execution_scope"}, "signal_proposal")
        if data.get("schema_version") != SIGNAL_SCHEMA_VERSION:
            raise ValueError("signal proposal schema version is unsupported")
        return cls(
            _text(data.get("proposal_id"), "proposal_id"),
            _text(data.get("prediction_id"), "prediction_id"),
            _text(data.get("target_id"), "target_id"),
            _positive_uint(data.get("horizon_seconds"), "horizon_seconds"),
            _text(data.get("market"), "market"),
            _text(data.get("action"), "action"),
            _optional_text(data.get("exit_kind"), "exit_kind"),
            InstrumentIdentity.from_dict(data.get("instrument")),
            _timestamp(data.get("created_at"), "created_at"),
            _timestamp(data.get("expires_at"), "expires_at"),
            _text(data.get("model_version"), "model_version"),
            Confidence.from_dict(data.get("confidence")),
            PortfolioContext.from_dict(data.get("portfolio_context")),
            _refs(data.get("evidence_refs"), "evidence_refs"),
            _text(data.get("proposal_state"), "proposal_state"),
            _text(data.get("execution_scope"), "execution_scope"),
        )


@dataclass(frozen=True)
class ManualAction:
    schema_version: ClassVar[str] = SIGNAL_SCHEMA_VERSION
    action_id: str
    proposal_id: str | None
    instrument: InstrumentIdentity
    market: str
    action: str
    exit_kind: str | None
    action_time: str
    recorded_at: str
    execution_status: str
    transaction_hash: str | None
    wallet_ref: str | None
    user_override: bool
    source_refs: tuple[str, ...]
    execution_scope: str = "manual_only"

    def __post_init__(self) -> None:
        _text(self.action_id, "action_id")
        _optional_text(self.proposal_id, "proposal_id")
        if self.market not in {"spot", "lp"}:
            raise ValueError("manual action market must be spot or lp")
        if self.action not in {"enter", "hold", "exit", "abstain"}:
            raise ValueError("unsupported manual action")
        if self.action == "exit" and self.exit_kind not in _EXIT_KINDS:
            raise ValueError("manual exits require a supported exit_kind")
        if self.action != "exit" and self.exit_kind is not None:
            raise ValueError("only exit manual actions may contain exit_kind")
        if self.market == "spot" and self.instrument.kind != "token":
            raise ValueError("spot manual actions require a token instrument")
        if self.market == "lp" and self.instrument.kind != "pool":
            raise ValueError("LP manual actions require a pool instrument")
        _timestamp(self.action_time, "action_time")
        _timestamp(self.recorded_at, "recorded_at")
        if self.execution_status not in {"reported", "matched", "ambiguous", "failed", "partial", "not_executed"}:
            raise ValueError("unsupported execution_status")
        _optional_text(self.transaction_hash, "transaction_hash")
        _optional_text(self.wallet_ref, "wallet_ref")
        if not isinstance(self.user_override, bool):
            raise ValueError("user_override must be boolean")
        _refs(list(self.source_refs), "source_refs")
        if self.execution_scope != "manual_only":
            raise ValueError("manual actions are manual_only")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "action_id": self.action_id,
            "proposal_id": self.proposal_id,
            "instrument": self.instrument.to_dict(),
            "market": self.market,
            "action": self.action,
            "exit_kind": self.exit_kind,
            "action_time": self.action_time,
            "recorded_at": self.recorded_at,
            "execution_status": self.execution_status,
            "transaction_hash": self.transaction_hash,
            "wallet_ref": self.wallet_ref,
            "user_override": self.user_override,
            "source_refs": list(self.source_refs),
            "execution_scope": self.execution_scope,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ManualAction":
        _exact(data, {"schema_version", "action_id", "proposal_id", "instrument", "market", "action", "exit_kind", "action_time", "recorded_at", "execution_status", "transaction_hash", "wallet_ref", "user_override", "source_refs", "execution_scope"}, "manual_action")
        if data.get("schema_version") != SIGNAL_SCHEMA_VERSION:
            raise ValueError("manual action schema version is unsupported")
        return cls(
            _text(data.get("action_id"), "action_id"),
            _optional_text(data.get("proposal_id"), "proposal_id"),
            InstrumentIdentity.from_dict(data.get("instrument")),
            _text(data.get("market"), "market"),
            _text(data.get("action"), "action"),
            _optional_text(data.get("exit_kind"), "exit_kind"),
            _timestamp(data.get("action_time"), "action_time"),
            _timestamp(data.get("recorded_at"), "recorded_at"),
            _text(data.get("execution_status"), "execution_status"),
            _optional_text(data.get("transaction_hash"), "transaction_hash"),
            _optional_text(data.get("wallet_ref"), "wallet_ref"),
            data.get("user_override"),
            _refs(data.get("source_refs"), "source_refs"),
            _text(data.get("execution_scope"), "execution_scope"),
        )


@dataclass(frozen=True)
class OutcomeRecord:
    schema_version: ClassVar[str] = SIGNAL_SCHEMA_VERSION
    outcome_id: str
    prediction_id: str
    target_id: str
    outcome_kind: str
    status: str
    observed_at: str
    label_available_at: str | None
    net_return_bps: int | None
    source_refs: tuple[str, ...]
    action_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.outcome_id, "outcome_id")
        _text(self.prediction_id, "prediction_id")
        _text(self.target_id, "target_id")
        if self.outcome_kind not in {"actual_manual", "simulated_counterfactual", "observed_market"}:
            raise ValueError("unsupported outcome_kind")
        if self.outcome_kind == "actual_manual" and self.action_id is None:
            raise ValueError("actual_manual outcomes require action_id")
        if self.outcome_kind != "actual_manual" and self.action_id is not None:
            raise ValueError("non-manual outcomes cannot claim a manual action")
        if self.status not in {"observed", "censored", "unresolved", "invalidated"}:
            raise ValueError("unsupported outcome status")
        observed = _timestamp(self.observed_at, "observed_at")
        if self.label_available_at is not None:
            available = _timestamp(self.label_available_at, "label_available_at")
            if datetime.fromisoformat(available.replace("Z", "+00:00")) < datetime.fromisoformat(observed.replace("Z", "+00:00")):
                raise ValueError("label_available_at cannot precede observed_at")
        _optional_int(self.net_return_bps, "net_return_bps")
        _refs(list(self.source_refs), "source_refs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcome_id": self.outcome_id,
            "prediction_id": self.prediction_id,
            "target_id": self.target_id,
            "outcome_kind": self.outcome_kind,
            "status": self.status,
            "observed_at": self.observed_at,
            "label_available_at": self.label_available_at,
            "net_return_bps": self.net_return_bps,
            "source_refs": list(self.source_refs),
            "action_id": self.action_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OutcomeRecord":
        _exact(data, {"schema_version", "outcome_id", "prediction_id", "target_id", "outcome_kind", "status", "observed_at", "label_available_at", "net_return_bps", "source_refs", "action_id"}, "outcome")
        if data.get("schema_version") != SIGNAL_SCHEMA_VERSION:
            raise ValueError("outcome schema version is unsupported")
        return cls(
            _text(data.get("outcome_id"), "outcome_id"),
            _text(data.get("prediction_id"), "prediction_id"),
            _text(data.get("target_id"), "target_id"),
            _text(data.get("outcome_kind"), "outcome_kind"),
            _text(data.get("status"), "status"),
            _timestamp(data.get("observed_at"), "observed_at"),
            None if data.get("label_available_at") is None else _timestamp(data.get("label_available_at"), "label_available_at"),
            _optional_int(data.get("net_return_bps"), "net_return_bps"),
            _refs(data.get("source_refs"), "source_refs"),
            _optional_text(data.get("action_id"), "action_id"),
        )


@dataclass(frozen=True)
class SignalContract:
    """Frozen B0 target and execution policy used by later model/UI layers."""

    schema_version: ClassVar[str] = SIGNAL_SCHEMA_VERSION
    contract_id: str
    decision_interval_seconds: int
    proposal_ttl_seconds: int
    horizons_seconds: tuple[int, ...]
    primary_horizon_seconds: int
    targets: tuple[PredictionTarget, ...]
    execution_scope: str = "manual_only"
    signing_enabled: bool = False
    funding_enabled: bool = False

    def __post_init__(self) -> None:
        _text(self.contract_id, "contract_id")
        _positive_uint(self.decision_interval_seconds, "decision_interval_seconds")
        _positive_uint(self.proposal_ttl_seconds, "proposal_ttl_seconds")
        if not self.horizons_seconds or tuple(sorted(set(self.horizons_seconds))) != self.horizons_seconds:
            raise ValueError("contract horizons must be sorted and unique")
        if any(_positive_uint(value, "horizon_seconds") != value for value in self.horizons_seconds):
            raise ValueError("contract horizons must be positive")
        if self.primary_horizon_seconds not in self.horizons_seconds:
            raise ValueError("primary horizon must be declared")
        if not self.targets:
            raise ValueError("signal contract requires targets")
        target_ids = [target.target_id for target in self.targets]
        if len(set(target_ids)) != len(target_ids):
            raise ValueError("signal target IDs must be unique")
        if any(tuple(target.horizons_seconds) != self.horizons_seconds for target in self.targets):
            raise ValueError("every target must use the contract horizon set")
        if self.execution_scope != "manual_only":
            raise ValueError("signal contract execution scope must be manual_only")
        if not isinstance(self.signing_enabled, bool) or not isinstance(self.funding_enabled, bool):
            raise ValueError("signing_enabled and funding_enabled must be boolean")
        if self.signing_enabled or self.funding_enabled:
            raise ValueError("signing and funding are disabled in this contract")

    def target(self, target_id: str) -> PredictionTarget:
        for target in self.targets:
            if target.target_id == target_id:
                return target
        raise KeyError(target_id)

    def validate_prediction(self, prediction: PredictionRecord) -> None:
        if prediction.contract_version != self.schema_version:
            raise ValueError("prediction does not use this signal contract")
        target = self.target(prediction.target_id)
        if prediction.horizon_seconds not in target.horizons_seconds:
            raise ValueError("prediction horizon is not declared for its target")
        expected_kind = "token" if target.market == "spot" else "pool"
        if prediction.instrument.kind != expected_kind:
            raise ValueError("prediction instrument does not match target market")

    def validate_proposal(self, proposal: SignalProposal) -> None:
        target = self.target(proposal.target_id)
        if proposal.horizon_seconds not in target.horizons_seconds:
            raise ValueError("proposal horizon is not declared for its target")
        expected_action = {"entry": "enter", "hold": "hold", "exit": "exit"}[target.action]
        if proposal.market != target.market or proposal.action not in {expected_action, "abstain"}:
            raise ValueError("proposal action does not match target identity")
        created = datetime.fromisoformat(proposal.created_at.replace("Z", "+00:00"))
        expiry = datetime.fromisoformat(proposal.expires_at.replace("Z", "+00:00"))
        if (expiry - created).total_seconds() > self.proposal_ttl_seconds:
            raise ValueError("proposal expiry exceeds the frozen TTL")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "decision_interval_seconds": self.decision_interval_seconds,
            "proposal_ttl_seconds": self.proposal_ttl_seconds,
            "horizons_seconds": list(self.horizons_seconds),
            "primary_horizon_seconds": self.primary_horizon_seconds,
            "targets": [target.to_dict() for target in self.targets],
            "execution_scope": self.execution_scope,
            "signing_enabled": self.signing_enabled,
            "funding_enabled": self.funding_enabled,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SignalContract":
        _exact(data, {"schema_version", "contract_id", "decision_interval_seconds", "proposal_ttl_seconds", "horizons_seconds", "primary_horizon_seconds", "targets", "execution_scope", "signing_enabled", "funding_enabled"}, "signal_contract")
        if data.get("schema_version") != SIGNAL_SCHEMA_VERSION:
            raise ValueError("signal contract schema version is unsupported")
        horizons = data.get("horizons_seconds")
        targets = data.get("targets")
        if not isinstance(horizons, list) or not isinstance(targets, list):
            raise ValueError("signal contract horizons and targets must be lists")
        return cls(
            _text(data.get("contract_id"), "contract_id"),
            _positive_uint(data.get("decision_interval_seconds"), "decision_interval_seconds"),
            _positive_uint(data.get("proposal_ttl_seconds"), "proposal_ttl_seconds"),
            tuple(horizons),
            _positive_uint(data.get("primary_horizon_seconds"), "primary_horizon_seconds"),
            tuple(PredictionTarget.from_dict(item) for item in targets),
            _text(data.get("execution_scope"), "execution_scope"),
            data.get("signing_enabled"),
            data.get("funding_enabled"),
        )


def default_signal_contract() -> SignalContract:
    """Return the frozen B0 contract used by the first model experiment."""

    horizons = (60, 300, 900)
    targets = tuple(
        PredictionTarget(
            target_id=f"{market}_{action}_net_return",
            market=market,
            action=action,
            metric="net_return_bps",
            horizons_seconds=horizons,
            qualification_gate="spot_execution_evidence" if market == "spot" else "lp_execution_evidence",
        )
        for market in ("spot", "lp")
        for action in ("entry", "hold", "exit")
    )
    return SignalContract(
        contract_id="brain-signal-v0.1",
        decision_interval_seconds=15,
        proposal_ttl_seconds=15,
        horizons_seconds=horizons,
        primary_horizon_seconds=300,
        targets=targets,
    )


__all__ = [
    "Confidence",
    "InstrumentIdentity",
    "ManualAction",
    "OutcomeRecord",
    "PortfolioContext",
    "PredictionRecord",
    "PredictionTarget",
    "SIGNAL_SCHEMA_VERSION",
    "SignalContract",
    "SignalProposal",
    "default_signal_contract",
]
