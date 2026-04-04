"""실시간 트레이딩 대시보드 (Streamlit)

실행: streamlit run dashboard/app.py
"""

import json
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import pytz

KST = pytz.timezone("Asia/Seoul")

# ========== 페이지 설정 ==========
st.set_page_config(
    page_title="AI 트레이딩 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ========== 자동 새로고침 ==========
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=5000, key="auto_refresh")  # 5초마다 갱신
except ImportError:
    pass


def load_dashboard_data() -> dict:
    """대시보드 데이터 로드 (엔진이 저장한 JSON)"""
    data_file = Path("logs/dashboard_state.json")
    if data_file.exists():
        with open(data_file, encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_trade_log() -> list:
    """오늘 거래 로그 로드"""
    today = datetime.now(KST).strftime("%Y%m%d")
    log_file = Path(f"logs/trades_{today}.json")
    if log_file.exists():
        with open(log_file, encoding="utf-8") as f:
            return json.load(f)
    return []


def main():
    data = load_dashboard_data()
    trade_log = load_trade_log()

    # ========== 헤더 ==========
    col_title, col_status = st.columns([3, 1])
    with col_title:
        st.title("AI 모멘텀 트레이딩 시스템")
        st.caption("Ross Cameron Strategy | Claude + GPT + Gemini")
    with col_status:
        is_running = data.get("is_running", False)
        if is_running:
            st.success("LIVE 운영 중", icon="🟢")
        else:
            st.warning("대기 중", icon="🟡")
        st.text(f"갱신: {datetime.now(KST).strftime('%H:%M:%S')}")

    st.divider()

    # ========== 핵심 지표 (KPI) ==========
    positions = data.get("positions", {})
    risk = data.get("risk", {})

    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

    realized_pnl = positions.get("realized_pnl", 0)
    total_pnl = positions.get("total_pnl", 0)
    win_rate = positions.get("win_rate", 0)
    total_trades = positions.get("total_trades", 0)
    open_count = positions.get("open_count", 0)

    kpi1.metric("실현 손익", f"{realized_pnl:+,}원",
                delta=f"{realized_pnl:+,}" if realized_pnl != 0 else None)
    kpi2.metric("총 손익 (미실현 포함)", f"{total_pnl:+,}원")
    kpi3.metric("승률", f"{win_rate:.1f}%",
                delta=f"{total_trades}건 중 {positions.get('winning_trades', 0)}승")
    kpi4.metric("총 거래", f"{total_trades}건")
    kpi5.metric("보유 종목", f"{open_count}개",
                delta=f"최대 {risk.get('max_positions', 5)}개")

    st.divider()

    # ========== 메인 레이아웃 ==========
    left_col, right_col = st.columns([2, 1])

    # ---------- 왼쪽: 보유 포지션 & 거래 로그 ----------
    with left_col:
        st.subheader("보유 포지션")
        open_positions = positions.get("open_positions", [])
        if open_positions:
            pos_df = pd.DataFrame(open_positions)
            display_cols = {
                "stock_name": "종목명",
                "stock_code": "종목코드",
                "qty": "수량",
                "entry_price": "진입가",
                "current_price": "현재가",
                "pnl": "손익(원)",
                "pnl_pct": "수익률(%)",
                "stop_loss": "손절가",
                "take_profit": "익절가",
                "minutes_held": "보유시간(분)",
            }
            available_cols = [c for c in display_cols if c in pos_df.columns]
            display_df = pos_df[available_cols].rename(
                columns={c: display_cols[c] for c in available_cols}
            )

            # 수익률 색상
            st.dataframe(
                display_df.style.applymap(
                    lambda v: "color: red" if isinstance(v, (int, float)) and v < 0
                    else "color: green" if isinstance(v, (int, float)) and v > 0
                    else "",
                    subset=[c for c in ["손익(원)", "수익률(%)"] if c in display_df.columns],
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("현재 보유 중인 포지션이 없습니다.")

        # 손익 차트
        st.subheader("거래 손익 추이")
        closed_trades = positions.get("closed_trades", [])
        if closed_trades:
            trades_df = pd.DataFrame(closed_trades)
            trades_df["cumulative_pnl"] = trades_df["realized_pnl"].cumsum()

            fig = go.Figure()
            colors = ["green" if v >= 0 else "red" for v in trades_df["realized_pnl"]]
            fig.add_trace(go.Bar(
                x=list(range(1, len(trades_df) + 1)),
                y=trades_df["realized_pnl"],
                marker_color=colors,
                name="개별 손익",
            ))
            fig.add_trace(go.Scatter(
                x=list(range(1, len(trades_df) + 1)),
                y=trades_df["cumulative_pnl"],
                mode="lines+markers",
                name="누적 손익",
                line=dict(color="blue", width=2),
            ))
            fig.update_layout(
                height=350,
                margin=dict(l=20, r=20, t=30, b=20),
                xaxis_title="거래 번호",
                yaxis_title="손익 (원)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("아직 청산된 거래가 없습니다.")

        # 거래 로그
        st.subheader("실시간 거래 로그")
        if trade_log:
            for entry in reversed(trade_log[-15:]):
                side = entry.get("side", "")
                trade = entry.get("trade", {})
                ts = entry.get("timestamp", "")[:19]

                if side == "BUY":
                    icon = "🟢"
                    color = "green"
                else:
                    icon = "🔴"
                    color = "red"

                name = trade.get("stock_name", trade.get("name", "?"))
                pnl_text = ""
                if "realized_pnl" in trade:
                    pnl_text = f" | 손익: {trade['realized_pnl']:+,}원"

                st.markdown(
                    f"{icon} **{ts}** [{side}] "
                    f"**{name}** "
                    f"{trade.get('qty', 0)}주 @ {trade.get('entry_price', trade.get('exit_price', 0)):,}원"
                    f"{pnl_text}"
                )
        else:
            st.info("오늘 거래 기록이 없습니다.")

    # ---------- 오른쪽: 리스크 & 종목 후보 ----------
    with right_col:
        # 리스크 현황
        st.subheader("리스크 현황")
        if risk:
            remaining = risk.get("remaining_loss_budget", 0)
            max_loss = risk.get("max_daily_loss", 200000)

            if remaining > 0:
                progress = remaining / max_loss
                st.progress(progress, text=f"잔여 손실 한도: {remaining:,}원 / {max_loss:,}원")
            else:
                st.error("일일 최대 손실 한도 도달!")

            risk_col1, risk_col2 = st.columns(2)
            risk_col1.metric("연속 손실", f"{risk.get('consecutive_losses', 0)}회")
            risk_col2.metric(
                "매매 상태",
                "중단" if risk.get("daily_loss_limit_hit") else "가능"
            )
        else:
            st.info("리스크 데이터 대기 중...")

        st.divider()

        # 갭업 후보 종목
        st.subheader("갭업 스캔 종목")
        candidates = data.get("candidates", [])
        if candidates:
            for c in candidates[:10]:
                name = c.get("name", c.get("stock_name", "?"))
                change = c.get("change_pct", 0)
                color = "🔺" if change > 0 else "🔻"
                st.markdown(
                    f"{color} **{name}** ({c.get('stock_code', '?')}) "
                    f"{change:+.2f}% | 거래량: {c.get('volume', 0):,}"
                )
        else:
            st.info("스캔 대기 중...")

        st.divider()

        # AI 선정 종목
        st.subheader("AI 선정 종목")
        selected = data.get("selected_stocks", [])
        if selected:
            for s in selected[:5]:
                name = s.get("stock_name", s.get("name", "?"))
                score = s.get("score", 0)
                risk_level = s.get("final_risk", "?")
                st.markdown(
                    f"**{name}** | 점수: {score}/100 | 리스크: {risk_level}"
                )
                reason = s.get("reason", "")
                if reason:
                    st.caption(reason[:150])
        else:
            st.info("AI 종목 선정 대기 중...")

        st.divider()

        # 마지막 스캔 시간
        last_scan = data.get("last_scan_time")
        if last_scan:
            st.caption(f"마지막 스캔: {last_scan[:19]}")

    # ========== 사이드바: 설정 & 일일 리포트 ==========
    with st.sidebar:
        st.header("설정")

        st.subheader("트레이딩 파라미터")
        st.text(f"일일 투자 한도: {data.get('risk', {}).get('max_daily_capital', 0):,}원")
        st.text(f"최대 보유 종목: {data.get('risk', {}).get('max_positions', 5)}개")

        st.divider()

        st.subheader("AI 모듈 상태")
        st.markdown("""
        - **Claude Opus**: 매매 실행 판단
        - **GPT-5.2**: 종목 선정 & 리포트
        - **Gemini 3 Pro**: 교차 검증
        """)

        st.divider()

        st.subheader("일일 리포트")
        report_dir = Path("reports/daily")
        if report_dir.exists():
            reports = sorted(report_dir.glob("report_*.json"), reverse=True)
            if reports:
                selected_report = st.selectbox(
                    "리포트 선택",
                    reports,
                    format_func=lambda x: x.stem.replace("report_", ""),
                )
                if selected_report and st.button("리포트 보기"):
                    with open(selected_report, encoding="utf-8") as f:
                        report = json.load(f)
                    st.json(report)
            else:
                st.info("아직 생성된 리포트가 없습니다.")


if __name__ == "__main__":
    main()
