# =========================
# CONFIG GENERAL
# =========================

st.set_page_config(
    page_title="BTCUSDT Futures Dashboard Pro",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
div[data-testid="stMetricValue"] {font-size: 1.0rem !important; font-weight: 600 !important;}
div[data-testid="stMetricLabel"] {font-size: 0.75rem !important;}
div[data-testid="stMetricDelta"] {font-size: 0.70rem !important;}
.block-container {padding-top: 2rem;}
@media (max-width: 768px) {
    div[data-testid="stMetricValue"] {font-size: 0.95rem !important;}
    div[data-testid="stMetricLabel"] {font-size: 0.70rem !important;}
    h1 {font-size: 1.55rem !important;}
    h2 {font-size: 1.20rem !important;}
}
</style>
""", unsafe_allow_html=True)

OPEN_TRADE_FILE = "open_trade.csv"
CLOSED_TRADES_FILE ="closed_trades.csv"
SIGNALS_FILE = "signals_log.csv"
AUTO_SIGNALS_FILE = "auto_signals_log.csv"
ALERTS_FILE = "alerts_sent_log.csv"
MARKET_STATE_FILE = "market_state.csv"
USERS_FILE = "users.csv"
SYMBOL = "BTC/USDT:USDT"
LIMIT = 300
BACKTEST_LIMIT = 1500
ACCESS_KEY = "1234"

STRATEGIES = [
    "Tendencia + Liquidez",
    "Pullback EMA50",
    "Sweep de Liquidez",
    "Ruptura de Estructura",
    "Reversión Extrema",
    "FVG + Tendencia",
]

