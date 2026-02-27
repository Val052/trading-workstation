"""Risk calculator — position sizing, R-multiples, stop/target math."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskCalc:
    """Full risk/reward calculation for a trade setup."""
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float | None
    risk_per_share: float
    reward_per_share: float
    r_multiple: float
    position_size: int
    dollar_risk: float
    dollar_reward: float
    account_risk_pct: float

    def to_dict(self) -> dict:
        return {
            "entry_price": round(self.entry_price, 2),
            "stop_loss": round(self.stop_loss, 2),
            "target_1": round(self.target_1, 2),
            "target_2": round(self.target_2, 2) if self.target_2 else None,
            "risk_per_share": round(self.risk_per_share, 2),
            "reward_per_share": round(self.reward_per_share, 2),
            "r_multiple": round(self.r_multiple, 2),
            "position_size": self.position_size,
            "dollar_risk": round(self.dollar_risk, 2),
            "dollar_reward": round(self.dollar_reward, 2),
            "account_risk_pct": round(self.account_risk_pct, 4),
            "r_targets": {
                "1R": round(self.entry_price + self.risk_per_share, 2),
                "2R": round(self.entry_price + 2 * self.risk_per_share, 2),
                "3R": round(self.entry_price + 3 * self.risk_per_share, 2),
            },
        }


def calculate_risk(
    entry_price: float,
    stop_loss: float,
    target_1: float,
    account_size: float,
    risk_per_trade: float,
    target_2: float | None = None,
) -> RiskCalc:
    """
    Calculate position sizing and R-multiples.

    Args:
        entry_price: planned entry price
        stop_loss: stop loss level
        target_1: primary price target
        account_size: total account value
        risk_per_trade: max risk as decimal (0.005 = 0.5%)
        target_2: optional secondary target

    Returns:
        RiskCalc with all computed fields
    """
    risk_per_share = abs(entry_price - stop_loss)
    reward_per_share = abs(target_1 - entry_price)

    if risk_per_share == 0:
        raise ValueError("Risk per share cannot be zero (entry == stop)")

    r_multiple = reward_per_share / risk_per_share

    # Position sizing: how many shares to risk exactly risk_per_trade of account
    max_dollar_risk = account_size * risk_per_trade
    position_size = int(max_dollar_risk / risk_per_share)

    # Actual dollar risk/reward at this position size
    dollar_risk = position_size * risk_per_share
    dollar_reward = position_size * reward_per_share
    account_risk_pct = dollar_risk / account_size if account_size > 0 else 0

    return RiskCalc(
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
        r_multiple=r_multiple,
        position_size=position_size,
        dollar_risk=dollar_risk,
        dollar_reward=dollar_reward,
        account_risk_pct=account_risk_pct,
    )


def suggest_targets(entry_price: float, stop_loss: float) -> dict:
    """Suggest 1R, 2R, 3R targets based on entry and stop."""
    risk = abs(entry_price - stop_loss)
    direction = 1 if entry_price > stop_loss else -1  # long vs short
    return {
        "1R": round(entry_price + direction * risk, 2),
        "2R": round(entry_price + direction * 2 * risk, 2),
        "3R": round(entry_price + direction * 3 * risk, 2),
    }
