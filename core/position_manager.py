from __future__ import annotations

"""포지션 관리 모듈"""

import json
from datetime import datetime
from pathlib import Path
from loguru import logger
import pytz

KST = pytz.timezone("Asia/Seoul")


class Position:
    """개별 포지션"""

    def __init__(self, stock_code: str, stock_name: str, qty: int,
                 entry_price: int, stop_loss: int = 0, take_profit: int = 0):
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.qty = qty
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.entry_time = datetime.now(KST)
        self.highest_price = entry_price
        self.current_price = entry_price
        self.order_no = ""
        self.ai_reasoning = ""

    @property
    def pnl(self) -> int:
        """손익 (원)"""
        return (self.current_price - self.entry_price) * self.qty

    @property
    def pnl_pct(self) -> float:
        """수익률 (%)"""
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price * 100

    @property
    def total_value(self) -> int:
        """평가 금액"""
        return self.current_price * self.qty

    @property
    def minutes_held(self) -> int:
        """보유 시간 (분)"""
        delta = datetime.now(KST) - self.entry_time
        return int(delta.total_seconds() / 60)

    def update_price(self, price: int):
        """현재가 업데이트"""
        self.current_price = price
        if price > self.highest_price:
            self.highest_price = price

    def to_dict(self) -> dict:
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "qty": self.qty,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "highest_price": self.highest_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "minutes_held": self.minutes_held,
            "entry_time": self.entry_time.isoformat(),
            "order_no": self.order_no,
            "ai_reasoning": self.ai_reasoning,
        }


class PositionManager:
    """포지션 관리자"""

    def __init__(self):
        self.positions: dict[str, Position] = {}
        self.closed_trades: list[dict] = []
        self.state_file = Path("logs/positions.json")
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def open_position(self, stock_code: str, stock_name: str, qty: int,
                      entry_price: int, stop_loss: int = 0,
                      take_profit: int = 0, order_no: str = "",
                      ai_reasoning: str = "") -> Position:
        """포지션 오픈"""
        pos = Position(stock_code, stock_name, qty, entry_price,
                       stop_loss, take_profit)
        pos.order_no = order_no
        pos.ai_reasoning = ai_reasoning
        self.positions[stock_code] = pos
        self._save_state()
        logger.info(
            f"포지션 오픈: {stock_name}({stock_code}) "
            f"{qty}주 @ {entry_price:,}원 "
            f"(손절: {stop_loss:,} / 익절: {take_profit:,})"
        )
        return pos

    def close_position(self, stock_code: str, exit_price: int,
                       reason: str = "") -> dict | None:
        """포지션 청산"""
        pos = self.positions.pop(stock_code, None)
        if pos is None:
            logger.warning(f"청산할 포지션 없음: {stock_code}")
            return None

        pos.current_price = exit_price
        trade_record = {
            **pos.to_dict(),
            "exit_price": exit_price,
            "exit_time": datetime.now(KST).isoformat(),
            "exit_reason": reason,
            "realized_pnl": (exit_price - pos.entry_price) * pos.qty,
            "realized_pnl_pct": pos.pnl_pct,
        }
        self.closed_trades.append(trade_record)
        self._save_state()

        logger.info(
            f"포지션 청산: {pos.stock_name}({stock_code}) "
            f"{pos.qty}주 @ {exit_price:,}원 "
            f"(수익: {trade_record['realized_pnl']:+,}원 / "
            f"{trade_record['realized_pnl_pct']:+.2f}%) "
            f"사유: {reason}"
        )
        return trade_record

    def update_price(self, stock_code: str, price: int):
        """포지션 현재가 업데이트"""
        if stock_code in self.positions:
            self.positions[stock_code].update_price(price)

    def get_position(self, stock_code: str) -> Position | None:
        return self.positions.get(stock_code)

    def has_position(self, stock_code: str) -> bool:
        return stock_code in self.positions

    @property
    def open_count(self) -> int:
        return len(self.positions)

    @property
    def total_pnl(self) -> int:
        """미실현 + 실현 총 손익"""
        unrealized = sum(p.pnl for p in self.positions.values())
        realized = sum(t["realized_pnl"] for t in self.closed_trades)
        return unrealized + realized

    @property
    def realized_pnl(self) -> int:
        return sum(t["realized_pnl"] for t in self.closed_trades)

    @property
    def winning_trades(self) -> int:
        return sum(1 for t in self.closed_trades if t["realized_pnl"] > 0)

    @property
    def win_rate(self) -> float:
        total = len(self.closed_trades)
        if total == 0:
            return 0.0
        return self.winning_trades / total * 100

    def get_summary(self) -> dict:
        """전체 포지션 요약"""
        return {
            "open_positions": [p.to_dict() for p in self.positions.values()],
            "open_count": self.open_count,
            "closed_trades": self.closed_trades,
            "total_trades": len(self.closed_trades),
            "winning_trades": self.winning_trades,
            "win_rate": self.win_rate,
            "realized_pnl": self.realized_pnl,
            "total_pnl": self.total_pnl,
        }

    def _save_state(self):
        """상태 저장"""
        state = {
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "closed_trades": self.closed_trades,
            "saved_at": datetime.now(KST).isoformat(),
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, default=str)
