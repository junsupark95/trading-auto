"""기술적 지표 계산 모듈"""

import numpy as np
import pandas as pd


class TechnicalIndicators:
    """로스 카메론 전략에 사용되는 기술적 지표"""

    @staticmethod
    def vwap(df: pd.DataFrame) -> pd.Series:
        """VWAP (Volume Weighted Average Price) 계산

        로스 카메론 핵심 지표: VWAP 위에서만 롱 진입
        """
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        cum_tp_vol = (typical_price * df["volume"]).cumsum()
        cum_vol = df["volume"].cumsum()
        return cum_tp_vol / cum_vol.replace(0, np.nan)

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        """지수이동평균"""
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        """단순이동평균"""
        return series.rolling(window=period).mean()

    @staticmethod
    def relative_volume(df: pd.DataFrame, lookback: int = 20) -> float:
        """상대 거래량 (현재 거래량 / 평균 거래량)"""
        if len(df) < lookback:
            return 0.0
        avg_vol = df["volume"].iloc[-lookback:].mean()
        current_vol = df["volume"].iloc[-1]
        return current_vol / avg_vol if avg_vol > 0 else 0.0

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """ATR (Average True Range) - 손절/익절 설정용"""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @staticmethod
    def support_resistance(df: pd.DataFrame, window: int = 5) -> dict:
        """지지/저항 레벨 계산"""
        highs = df["high"].rolling(window=window, center=True).max()
        lows = df["low"].rolling(window=window, center=True).min()

        resistance_levels = df.loc[df["high"] == highs, "high"].unique()
        support_levels = df.loc[df["low"] == lows, "low"].unique()

        return {
            "resistance": sorted(resistance_levels, reverse=True)[:5],
            "support": sorted(support_levels)[:5],
        }

    @staticmethod
    def is_bullish_candle(row: pd.Series) -> bool:
        """양봉 여부"""
        return row["close"] > row["open"]

    @staticmethod
    def candle_body_ratio(row: pd.Series) -> float:
        """캔들 몸통 비율 (강한 모멘텀 판별)"""
        total_range = row["high"] - row["low"]
        if total_range == 0:
            return 0.0
        body = abs(row["close"] - row["open"])
        return body / total_range

    @classmethod
    def compute_all(cls, df: pd.DataFrame, ma_periods: list[int] = None) -> pd.DataFrame:
        """모든 지표를 한번에 계산하여 DataFrame에 추가"""
        if ma_periods is None:
            ma_periods = [9, 20]

        result = df.copy()

        # VWAP
        result["vwap"] = cls.vwap(df)

        # 이동평균
        for period in ma_periods:
            result[f"ema_{period}"] = cls.ema(df["close"], period)
            result[f"sma_{period}"] = cls.sma(df["close"], period)

        # ATR
        result["atr"] = cls.atr(df)

        return result
