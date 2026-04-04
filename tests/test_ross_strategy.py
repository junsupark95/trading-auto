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

from strategy.ross_cameron import RossCameronStrategy, TradeSignal


class RossStrategyTest(unittest.TestCase):
    def setUp(self):
        self.strategy = RossCameronStrategy()

    def test_exit_on_stop_loss(self):
        signal = self.strategy.check_exit(
            stock_code="005930",
            entry_price=10_000,
            current_price=9_700,   # -3%
            highest_since_entry=10_000,
            minutes_held=5,
            df=None,
        )
        self.assertEqual(signal.action, TradeSignal.SELL)
        self.assertGreaterEqual(signal.confidence, 0.9)

    def test_exit_on_take_profit(self):
        signal = self.strategy.check_exit(
            stock_code="005930",
            entry_price=10_000,
            current_price=10_500,  # +5%
            highest_since_entry=10_600,
            minutes_held=10,
            df=None,
        )
        self.assertEqual(signal.action, TradeSignal.SELL)
        self.assertGreaterEqual(signal.confidence, 0.9)


if __name__ == "__main__":
    unittest.main()
