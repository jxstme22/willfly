"""Strict, JSON-safe contracts for the first Observatory release.

The contracts intentionally use strings for EVM quantities. This avoids loss of
precision in tooling that parses JSON through IEEE-754 numbers and makes the
raw lineage explicit at every boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, ClassVar, Mapping


SCHEMA_VERSION = "0.1.0"
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
BYTES32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
TX_HASH_RE = BYTES32_RE
UINT_RE = re.compile(r"^(0|[1-9][0-9]*)$")


class SchemaValidationError(ValueError):
    """Raised when a record cannot satisfy its versioned contract."""


class AmbiguousContractError(SchemaValidationError):
    """Raised when a record would silently turn an unknown into a claim."""


def _require(condition: bool, message: str, *, ambiguous: bool = False) -> None:
    if not condition:
        error_type = AmbiguousContractError if ambiguous else SchemaValidationError
        raise error_type(message)


def _text(value: Any, field_name: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{field_name} must be non-empty text")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _address(value: Any, field_name: str) -> str:
    _require(isinstance(value, str) and ADDRESS_RE.fullmatch(value) is not None, f"{field_name} must be an EVM address")
    return value


def _optional_address(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _address(value, field_name)


def _bytes32(value: Any, field_name: str) -> str:
    _require(isinstance(value, str) and BYTES32_RE.fullmatch(value) is not None, f"{field_name} must be 32-byte hex")
    return value


def _optional_bytes32(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _bytes32(value, field_name)


def _uint_string(value: Any, field_name: str) -> str:
    _require(isinstance(value, str) and UINT_RE.fullmatch(value) is not None, f"{field_name} must be a canonical unsigned integer string")
    return value


def _uint(value: Any, field_name: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool) and value >= 0, f"{field_name} must be a non-negative integer")
    return value


def _timestamp(value: Any, field_name: str) -> str:
    _require(isinstance(value, str), f"{field_name} must be RFC-3339 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SchemaValidationError(f"{field_name} must be RFC-3339 text") from exc
    _require(parsed.tzinfo is not None, f"{field_name} must include a timezone")
    return value


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{field_name} must be an object")
    return dict(value)


def _list_of_text(value: Any, field_name: str) -> tuple[str, ...]:
    _require(isinstance(value, list), f"{field_name} must be a list")
    return tuple(_text(item, f"{field_name}[]") for item in value)


class ContractMixin:
    schema_version: ClassVar[str] = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"schema_version": self.schema_version}
        for name, value in self.__dict__.items():
            if isinstance(value, tuple):
                result[name] = [item.to_dict() if hasattr(item, "to_dict") else item for item in value]
            elif hasattr(value, "to_dict"):
                result[name] = value.to_dict()
            else:
                result[name] = value
        return result


@dataclass(frozen=True)
class RawEvent(ContractMixin):
    chain_id: int
    source: str
    source_schema_version: str
    block_number: int | None
    block_hash: str | None
    parent_hash: str | None
    transaction_hash: str | None
    log_index: int | None
    event_time: str
    received_time: str
    payload: Mapping[str, Any]
    ingestion_run: str
    canonical_status: str

    def __post_init__(self) -> None:
        _require(self.chain_id > 0, "chain_id must be positive")
        _text(self.source, "source")
        _text(self.source_schema_version, "source_schema_version")
        if self.block_number is not None:
            _uint(self.block_number, "block_number")
        if self.block_hash is not None:
            _bytes32(self.block_hash, "block_hash")
        if self.parent_hash is not None:
            _bytes32(self.parent_hash, "parent_hash")
        if self.transaction_hash is not None:
            _bytes32(self.transaction_hash, "transaction_hash")
        if self.log_index is not None:
            _uint(self.log_index, "log_index")
        _timestamp(self.event_time, "event_time")
        _timestamp(self.received_time, "received_time")
        _mapping(self.payload, "payload")
        _text(self.ingestion_run, "ingestion_run")
        _require(self.canonical_status in {"provisional", "canonical", "orphaned", "quarantined"}, "unsupported canonical_status")
        if self.canonical_status == "orphaned":
            _require(self.block_hash is not None, "orphaned events retain their block hash")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawEvent":
        return cls(
            chain_id=_uint(data.get("chain_id"), "chain_id"),
            source=_text(data.get("source"), "source"),
            source_schema_version=_text(data.get("source_schema_version"), "source_schema_version"),
            block_number=None if data.get("block_number") is None else _uint(data["block_number"], "block_number"),
            block_hash=_optional_bytes32(data.get("block_hash"), "block_hash"),
            parent_hash=_optional_bytes32(data.get("parent_hash"), "parent_hash"),
            transaction_hash=_optional_bytes32(data.get("transaction_hash"), "transaction_hash"),
            log_index=None if data.get("log_index") is None else _uint(data["log_index"], "log_index"),
            event_time=_timestamp(data.get("event_time"), "event_time"),
            received_time=_timestamp(data.get("received_time"), "received_time"),
            payload=_mapping(data.get("payload"), "payload"),
            ingestion_run=_text(data.get("ingestion_run"), "ingestion_run"),
            canonical_status=_text(data.get("canonical_status"), "canonical_status"),
        )

    @property
    def logical_key(self) -> tuple[int, str | None, str | None, int | None]:
        return (self.chain_id, self.block_hash, self.transaction_hash, self.log_index)


@dataclass(frozen=True)
class PoolIdentity(ContractMixin):
    chain_id: int
    protocol: str
    manager_or_factory: str
    pool_address: str | None
    pool_id: str | None
    currency0: str
    currency1: str
    fee: int
    tick_spacing: int
    hook: str | None

    def __post_init__(self) -> None:
        _uint(self.chain_id, "chain_id")
        _require(self.protocol in {"uniswap_v3", "uniswap_v4"}, "unsupported protocol")
        _address(self.manager_or_factory, "manager_or_factory")
        _address(self.currency0, "currency0") if self.currency0 != "0x0000000000000000000000000000000000000000" else None
        _address(self.currency1, "currency1") if self.currency1 != "0x0000000000000000000000000000000000000000" else None
        _require(self.currency0.lower() != self.currency1.lower(), "currency0 and currency1 must differ", ambiguous=True)
        _uint(self.fee, "fee")
        _require(isinstance(self.tick_spacing, int) and not isinstance(self.tick_spacing, bool), "tick_spacing must be an integer")
        if self.protocol == "uniswap_v4":
            _require(self.pool_address is None, "V4 identity cannot use a pool address", ambiguous=True)
            _bytes32(self.pool_id, "pool_id")
            _address(self.hook, "hook")
        else:
            _require(self.pool_id is None, "V3 identity cannot use a V4 pool_id", ambiguous=True)
            _address(self.pool_address, "pool_address")
            _require(self.hook is None, "V3 identity cannot claim a V4 hook", ambiguous=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PoolIdentity":
        return cls(
            chain_id=_uint(data.get("chain_id"), "chain_id"),
            protocol=_text(data.get("protocol"), "protocol"),
            manager_or_factory=_address(data.get("manager_or_factory"), "manager_or_factory"),
            pool_address=_optional_address(data.get("pool_address"), "pool_address"),
            pool_id=_optional_bytes32(data.get("pool_id"), "pool_id"),
            currency0=_text(data.get("currency0"), "currency0"),
            currency1=_text(data.get("currency1"), "currency1"),
            fee=_uint(data.get("fee"), "fee"),
            tick_spacing=data.get("tick_spacing"),
            hook=_optional_address(data.get("hook"), "hook"),
        )


@dataclass(frozen=True)
class Launch(ContractMixin):
    chain_id: int
    token: str
    launch_contract: str | None
    launch_contract_version: str | None
    creation_evidence: tuple[str, ...]
    creator: str | None
    created_at: str | None
    first_seen_at: str
    origin_confidence: str
    linked_pool_ids: tuple[str, ...]
    lifecycle_state: str

    def __post_init__(self) -> None:
        _uint(self.chain_id, "chain_id")
        _address(self.token, "token")
        _optional_address(self.launch_contract, "launch_contract")
        _optional_text(self.launch_contract_version, "launch_contract_version")
        _require(all(isinstance(ref, str) and ref for ref in self.creation_evidence), "creation_evidence must contain non-empty references")
        _optional_address(self.creator, "creator")
        if self.created_at is not None:
            _timestamp(self.created_at, "created_at")
        _timestamp(self.first_seen_at, "first_seen_at")
        _require(self.origin_confidence in {"verified", "observed", "unverified", "unknown"}, "unsupported origin_confidence")
        for pool_id in self.linked_pool_ids:
            _bytes32(pool_id, "linked_pool_ids[]")
        _require(self.lifecycle_state in {"active", "graduated", "non_graduate", "unknown"}, "unsupported lifecycle_state")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Launch":
        return cls(
            chain_id=_uint(data.get("chain_id"), "chain_id"),
            token=_address(data.get("token"), "token"),
            launch_contract=_optional_address(data.get("launch_contract"), "launch_contract"),
            launch_contract_version=_optional_text(data.get("launch_contract_version"), "launch_contract_version"),
            creation_evidence=_list_of_text(data.get("creation_evidence"), "creation_evidence"),
            creator=_optional_address(data.get("creator"), "creator"),
            created_at=None if data.get("created_at") is None else _timestamp(data["created_at"], "created_at"),
            first_seen_at=_timestamp(data.get("first_seen_at"), "first_seen_at"),
            origin_confidence=_text(data.get("origin_confidence"), "origin_confidence"),
            linked_pool_ids=tuple(data.get("linked_pool_ids", [])),
            lifecycle_state=_text(data.get("lifecycle_state"), "lifecycle_state"),
        )


@dataclass(frozen=True)
class PaymentLeg(ContractMixin):
    asset: str
    amount_atomic: str
    direction: str
    from_address: str
    to_address: str
    evidence_ref: str

    def __post_init__(self) -> None:
        if self.asset.lower() != "native:eth":
            _address(self.asset, "asset")
        _uint_string(self.amount_atomic, "amount_atomic")
        _require(self.amount_atomic != "0", "payment amount must be positive")
        _require(self.direction in {"out", "in"}, "unsupported payment direction")
        _address(self.from_address, "from_address")
        _address(self.to_address, "to_address")
        _text(self.evidence_ref, "evidence_ref")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PaymentLeg":
        return cls(
            asset=_text(data.get("asset"), "asset"),
            amount_atomic=_uint_string(data.get("amount_atomic"), "amount_atomic"),
            direction=_text(data.get("direction"), "direction"),
            from_address=_address(data.get("from_address"), "from_address"),
            to_address=_address(data.get("to_address"), "to_address"),
            evidence_ref=_text(data.get("evidence_ref"), "evidence_ref"),
        )


@dataclass(frozen=True)
class TradeEvidence(ContractMixin):
    transaction_hash: str
    wallet: str
    token: str
    classification: str
    payment_legs: tuple[PaymentLeg, ...]
    receipt_legs: tuple[PaymentLeg, ...]
    quote_asset: str | None
    valuation_method: str | None
    estimated_usd: bool
    estimated_usd_value: str | None
    reason_flags: tuple[str, ...]
    method_version: str
    as_of_time: str
    retrieved_time: str
    raw_event_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _bytes32(self.transaction_hash, "transaction_hash")
        _address(self.wallet, "wallet")
        _address(self.token, "token")
        _require(self.classification in {"genuine_swap", "transfer", "gift_or_airdrop", "ambiguous"}, "unsupported trade classification")
        _require(all(isinstance(leg, PaymentLeg) for leg in self.payment_legs), "payment_legs must contain PaymentLeg records")
        _require(all(isinstance(leg, PaymentLeg) for leg in self.receipt_legs), "receipt_legs must contain PaymentLeg records")
        if self.classification == "genuine_swap":
            _require(bool(self.payment_legs) and bool(self.receipt_legs), "a genuine swap requires payment and receipt legs", ambiguous=True)
        if self.quote_asset is not None and self.quote_asset.lower() != "native:eth":
            _address(self.quote_asset, "quote_asset")
        if self.estimated_usd:
            _require(self.estimated_usd_value is not None and self.valuation_method is not None, "estimated USD requires value and valuation method")
            _uint_string(self.estimated_usd_value, "estimated_usd_value")
        else:
            _require(self.estimated_usd_value is None, "estimated_usd_value must be absent when not estimated")
        _optional_text(self.valuation_method, "valuation_method")
        _list_of_text(list(self.reason_flags), "reason_flags")
        _text(self.method_version, "method_version")
        _timestamp(self.as_of_time, "as_of_time")
        _timestamp(self.retrieved_time, "retrieved_time")
        _require(bool(self.raw_event_refs), "raw_event_refs cannot be empty")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TradeEvidence":
        return cls(
            transaction_hash=_bytes32(data.get("transaction_hash"), "transaction_hash"),
            wallet=_address(data.get("wallet"), "wallet"),
            token=_address(data.get("token"), "token"),
            classification=_text(data.get("classification"), "classification"),
            payment_legs=tuple(PaymentLeg.from_dict(item) for item in data.get("payment_legs", [])),
            receipt_legs=tuple(PaymentLeg.from_dict(item) for item in data.get("receipt_legs", [])),
            quote_asset=_optional_text(data.get("quote_asset"), "quote_asset"),
            valuation_method=_optional_text(data.get("valuation_method"), "valuation_method"),
            estimated_usd=bool(data.get("estimated_usd")),
            estimated_usd_value=_optional_text(data.get("estimated_usd_value"), "estimated_usd_value"),
            reason_flags=tuple(data.get("reason_flags", [])),
            method_version=_text(data.get("method_version"), "method_version"),
            as_of_time=_timestamp(data.get("as_of_time"), "as_of_time"),
            retrieved_time=_timestamp(data.get("retrieved_time"), "retrieved_time"),
            raw_event_refs=_list_of_text(data.get("raw_event_refs"), "raw_event_refs"),
        )


@dataclass(frozen=True)
class VendorAssessment(ContractMixin):
    vendor: str
    subject_type: str
    subject_id: str
    method_version: str | None
    reason_flags: tuple[str, ...]
    source_as_of_time: str | None
    retrieved_time: str
    freshness: str
    raw_reference: str | None
    unavailable: bool

    def __post_init__(self) -> None:
        _text(self.vendor, "vendor")
        _require(self.subject_type in {"token", "pool", "wallet"}, "unsupported subject_type")
        _text(self.subject_id, "subject_id")
        _optional_text(self.method_version, "method_version")
        _list_of_text(list(self.reason_flags), "reason_flags")
        if self.source_as_of_time is not None:
            _timestamp(self.source_as_of_time, "source_as_of_time")
        _timestamp(self.retrieved_time, "retrieved_time")
        _require(self.freshness in {"fresh", "stale", "unknown"}, "unsupported freshness")
        _optional_text(self.raw_reference, "raw_reference")
        if self.unavailable:
            _require(self.freshness == "unknown", "unavailable vendor data cannot be fresh or stale", ambiguous=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VendorAssessment":
        return cls(
            vendor=_text(data.get("vendor"), "vendor"),
            subject_type=_text(data.get("subject_type"), "subject_type"),
            subject_id=_text(data.get("subject_id"), "subject_id"),
            method_version=_optional_text(data.get("method_version"), "method_version"),
            reason_flags=tuple(data.get("reason_flags", [])),
            source_as_of_time=None if data.get("source_as_of_time") is None else _timestamp(data["source_as_of_time"], "source_as_of_time"),
            retrieved_time=_timestamp(data.get("retrieved_time"), "retrieved_time"),
            freshness=_text(data.get("freshness"), "freshness"),
            raw_reference=_optional_text(data.get("raw_reference"), "raw_reference"),
            unavailable=bool(data.get("unavailable")),
        )


@dataclass(frozen=True)
class WalletCohort(ContractMixin):
    cohort_id: str
    wallet: str
    membership_state: str
    source: str
    observed_at: str
    relationship_evidence: tuple[str, ...]
    relationship_uncertainty: str
    raw_references: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.cohort_id, "cohort_id")
        _address(self.wallet, "wallet")
        _require(self.membership_state in {"member", "not_member", "unknown"}, "unsupported membership_state")
        _text(self.source, "source")
        _timestamp(self.observed_at, "observed_at")
        _list_of_text(list(self.relationship_evidence), "relationship_evidence")
        _require(self.relationship_uncertainty in {"low", "medium", "high", "unknown"}, "unsupported relationship_uncertainty")
        _require(bool(self.raw_references), "raw_references cannot be empty")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WalletCohort":
        return cls(
            cohort_id=_text(data.get("cohort_id"), "cohort_id"),
            wallet=_address(data.get("wallet"), "wallet"),
            membership_state=_text(data.get("membership_state"), "membership_state"),
            source=_text(data.get("source"), "source"),
            observed_at=_timestamp(data.get("observed_at"), "observed_at"),
            relationship_evidence=_list_of_text(data.get("relationship_evidence"), "relationship_evidence"),
            relationship_uncertainty=_text(data.get("relationship_uncertainty"), "relationship_uncertainty"),
            raw_references=_list_of_text(data.get("raw_references"), "raw_references"),
        )


@dataclass(frozen=True)
class Observation(ContractMixin):
    subject_type: str
    subject_id: str
    as_of_time: str
    latest_included_event_time: str | None
    latest_included_arrival_time: str | None
    feature_version: str
    values: Mapping[str, Any]
    missingness: Mapping[str, str]
    quality_state: str
    lineage: tuple[str, ...]

    def __post_init__(self) -> None:
        _require(self.subject_type in {"token", "pool", "launch"}, "unsupported observation subject_type")
        _text(self.subject_id, "subject_id")
        _timestamp(self.as_of_time, "as_of_time")
        if self.latest_included_event_time is not None:
            _timestamp(self.latest_included_event_time, "latest_included_event_time")
        if self.latest_included_arrival_time is not None:
            _timestamp(self.latest_included_arrival_time, "latest_included_arrival_time")
        _text(self.feature_version, "feature_version")
        _mapping(self.values, "values")
        _mapping(self.missingness, "missingness")
        _require(self.quality_state in {"healthy", "stale", "degraded", "unknown"}, "unsupported quality_state")
        _require(bool(self.lineage), "lineage cannot be empty")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Observation":
        return cls(
            subject_type=_text(data.get("subject_type"), "subject_type"),
            subject_id=_text(data.get("subject_id"), "subject_id"),
            as_of_time=_timestamp(data.get("as_of_time"), "as_of_time"),
            latest_included_event_time=None if data.get("latest_included_event_time") is None else _timestamp(data["latest_included_event_time"], "latest_included_event_time"),
            latest_included_arrival_time=None if data.get("latest_included_arrival_time") is None else _timestamp(data["latest_included_arrival_time"], "latest_included_arrival_time"),
            feature_version=_text(data.get("feature_version"), "feature_version"),
            values=_mapping(data.get("values"), "values"),
            missingness=_mapping(data.get("missingness"), "missingness"),
            quality_state=_text(data.get("quality_state"), "quality_state"),
            lineage=_list_of_text(data.get("lineage"), "lineage"),
        )
