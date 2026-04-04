import unittest
import sys
import types
import os


class _DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


sys.modules.setdefault("loguru", types.SimpleNamespace(logger=_DummyLogger()))

os.environ.setdefault("KIS_APP_KEY", "test")
os.environ.setdefault("KIS_APP_SECRET", "test")
os.environ.setdefault("KIS_ACCOUNT_NO", "00000000-00")

from core.risk_manager import RiskManager


class DummyPosition:
    def __init__(self, total_value: int):
        self.total_value = total_value


class DummyPositionManager:
    def __init__(self):
        self.realized_pnl = 0
        self.open_count = 0
        self.positions = {}
        self._held = set()

    def has_position(self, stock_code: str) -> bool:
        return stock_code in self._held


class RiskManagerTest(unittest.TestCase):
    def test_blocks_when_daily_loss_hit(self):
        pm = DummyPositionManager()
        rm = RiskManager(pm)
        pm.realized_pnl = -rm.settings.max_daily_loss

        allowed, reason = rm.can_open_position("005930", 100_000)

        self.assertFalse(allowed)
        self.assertIn("일일 최대 손실", reason)

    def test_reduces_position_size_after_losses(self):
        pm = DummyPositionManager()
        rm = RiskManager(pm)
        rm.consecutive_losses = 3

        adjusted = rm.get_adjusted_position_size(100)

        self.assertEqual(adjusted, 50)


if __name__ == "__main__":
    unittest.main()
