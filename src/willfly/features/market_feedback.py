"""Causal market feedback derived from canonical V4 chain observations.

This module is the bridge between the read-only chain pipeline and the
learning store.  It intentionally uses only canonical, decoded ``Initialize``
and ``Swap`` logs.  A point is available at its raw ``received_time`` and a
forward label is not emitted as observed until a later market point has been
received.  No wallet activity, winner list, vendor score, or model output is
used to create a label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from willfly.adapters.protocols.v4 import (
    DecodedV4Event,
    DecodeError,
    deduplicate_decoded_events,
    decode_v4_event,
    pool_identity_from_initialize,
)
from willfly.domain import (
    Confidence,
    InstrumentIdentity,
    OutcomeRecord,
    PortfolioContext,
    PoolIdentity,
    PredictionRecord,
    RawEvent,
    default_signal_contract,
)


Q96 = 1 << 96
_ZERO_ADDRESS = "0x" + "0" * 40
_CORPUS_SCHEMA = "willfly.market-feedback-bundle.v0.1"


@dataclass(frozen=True)
class MarketPoint:
    """One canonical V4 price observation with exact integer price ratio."""

    point_id: str
    chain_id: int
    pool_id: str
    base_asset: str
    quote_asset: str
    event_time: str
    available_at: str
    price_numerator: int
    price_denominator: int
    sqrt_price_x96: int
    liquidity: int
    tick: int
    fee: int
    amount0: int
    amount1: int
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.point_id or not self.pool_id or not self.base_asset or not self.quote_asset:
            raise ValueError("market points require identity")
        if self.base_asset.lower() == self.quote_asset.lower():
            raise ValueError("market point base and quote assets must differ")
        event = _instant(self.event_time)
        available = _instant(self.available_at)
        if event > available:
            raise ValueError("market point event time cannot be after availability")
        if any(not isinstance(value, int) or isinstance(value, bool) for value in (
            self.chain_id,
            self.price_numerator,
            self.price_denominator,
            self.sqrt_price_x96,
            self.liquidity,
            self.tick,
            self.fee,
            self.amount0,
            self.amount1,
        )):
            raise ValueError("market point numeric fields must be integers")
        if self.chain_id <= 0 or self.price_numerator <= 0 or self.price_denominator <= 0 or self.sqrt_price_x96 <= 0:
            raise ValueError("market point price fields must be positive")
        if self.liquidity < 0 or self.fee < 0 or not self.source_refs:
            raise ValueError("market point liquidity, fee and lineage are invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "chain_id": self.chain_id,
            "pool_id": self.pool_id,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "event_time": self.event_time,
            "available_at": self.available_at,
            "price_numerator": str(self.price_numerator),
            "price_denominator": str(self.price_denominator),
            "sqrt_price_x96": str(self.sqrt_price_x96),
            "liquidity": str(self.liquidity),
            "tick": self.tick,
            "fee": self.fee,
            "amount0": str(self.amount0),
            "amount1": str(self.amount1),
            "source_refs": list(self.source_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MarketPoint":
        if not isinstance(data, Mapping):
            raise ValueError("market point must be an object")
        refs = data.get("source_refs")
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            raise ValueError("market point source_refs must be a string array")
        try:
            return cls(
                point_id=str(data["point_id"]),
                chain_id=int(data["chain_id"]),
                pool_id=str(data["pool_id"]),
                base_asset=str(data["base_asset"]),
                quote_asset=str(data["quote_asset"]),
                event_time=str(data["event_time"]),
                available_at=str(data["available_at"]),
                price_numerator=int(data["price_numerator"]),
                price_denominator=int(data["price_denominator"]),
                sqrt_price_x96=int(data["sqrt_price_x96"]),
                liquidity=int(data["liquidity"]),
                tick=int(data["tick"]),
                fee=int(data["fee"]),
                amount0=int(data["amount0"]),
                amount1=int(data["amount1"]),
                source_refs=tuple(refs),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("market point fields are malformed") from exc


def corpus_content_hashes(
    points: Iterable[MarketPoint],
    predictions: Iterable[PredictionRecord],
    outcomes: Iterable[OutcomeRecord],
    features_by_prediction: Mapping[str, Mapping[str, float]],
    partitions_by_prediction: Mapping[str, str],
) -> dict[str, str]:
    """Return hashes over normalized corpus content, including event lineage."""

    point_rows = [point.to_dict() for point in points]
    prediction_rows = [prediction.to_dict() for prediction in predictions]
    outcome_rows = [outcome.to_dict() for outcome in outcomes]
    feature_rows = {str(key): dict(value) for key, value in sorted(features_by_prediction.items())}
    partition_rows = {str(key): str(value) for key, value in sorted(partitions_by_prediction.items())}
    event_refs = sorted({ref for point in point_rows for ref in point["source_refs"]})

    def digest(value: object) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    return {
        "event_content_hash": digest(event_refs),
        "observation_content_hash": digest(point_rows),
        "predictions_content_hash": digest(prediction_rows),
        "outcomes_content_hash": digest(outcome_rows),
        "features_content_hash": digest(feature_rows),
        "partitions_content_hash": digest(partition_rows),
    }


def corpus_bundle_content_hash(bundle: Mapping[str, Any]) -> str:
    """Hash every bundle field except provenance, which stores this hash."""

    content = {str(key): value for key, value in bundle.items() if key != "provenance"}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MarketFeedbackCorpus:
    """Portable causal corpus and feedback records for the learning loop."""

    as_of_time: str
    source: str
    points: tuple[MarketPoint, ...]
    predictions: tuple[PredictionRecord, ...]
    outcomes: tuple[OutcomeRecord, ...]
    features_by_prediction: Mapping[str, Mapping[str, float]]
    partitions_by_prediction: Mapping[str, str]
    excluded: tuple[Mapping[str, str], ...]
    missingness: tuple[str, ...]
    lineage: tuple[str, ...]
    label_policy: Mapping[str, Any]
    split_policy: Mapping[str, Any]
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _instant(self.as_of_time)
        if not self.source:
            raise ValueError("market corpus source is required")
        prediction_ids = {prediction.prediction_id for prediction in self.predictions}
        feature_ids = set(self.features_by_prediction)
        partition_ids = set(self.partitions_by_prediction)
        if feature_ids != prediction_ids:
            missing = sorted(prediction_ids - feature_ids)
            extra = sorted(feature_ids - prediction_ids)
            raise ValueError(f"market corpus feature map identity mismatch: missing={missing}, extra={extra}")
        if partition_ids != prediction_ids:
            missing = sorted(prediction_ids - partition_ids)
            extra = sorted(partition_ids - prediction_ids)
            raise ValueError(f"market corpus partition map identity mismatch: missing={missing}, extra={extra}")
        for prediction_id, feature_map in self.features_by_prediction.items():
            if not isinstance(feature_map, Mapping):
                raise ValueError(f"market corpus feature map is not an object: {prediction_id}")
            for feature_name, value in feature_map.items():
                if not isinstance(feature_name, str) or not feature_name:
                    raise ValueError("market corpus feature names must be non-empty strings")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    raise ValueError(f"market corpus feature value is not finite: {prediction_id}:{feature_name}")
        if any(partition not in {"train", "validation", "test"} for partition in self.partitions_by_prediction.values()):
            raise ValueError("market corpus partitions must be train, validation or test")
        if not self.lineage:
            raise ValueError("market corpus lineage cannot be empty")
        if not isinstance(self.provenance, Mapping):
            raise ValueError("market corpus provenance must be an object")

    @property
    def observed_outcome_count(self) -> int:
        return sum(outcome.status == "observed" for outcome in self.outcomes)

    def to_bundle(self) -> dict[str, Any]:
        """Serialize a feedback-import-compatible bundle with corpus evidence."""

        bundle = {
            "schema_version": _CORPUS_SCHEMA,
            "as_of_time": self.as_of_time,
            "source": self.source,
            "market_observations": [point.to_dict() for point in self.points],
            "predictions": [prediction.to_dict() for prediction in self.predictions],
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
            "features_by_prediction": {
                prediction_id: dict(values)
                for prediction_id, values in sorted(self.features_by_prediction.items())
            },
            "partitions_by_prediction": dict(sorted(self.partitions_by_prediction.items())),
            "excluded": [dict(row) for row in self.excluded],
            "missingness": list(self.missingness),
            "lineage": list(self.lineage),
            "label_policy": dict(self.label_policy),
            "split_policy": dict(self.split_policy),
            "provenance": dict(self.provenance),
            "personal_trade_count": 0,
            "operating_mode": "read_only_observation_import",
            "execution_scope": "manual_only",
            "signing": False,
            "broadcast": False,
        }
        provenance = dict(bundle["provenance"])
        provenance["bundle_content_hash"] = corpus_bundle_content_hash(bundle)
        bundle["provenance"] = provenance
        return bundle


def build_market_feedback_corpus(
    raw_events: Iterable[RawEvent],
    *,
    as_of_time: str,
    source: str,
    pool_identities: Iterable[PoolIdentity] = (),
    horizons_seconds: tuple[int, ...] = (60, 300, 900),
    max_label_delay_seconds: int = 15,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    expected_emitter: str | None = None,
) -> MarketFeedbackCorpus:
    """Build observed-market feedback from canonical V4 logs only.

    The price orientation is ``currency0 per currency1``.  That makes the
    usual token-as-currency1 V4 pool produce a spot token return against its
    currency0 quote, while still preserving the exact orientation for unusual
    pools.  Labels use the first later point within the declared horizon
    window, with a bounded delayed-observation tolerance.  If the window has
    matured but no endpoint exists, a censored non-numeric outcome is retained;
    if the window has not matured, an unresolved outcome remains revisable.
    """

    cutoff = _instant(as_of_time)
    _validate_horizons(horizons_seconds)
    if max_label_delay_seconds < 0:
        raise ValueError("max_label_delay_seconds cannot be negative")
    if not 0 < train_fraction < 1 or not 0 <= validation_fraction < 1 or train_fraction + validation_fraction >= 1:
        raise ValueError("train and validation fractions must leave a positive test fraction")
    if expected_emitter is not None and (
        not isinstance(expected_emitter, str) or not expected_emitter.startswith("0x") or len(expected_emitter) != 42
    ):
        raise ValueError("expected_emitter must be a 20-byte hex address")
    expected_emitter = expected_emitter.lower() if expected_emitter is not None else None
    records = tuple(raw_events)
    excluded: list[dict[str, str]] = []
    canonical = []
    for event in records:
        if event.canonical_status != "canonical":
            excluded.append({"kind": "raw_event", "reference": _raw_ref(event), "reason": "noncanonical_raw_evidence"})
            continue
        if _instant(event.event_time) > cutoff or _instant(event.received_time) > cutoff:
            excluded.append({"kind": "raw_event", "reference": _raw_ref(event), "reason": "event_or_arrival_after_cutoff"})
            continue
        if _instant(event.event_time) > _instant(event.received_time):
            excluded.append({"kind": "raw_event", "reference": _raw_ref(event), "reason": "event_after_arrival"})
            continue
        try:
            decoded = decode_v4_event(event)
            if expected_emitter is not None and decoded.emitter.lower() != expected_emitter:
                excluded.append(
                    {
                        "kind": "raw_event",
                        "reference": _raw_ref(event),
                        "reason": "unexpected_v4_pool_manager",
                    }
                )
                continue
            canonical.append((decoded, event))
        except (DecodeError, ValueError) as exc:
            excluded.append({"kind": "raw_event", "reference": _raw_ref(event), "reason": f"decode_failed:{type(exc).__name__}"})
    decoded = deduplicate_decoded_events(item[0] for item in canonical)
    by_key = {item[0].raw_event_key: item[1] for item in canonical}
    identities: dict[str, tuple[PoolIdentity, RawEvent, DecodedV4Event]] = {}
    for item in decoded:
        if item.event_type != "Initialize":
            continue
        raw = by_key[item.raw_event_key]
        try:
            identity = pool_identity_from_initialize(item, chain_id=raw.chain_id, manager=item.emitter)
        except (DecodeError, ValueError) as exc:
            excluded.append({"kind": "initialize", "reference": _raw_ref(raw), "reason": f"identity_failed:{type(exc).__name__}"})
            continue
        pool_key = item.pool_id.lower()
        prior = identities.get(pool_key)
        if prior is not None and prior[0].to_dict() != identity.to_dict():
            raise ValueError(f"conflicting pool identity for {item.pool_id}")
        if prior is None or _sort_key(raw) < _sort_key(prior[1]):
            identities[pool_key] = (identity, raw, item)
    for identity in pool_identities:
        if identity.pool_id is None:
            excluded.append({"kind": "pool_identity", "reference": identity.manager_or_factory, "reason": "pool_id_missing"})
            continue
        pool_key = identity.pool_id.lower()
        prior = identities.get(pool_key)
        if prior is not None and prior[0].to_dict() != identity.to_dict():
            raise ValueError(f"conflicting supplied pool identity for {identity.pool_id}")
        if prior is None:
            # A supplied identity has no event timestamp.  It is safe for
            # already-canonical swap logs because it is an explicit operator
            # input; the input remains visible in the lineage.
            identities[pool_key] = (identity, _identity_sentinel(raw_records, identity), _identity_decoded(identity))

    points: list[MarketPoint] = []
    for item in decoded:
        if item.event_type != "Swap":
            continue
        raw = by_key[item.raw_event_key]
        identity_record = identities.get(item.pool_id.lower())
        if identity_record is None:
            excluded.append({"kind": "swap", "reference": _raw_ref(raw), "reason": "swap_pool_identity_unavailable"})
            continue
        identity, init_raw, _init = identity_record
        if init_raw is not None and init_raw.source != "identity" and (
            _instant(init_raw.event_time) > _instant(raw.event_time)
            or _instant(init_raw.received_time) > _instant(raw.received_time)
        ):
            excluded.append({"kind": "swap", "reference": _raw_ref(raw), "reason": "swap_before_pool_initialization"})
            continue
        if "unsupported_hook_behavior" in item.reason_flags:
            excluded.append({"kind": "swap", "reference": _raw_ref(raw), "reason": "unsupported_hook_behavior"})
            continue
        sqrt_price = _positive_int(item.fields.get("sqrt_price_x96"), "sqrt_price_x96")
        liquidity = _nonnegative_int(item.fields.get("liquidity"), "liquidity")
        fee = _nonnegative_int(item.fields.get("fee"), "fee")
        tick = _signed_int(item.fields.get("tick"), "tick")
        amount0 = _signed_int(item.fields.get("amount0"), "amount0")
        amount1 = _signed_int(item.fields.get("amount1"), "amount1")
        base_asset = _asset(identity.currency1)
        quote_asset = _asset(identity.currency0)
        point_id = "market-point:" + hashlib.sha256(
            json.dumps([raw.chain_id, raw.logical_key], separators=(",", ":")).encode()
        ).hexdigest()[:24]
        identity_ref = (
            f"identity:supplied:{item.pool_id}"
            if init_raw.source == "identity"
            else _raw_ref(init_raw)
        )
        points.append(
            MarketPoint(
                point_id=point_id,
                chain_id=raw.chain_id,
                pool_id=item.pool_id,
                base_asset=base_asset,
                quote_asset=quote_asset,
                event_time=raw.event_time,
                available_at=raw.received_time,
                price_numerator=Q96 * Q96,
                price_denominator=sqrt_price * sqrt_price,
                sqrt_price_x96=sqrt_price,
                liquidity=liquidity,
                tick=tick,
                fee=fee,
                amount0=amount0,
                amount1=amount1,
                source_refs=tuple(dict.fromkeys((*item.raw_lineage, identity_ref))),
            )
        )
    points = sorted(points, key=lambda point: (point.pool_id.lower(), _instant(point.event_time), _instant(point.available_at), point.point_id))
    features: dict[str, Mapping[str, float]] = {}
    points_by_pool: dict[str, list[MarketPoint]] = {}
    for point in points:
        points_by_pool.setdefault(point.pool_id.lower(), []).append(point)
    for pool_points in points_by_pool.values():
        # Features must follow arrival order.  Event-time order is still used
        # below for forward horizon matching, but an earlier chain event that
        # arrives later cannot become visible history for an older prediction.
        history_points = sorted(
            pool_points,
            key=lambda point: (_instant(point.available_at), _instant(point.event_time), point.point_id),
        )
        first = history_points[0]
        previous: MarketPoint | None = None
        for index, point in enumerate(history_points):
            previous_return = _price_return_bps(previous, point) if previous is not None else 0
            level_return = _price_return_bps(first, point) if point is not first else 0
            delta_seconds = 0 if previous is None else max(
                0, int((_instant(point.available_at) - _instant(previous.available_at)).total_seconds())
            )
            features[point.point_id] = {
                "market.price_change_bps": float(previous_return),
                "market.price_level_bps": float(level_return),
                "market.history_available": 0.0 if previous is None else 1.0,
                "market.seconds_since_previous_scaled": min(delta_seconds, 900) / 900.0,
                "market.tick_scaled": _clamp(point.tick / 1_000_000.0),
                "market.liquidity_log2_scaled": min(point.liquidity.bit_length() / 256.0, 1.0),
                "market.fee_scaled": min(point.fee / 1_000_000.0, 1.0),
                "market.amount0_sign": float(_sign(point.amount0)),
                "market.amount1_sign": float(_sign(point.amount1)),
                "market.sequence_index_scaled": min(index / 1024.0, 1.0),
            }
            previous = point

    contract = default_signal_contract()
    target_id = "spot_entry_net_return"
    target = contract.target(target_id)
    predictions: list[PredictionRecord] = []
    outcomes: list[OutcomeRecord] = []
    prediction_point: dict[str, MarketPoint] = {}
    for point in points:
        if point.available_at > as_of_time:
            continue
        for horizon in horizons_seconds:
            # ``point_id`` itself contains colons; use a delimiter that cannot
            # be confused with its stable identity when deriving split groups.
            prediction_id = f"{point.point_id}|{target_id}|{horizon}"
            prediction = PredictionRecord(
                prediction_id=prediction_id,
                contract_version=contract.schema_version,
                target_id=target_id,
                horizon_seconds=horizon,
                instrument=InstrumentIdentity(
                    chain_id=point.chain_id,
                    kind="token",
                    identifier=point.base_asset,
                    quote_asset=point.quote_asset,
                ),
                created_at=point.available_at,
                evidence_cutoff=point.event_time,
                expires_at=(_instant(point.available_at) + timedelta(seconds=horizon)).isoformat(),
                model_id="market-corpus-observation",
                model_version="market-corpus-v0.1",
                expected_value_bps=None,
                uncertainty_bps=None,
                confidence=Confidence("unavailable"),
                portfolio_context=PortfolioContext(
                    as_of_time=point.available_at,
                    position_state="unknown",
                    wallet_scope="none",
                    quality_state="healthy",
                    source_refs=point.source_refs,
                ),
                source_refs=point.source_refs,
            )
            contract.validate_prediction(prediction)
            predictions.append(prediction)
            prediction_point[prediction_id] = point
            outcomes.append(_forward_outcome(
                prediction,
                point,
                points_by_pool[point.pool_id.lower()],
                as_of_time=as_of_time,
                max_label_delay_seconds=max_label_delay_seconds,
            ))

    partitions = _chronological_partitions(
        predictions,
        train_fraction,
        validation_fraction,
        pool_by_prediction={prediction_id: prediction_point[prediction_id].pool_id for prediction_id in prediction_point},
    )
    lineage = tuple(dict.fromkeys(ref for point in points for ref in point.source_refs))
    if not points:
        missingness = ("no_canonical_v4_swap_points_at_cutoff",)
    else:
        missingness = ()
    if not outcomes or not any(outcome.status == "observed" for outcome in outcomes):
        missingness = tuple(dict.fromkeys((*missingness, "no_mature_observed_market_labels_at_cutoff")))
    return MarketFeedbackCorpus(
        as_of_time=as_of_time,
        source=source,
        points=tuple(points),
        predictions=tuple(predictions),
        outcomes=tuple(outcomes),
        features_by_prediction={
            prediction.prediction_id: features[prediction_point[prediction.prediction_id].point_id]
            for prediction in predictions
        },
        partitions_by_prediction=partitions,
        excluded=tuple(excluded),
        missingness=missingness,
        lineage=lineage or (f"market-corpus:{source}:{as_of_time}",),
        label_policy={
            "target_id": target_id,
            "horizons_seconds": list(horizons_seconds),
            "endpoint": "first_later_point_at_or_after_horizon",
            "max_label_delay_seconds": max_label_delay_seconds,
            "outcome_kind": "observed_market",
            "personal_trade_required": False,
        },
        split_policy={
            "kind": "chronological_by_market_point",
            "sort_key": "evidence_cutoff",
            "train_fraction": train_fraction,
            "validation_fraction": validation_fraction,
            "test_fraction": 1.0 - train_fraction - validation_fraction,
            "group_key": "pool_id",
            "group_isolation": True,
            "purge": "pool_id_group_isolation",
        },
        provenance={
            "source": source,
            "canonical_event_set_hash": _canonical_event_set_hash(records, cutoff),
            "canonical_event_set_cutoff": as_of_time,
            "expected_emitter": expected_emitter,
            **corpus_content_hashes(
                points,
                predictions,
                outcomes,
                {
                    prediction.prediction_id: features[prediction_point[prediction.prediction_id].point_id]
                    for prediction in predictions
                },
                partitions,
            ),
        },
    )


def _forward_outcome(
    prediction: PredictionRecord,
    point: MarketPoint,
    pool_points: Sequence[MarketPoint],
    *,
    as_of_time: str,
    max_label_delay_seconds: int,
) -> OutcomeRecord:
    target_time = _instant(point.event_time) + timedelta(seconds=prediction.horizon_seconds)
    label_ref = f"market-window:{point.point_id}:{prediction.horizon_seconds}"
    candidates = [
        candidate
        for candidate in pool_points
        if _instant(candidate.event_time) > _instant(point.event_time)
        and _instant(candidate.event_time) >= target_time
        and _instant(candidate.event_time) <= target_time + timedelta(seconds=max_label_delay_seconds)
        and _instant(candidate.available_at) > _instant(point.available_at)
        and _instant(candidate.available_at) <= _instant(as_of_time)
    ]
    candidates.sort(key=lambda candidate: (_instant(candidate.event_time), _instant(candidate.available_at), candidate.point_id))
    candidate = candidates[0] if candidates else None
    outcome_id = f"outcome:{prediction.prediction_id}"
    if candidate is not None:
        return OutcomeRecord(
            outcome_id=outcome_id,
            prediction_id=prediction.prediction_id,
            target_id=prediction.target_id,
            outcome_kind="observed_market",
            status="observed",
            # Historical backfills can arrive after the chain event timestamp
            # (sometimes by a day).  The endpoint's arrival is the first time
            # this label was observable to the operator, so using it keeps the
            # feedback join causal without changing horizon matching.
            observed_at=candidate.available_at,
            label_available_at=candidate.available_at,
            net_return_bps=_price_return_bps(point, candidate),
            source_refs=tuple(dict.fromkeys((*point.source_refs, *candidate.source_refs))),
        )
    if _instant(as_of_time) >= target_time:
        # A backfilled historical window can have a chain-time horizon before
        # the prediction's arrival.  The censored label becomes observable only
        # after both the horizon and the prediction itself are known.
        censored_observed_at = max(target_time, _instant(point.available_at)).isoformat()
        return OutcomeRecord(
            outcome_id=outcome_id,
            prediction_id=prediction.prediction_id,
            target_id=prediction.target_id,
            outcome_kind="observed_market",
            status="censored",
            observed_at=censored_observed_at,
            label_available_at=as_of_time,
            net_return_bps=None,
            source_refs=tuple(dict.fromkeys((*point.source_refs, label_ref))),
        )
    return OutcomeRecord(
        outcome_id=outcome_id,
        prediction_id=prediction.prediction_id,
        target_id=prediction.target_id,
        outcome_kind="observed_market",
        status="unresolved",
        observed_at=target_time.isoformat(),
        label_available_at=None,
        net_return_bps=None,
        source_refs=tuple(dict.fromkeys((*point.source_refs, label_ref))),
    )


def _chronological_partitions(
    predictions: Sequence[PredictionRecord],
    train_fraction: float,
    validation_fraction: float,
    *,
    pool_by_prediction: Mapping[str, str] | None = None,
) -> dict[str, str]:
    group_ids = []
    seen: set[str] = set()
    for prediction in sorted(predictions, key=lambda item: (item.evidence_cutoff, item.created_at, item.prediction_id)):
        point_id = prediction.prediction_id.rsplit("|", 2)[0]
        group_id = (pool_by_prediction or {}).get(prediction.prediction_id, point_id).lower()
        if group_id not in seen:
            seen.add(group_id)
            group_ids.append(group_id)
    count = len(group_ids)
    train_end = max(1, min(count, math.floor(count * train_fraction))) if count else 0
    validation_end = max(train_end, min(count, math.floor(count * (train_fraction + validation_fraction))))
    if count >= 3:
        train_end = min(train_end, count - 2)
        validation_end = max(train_end + 1, min(validation_end, count - 1))
    labels = {
        group_id: "train" if index < train_end else "validation" if index < validation_end else "test"
        for index, group_id in enumerate(group_ids)
    }
    return {
        prediction.prediction_id: labels[(pool_by_prediction or {}).get(
            prediction.prediction_id, prediction.prediction_id.rsplit("|", 2)[0]
        ).lower()]
        for prediction in predictions
    }


def _canonical_event_set_hash(records: Sequence[RawEvent], cutoff: datetime) -> str:
    selected = [
        event.to_dict()
        for event in records
        if event.canonical_status == "canonical"
        and _instant(event.event_time) <= cutoff
        and _instant(event.received_time) <= cutoff
    ]
    # RawEvent.to_dict intentionally does not expose the computed logical key;
    # sorting by the stable serialized identity keeps the hash deterministic.
    selected.sort(key=lambda event: json.dumps(event, sort_keys=True, separators=(",", ":")))
    encoded = json.dumps(selected, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _price_return_bps(start: MarketPoint | None, end: MarketPoint) -> int:
    if start is None:
        return 0
    numerator = end.price_numerator * start.price_denominator
    denominator = start.price_numerator * end.price_denominator
    return (numerator - denominator) * 10_000 // denominator


def _identity_sentinel(records: Sequence[RawEvent], identity: PoolIdentity) -> RawEvent:
    # This object is never decoded or included in lineage.  Keeping a typed
    # sentinel lets the identity path share the same temporal checks while
    # making supplied identities explicit in the generated bundle.
    return RawEvent(
        chain_id=identity.chain_id,
        source="identity",
        source_schema_version="identity.v0.1",
        block_number=0,
        block_hash="0x" + "0" * 64,
        parent_hash=None,
        transaction_hash=None,
        log_index=None,
        event_time="1970-01-01T00:00:00+00:00",
        received_time="1970-01-01T00:00:00+00:00",
        payload={},
        ingestion_run="identity",
        canonical_status="canonical",
    )


def _identity_decoded(identity: PoolIdentity) -> DecodedV4Event:
    return DecodedV4Event(
        event_type="Initialize",
        pool_id=identity.pool_id or "",
        sender=None,
        emitter=identity.manager_or_factory,
        fields={},
        raw_event_key=(identity.chain_id, None, None, None),
        raw_lineage=("identity:supplied",),
    )


def _raw_ref(event: RawEvent) -> str:
    return "raw:" + event.source + ":" + ":".join(str(part) for part in event.logical_key)


def _sort_key(event: RawEvent) -> tuple[datetime, datetime, tuple[Any, ...]]:
    return (_instant(event.event_time), _instant(event.received_time), event.logical_key)


def _asset(value: str) -> str:
    return "native:ETH" if value.lower() == _ZERO_ADDRESS else value


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("market corpus timestamps must include a timezone")
    return parsed


def _validate_horizons(horizons: tuple[int, ...]) -> None:
    if not horizons or tuple(sorted(set(horizons))) != horizons or any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in horizons
    ):
        raise ValueError("horizons must be sorted, unique positive integers")
    contract_horizons = default_signal_contract().horizons_seconds
    if tuple(horizons) != contract_horizons:
        raise ValueError("market corpus horizons must match the frozen signal contract")


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{field} must be a positive integer")
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return parsed


def _nonnegative_int(value: Any, field: str) -> int:
    parsed = _positive_int(value, field) if value not in {0, "0"} else 0
    return parsed


def _signed_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{field} must be an integer")
    return int(value)


def _sign(value: int) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


__all__ = [
    "MarketFeedbackCorpus",
    "MarketPoint",
    "Q96",
    "build_market_feedback_corpus",
    "corpus_bundle_content_hash",
    "corpus_content_hashes",
]
