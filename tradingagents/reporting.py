"""Reusable report-tree writer shared by the CLI and the programmatic API.

Writes a run's per-section markdown (analysts, research, trading, risk,
portfolio) plus a consolidated ``complete_report.md`` under ``save_path``. The
CLI and ``TradingAgentsGraph.save_reports`` both call this, so a headless / API
run produces the same on-disk report tree a CLI run does.
"""

from datetime import datetime
from pathlib import Path

from tradingagents.agents.rating import run_rating

KOREAN_REPORT_LABELS = {
    "Trading Analysis Report": "종목 분석 보고서",
    "I. Analyst Team Reports": "I. 분석팀 보고서",
    "II. Research Team Decision": "II. 연구팀 판단",
    "III. Trading Team Plan": "III. 매매 계획",
    "IV. Risk Management Team Decision": "IV. 위험관리팀 판단",
    "V. Portfolio Manager Decision": "V. 포트폴리오 관리자 최종 판단",
    "Market Analyst": "시장·기술 분석가",
    "Sentiment Analyst": "시장심리 분석가",
    "News Analyst": "뉴스 분석가",
    "Fundamentals Analyst": "재무·기업가치 분석가",
    "Bull Researcher": "상승론 연구원",
    "Bear Researcher": "하락론 연구원",
    "Research Manager": "연구 관리자",
    "Trader": "트레이더",
    "Aggressive Analyst": "공격적 위험 분석가",
    "Conservative Analyst": "보수적 위험 분석가",
    "Neutral Analyst": "중립적 위험 분석가",
    "Portfolio Manager": "포트폴리오 관리자",
}


def analyst_names(keys) -> list[str]:
    """The analysts as users select them: the sentiment analyst's key is "social"."""
    return ["sentiment" if key == "social" else key for key in keys or []]


def _header(ticker: str, final_state: dict, settings: dict | None) -> str:
    """The report's title and what produced it: analysis date, version, models, analysts, vendors."""
    lines = [f"# Trading Analysis Report: {ticker}", ""]
    if final_state.get("trade_date"):
        lines.append(f"- Analysis date: {final_state['trade_date']}")
    if final_state.get("final_trade_decision"):
        lines.append(f"- Rating: {run_rating(final_state)}")
    lines.append(f"- Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}")
    if settings:
        s = settings.get
        deep_provider = s("deep_think_provider") or s("llm_provider", "?")
        quick_provider = s("quick_think_provider") or s("llm_provider", "?")
        if deep_provider == quick_provider:
            models = f"{deep_provider}, deep {s('deep_think_llm', '?')}, quick {s('quick_think_llm', '?')}"
        else:   # each tier on its own provider (#1440)
            models = (f"deep {deep_provider} {s('deep_think_llm', '?')}, "
                      f"quick {quick_provider} {s('quick_think_llm', '?')}")
        lines.append(f"- TradingAgents {s('version', '?')}: {models}")
        lines.append(f"- Analysts: {', '.join(analyst_names(s('analysts')))}; "
                     f"research debate rounds {s('max_debate_rounds', '?')}, "
                     f"risk debate rounds {s('max_risk_discuss_rounds', '?')}")
        vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
        if vendors:
            lines.append("- Data vendors: " + ", ".join(f"{k} {v}" for k, v in vendors.items()))
    if final_state.get("memory_note"):
        lines.append(f"- Memory log: {final_state['memory_note']}")
    return "\n".join(lines) + "\n\n"


# The report's sections in order: (heading, folder, [(agent, file, state path)]).
_SECTIONS = (
    ("I. Analyst Team Reports", "1_analysts", (
        ("Market Analyst", "market.md", ("market_report",)),
        ("Sentiment Analyst", "sentiment.md", ("sentiment_report",)),
        ("News Analyst", "news.md", ("news_report",)),
        ("Fundamentals Analyst", "fundamentals.md", ("fundamentals_report",)),
    )),
    ("II. Research Team Decision", "2_research", (
        ("Bull Researcher", "bull.md", ("investment_debate_state", "bull_history")),
        ("Bear Researcher", "bear.md", ("investment_debate_state", "bear_history")),
        ("Research Manager", "manager.md", ("investment_plan",)),
    )),
    ("III. Trading Team Plan", "3_trading", (
        ("Trader", "trader.md", ("trader_investment_plan",)),
    )),
    ("IV. Risk Management Team Decision", "4_risk", (
        ("Aggressive Analyst", "aggressive.md", ("risk_debate_state", "aggressive_history")),
        ("Conservative Analyst", "conservative.md", ("risk_debate_state", "conservative_history")),
        ("Neutral Analyst", "neutral.md", ("risk_debate_state", "neutral_history")),
    )),
    ("V. Portfolio Manager Decision", "5_portfolio", (
        ("Portfolio Manager", "decision.md", ("final_trade_decision",)),
    )),
)


def _report_parts(final_state: dict) -> list[tuple[str, str, list[tuple[str, str, str]]]]:
    """The sections with something to say: (heading, folder, [(agent, file, text)])."""
    parts = []
    for heading, folder, agents in _SECTIONS:
        written = []
        for agent, filename, path in agents:
            value = final_state
            for key in path:
                value = (value or {}).get(key)
            if value:
                written.append((agent, filename, value))
        if written:
            parts.append((heading, folder, written))
    return parts


def write_report_tree(final_state: dict, ticker: str, save_path, settings: dict | None = None,
                      html: bool = True, *, output_language=None) -> Path:
    """Save a completed run's reports to ``save_path``; return the complete-report path.

    ``settings`` (``TradingAgentsGraph.run_settings()``) adds what produced the run
    to the report's header. ``html`` also writes ``complete_report.html``, one
    self-contained page of the same report (#1419).
    """
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)
    language = output_language or (settings or {}).get("output_language", "English")
    korean = str(language).lower() in {"korean", "ko", "한국어"}
    def label(text):
        return f"{text} ({KOREAN_REPORT_LABELS[text]})" if korean else text
    parts = [(label(h), folder, [(label(a), f, t) for a, f, t in written])
             for h, folder, written in _report_parts(final_state)]
    sections = []
    for heading, folder, written in parts:
        (save_path / folder).mkdir(exist_ok=True)
        for _agent, filename, text in written:
            (save_path / folder / filename).write_text(text, encoding="utf-8")
        content = "\n\n".join(f"### {agent}\n{text}" for agent, _filename, text in written)
        sections.append(f"## {heading}\n\n{content}")

    header = _header(ticker, final_state, settings)
    if korean:
        header = header.replace("# Trading Analysis Report:", "# " + label("Trading Analysis Report") + ":", 1)
        header += (
            "> 생성 시각은 파일 작성 시각이며, 분석 기준일·가격 관측일과 다를 수 있습니다.\n"
            "> 역할별 자료 범위: 시장 분석은 가격·기술지표, 재무 분석은 기업정보·재무제표, "
            "뉴스 분석은 기사·공시·거시자료, 심리 분석은 확보된 뉴스·소셜 자료를 다룹니다. "
            "각 절의 자료 누락 설명은 그 역할의 범위이며 전체 수집 실패를 뜻하지 않습니다. "
            "실제 사용 여부와 제약은 각 절의 근거를 확인하세요.\n\n"
        )
    (save_path / "complete_report.md").write_text(
        header + "\n\n".join(sections), encoding="utf-8"
    )
    if html:
        from tradingagents.report_html import render_report

        (save_path / "complete_report.html").write_text(
            render_report(ticker, final_state, settings, parts, output_language=language), encoding="utf-8"
        )
    return save_path / "complete_report.md"
