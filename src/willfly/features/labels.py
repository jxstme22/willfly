"""Forward labels that never use pre-observation future outcomes as features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from willfly.domain import OutcomeRecord


@dataclass(frozen=True)
class ForwardEpisode:
    episode_id: str
    subject_id: str
    entry_event_time: str
    entry_available_at: str
    exit_event_time: str | None
    exit_available_at: str | None
    cost_atomic: int | None
    proceeds_atomic: int | None
    adverse_excursion_bps: int | None
    source_refs: tuple[str, ...]
    failed: bool = False
    unsellable: bool = False

    def __post_init__(self) -> None:
        if not self.episode_id or not self.subject_id or not self.source_refs:
            raise ValueError("forward episodes require identity and source references")
        for value in (self.entry_event_time, self.entry_available_at, self.exit_event_time, self.exit_available_at):
            if value is not None:
                _parse(value)
        if self.cost_atomic is not None and self.cost_atomic <= 0:
            raise ValueError("episode cost must be positive")
        if self.proceeds_atomic is not None and self.proceeds_atomic < 0:
            raise ValueError("episode proceeds cannot be negative")
        if self.adverse_excursion_bps is not None and self.adverse_excursion_bps < 0:
            raise ValueError("adverse excursion cannot be negative")


@dataclass(frozen=True)
class OutcomeLabel:
    episode_id: str
    subject_id: str
    observation_time: str
    horizon_seconds: int
    status: str
    net_return_bps: int | None
    adverse_excursion_bps: int | None
    entry_feasible: bool
    exit_feasible: bool
    label_available_at: str | None
    source_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def build_forward_labels(
    *,
    observation_time: str,
    observation_available_at: str,
    episodes: Iterable[ForwardEpisode],
    horizons_seconds: tuple[int, ...] = (60, 300, 900),
) -> tuple[OutcomeLabel, ...]:
    """Build censored/unresolved labels from episodes after the observation."""

    observed_at = _parse(observation_time)
    available_at = _parse(observation_available_at)
    if any(horizon <= 0 for horizon in horizons_seconds):
        raise ValueError("label horizons must be positive")
    records = tuple(episodes)
    labels: list[OutcomeLabel] = []
    for episode in sorted(records, key=lambda item: (item.entry_event_time, item.episode_id)):
        entry_time = _parse(episode.entry_event_time)
        if entry_time <= observed_at:
            continue
        for horizon in horizons_seconds:
            horizon_end = observed_at + timedelta(seconds=horizon)
            if entry_time > horizon_end:
                continue
            if episode.failed or episode.unsellable:
                labels.append(_label(episode, observation_time, horizon, "unresolved", None, False, False, None))
                continue
            exit_time = _parse(episode.exit_event_time) if episode.exit_event_time else None
            if exit_time is None or exit_time > horizon_end:
                labels.append(_label(episode, observation_time, horizon, "censored", None, True, False, None))
                continue
            if episode.cost_atomic is None or episode.proceeds_atomic is None:
                labels.append(_label(episode, observation_time, horizon, "unresolved", None, False, False, None))
                continue
            if _parse(episode.entry_available_at) < available_at:
                labels.append(_label(episode, observation_time, horizon, "unresolved", None, False, False, None))
                continue
            net_return_bps = (episode.proceeds_atomic - episode.cost_atomic) * 10_000 // episode.cost_atomic
            labels.append(
                _label(
                    episode,
                    observation_time,
                    horizon,
                    "observed",
                    net_return_bps,
                    True,
                    episode.exit_available_at is not None,
                    episode.exit_available_at,
                )
            )
    return tuple(labels)


def outcome_from_forward_label(
    label: OutcomeLabel,
    *,
    prediction_id: str,
    target_id: str,
) -> OutcomeRecord:
    """Adapt one causal horizon label to the B3 outcome contract."""

    if not prediction_id or not target_id:
        raise ValueError("prediction_id and target_id are required")
    if label.status not in {"observed", "censored", "unresolved"}:
        raise ValueError("unsupported forward label status")
    if label.status == "observed" and label.label_available_at is None:
        raise ValueError("observed forward labels require label availability")
    outcome_id = f"outcome:{prediction_id}:{target_id}:{label.horizon_seconds}:{label.episode_id}"
    return OutcomeRecord(
        outcome_id=outcome_id,
        prediction_id=prediction_id,
        target_id=target_id,
        outcome_kind="observed_market",
        status=label.status,
        observed_at=label.observation_time,
        label_available_at=label.label_available_at,
        net_return_bps=label.net_return_bps,
        source_refs=label.source_refs,
    )


def _label(
    episode: ForwardEpisode,
    observation_time: str,
    horizon: int,
    status: str,
    net_return_bps: int | None,
    entry_feasible: bool,
    exit_feasible: bool,
    label_available_at: str | None,
) -> OutcomeLabel:
    return OutcomeLabel(
        episode.episode_id,
        episode.subject_id,
        observation_time,
        horizon,
        status,
        net_return_bps,
        episode.adverse_excursion_bps,
        entry_feasible,
        exit_feasible,
        label_available_at,
        episode.source_refs,
    )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed
