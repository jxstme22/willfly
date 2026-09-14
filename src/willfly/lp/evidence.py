"""Fail-closed evidence requirements for LP recommendations."""

from __future__ import annotations

from dataclasses import dataclass


ROBINHOOD_CHAIN_ID = 4663


@dataclass(frozen=True)
class LPEvidence:
    """Evidence required before an LP policy can be recommended.

    A fixture or a protocol documentation page can support mechanics tests,
    but neither satisfies this gate. Every field is explicit so a caller cannot
    promote LP merely by changing a status string.
    """

    protocol: str = "uniswap_v4"
    chain_id: int | None = None
    deployment_ref: str | None = None
    bytecode_ref: str | None = None
    live_protocol_verified: bool = False
    token_order_verified: bool = False
    tick_math_verified: bool = False
    hook_behavior_verified: bool = False
    supported_tokens_verified: bool = False
    position_state_verified: bool = False
    receipt_accounting_verified: bool = False
    gas_denomination_verified: bool = False
    complete_receipts_verified: bool = False
    observed_checkpoint_count: int = 0
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.protocol != "uniswap_v4":
            raise ValueError("only the declared Uniswap V4 family is supported")
        if self.chain_id is not None and (not isinstance(self.chain_id, int) or isinstance(self.chain_id, bool) or self.chain_id <= 0):
            raise ValueError("chain_id must be a positive integer")
        for field_name in (
            "deployment_ref",
            "bytecode_ref",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be non-empty text")
        for field_name in (
            "live_protocol_verified",
            "token_order_verified",
            "tick_math_verified",
            "hook_behavior_verified",
            "supported_tokens_verified",
            "position_state_verified",
            "receipt_accounting_verified",
            "gas_denomination_verified",
            "complete_receipts_verified",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be boolean")
        if not isinstance(self.observed_checkpoint_count, int) or isinstance(self.observed_checkpoint_count, bool) or self.observed_checkpoint_count < 0:
            raise ValueError("observed_checkpoint_count must be a non-negative integer")
        if not isinstance(self.source_refs, tuple) or not all(isinstance(ref, str) and ref for ref in self.source_refs):
            raise ValueError("source_refs must contain non-empty text")

    @property
    def qualifies(self) -> bool:
        """Whether all declared live protocol and accounting requirements pass."""

        return bool(
            self.chain_id == ROBINHOOD_CHAIN_ID
            and self.deployment_ref
            and self.bytecode_ref
            and self.live_protocol_verified
            and self.token_order_verified
            and self.tick_math_verified
            and self.hook_behavior_verified
            and self.supported_tokens_verified
            and self.position_state_verified
            and self.receipt_accounting_verified
            and self.gas_denomination_verified
            and self.complete_receipts_verified
            and self.observed_checkpoint_count > 0
            and bool(self.source_refs)
        )

    @property
    def reason_flags(self) -> tuple[str, ...]:
        if self.qualifies:
            return ()
        missing = []
        for name in (
            "live_protocol_verified",
            "token_order_verified",
            "tick_math_verified",
            "hook_behavior_verified",
            "supported_tokens_verified",
            "position_state_verified",
            "receipt_accounting_verified",
            "gas_denomination_verified",
            "complete_receipts_verified",
        ):
            if not getattr(self, name):
                missing.append(f"missing_{name}")
        if not self.deployment_ref:
            missing.append("missing_deployment_evidence")
        if self.chain_id != ROBINHOOD_CHAIN_ID:
            missing.append("unsupported_or_unverified_robinhood_chain")
        if not self.bytecode_ref:
            missing.append("missing_bytecode_evidence")
        if not self.source_refs:
            missing.append("missing_live_source_refs")
        if self.observed_checkpoint_count <= 0:
            missing.append("missing_observed_position_checkpoint")
        return tuple(missing)


def is_verified_live_evidence(evidence: LPEvidence | None) -> bool:
    return evidence is not None and evidence.qualifies


def evidence_status(evidence: LPEvidence | None) -> str:
    if evidence is None:
        return "unavailable"
    return "verified" if evidence.qualifies else "inconclusive"


__all__ = ["LPEvidence", "ROBINHOOD_CHAIN_ID", "evidence_status", "is_verified_live_evidence"]
