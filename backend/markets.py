"""Market presets: each is a scan universe plus a benchmark used for relative strength.
Any Yahoo symbol worldwide can also be analysed directly through search, even if it is not in a preset."""

PRESETS = {
    "us": {"name": "US Large Caps", "flag": "🇺🇸", "benchmark": "^GSPC", "currency": "USD", "shortable": True, "symbols": [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "BRK-B", "JPM", "V", "MA", "LLY", "UNH", "XOM", "JNJ",
        "WMT", "PG", "HD", "COST", "ORCL", "NFLX", "CRM", "AMD", "ADBE", "KO", "PEP", "MRK", "ABBV", "BAC", "CVX", "TMO",
        "MCD", "CSCO", "ACN", "LIN", "INTU", "QCOM", "TXN", "AMAT", "IBM", "GE", "CAT", "DIS", "NKE", "GS", "MS", "UBER",
        "PLTR", "NOW", "ISRG", "BKNG", "SBUX", "PFE", "T", "VZ", "BA", "INTC", "MU", "PANW", "SHOP", "COIN"]},
    "india": {"name": "India NSE (Nifty 50)", "flag": "🇮🇳", "benchmark": "^NSEI", "currency": "INR", "shortable": False, "symbols": [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "BHARTIARTL.NS", "ITC.NS", "SBIN.NS", "LT.NS",
        "HINDUNILVR.NS", "BAJFINANCE.NS", "KOTAKBANK.NS", "AXISBANK.NS", "HCLTECH.NS", "MARUTI.NS", "SUNPHARMA.NS", "M&M.NS",
        "TITAN.NS", "ULTRACEMCO.NS", "ASIANPAINT.NS", "NTPC.NS", "TATAMOTORS.NS", "POWERGRID.NS", "WIPRO.NS", "ONGC.NS",
        "NESTLEIND.NS", "JSWSTEEL.NS", "TATASTEEL.NS", "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS", "BAJAJFINSV.NS",
        "TECHM.NS", "GRASIM.NS", "HINDALCO.NS", "DRREDDY.NS", "CIPLA.NS", "EICHERMOT.NS", "BRITANNIA.NS", "HEROMOTOCO.NS",
        "APOLLOHOSP.NS", "INDUSINDBK.NS", "TRENT.NS", "BEL.NS", "SHRIRAMFIN.NS", "ZOMATO.NS"]},
    "uk": {"name": "UK FTSE", "flag": "🇬🇧", "benchmark": "^FTSE", "currency": "GBP", "shortable": True, "symbols": [
        "SHEL.L", "AZN.L", "HSBA.L", "ULVR.L", "BP.L", "RIO.L", "GSK.L", "REL.L", "DGE.L", "BATS.L", "LSEG.L", "GLEN.L",
        "BARC.L", "LLOY.L", "NWG.L", "RR.L", "VOD.L", "TSCO.L", "BA.L", "AAL.L", "NG.L", "PRU.L", "EXPN.L", "CPG.L"]},
    "europe": {"name": "Europe (Euro Stoxx)", "flag": "🇪🇺", "benchmark": "^STOXX50E", "currency": "EUR", "shortable": True, "symbols": [
        "ASML.AS", "SAP.DE", "MC.PA", "SIE.DE", "TTE.PA", "OR.PA", "SAN.PA", "ALV.DE", "AIR.PA", "RMS.PA", "SU.PA", "DTE.DE",
        "BNP.PA", "IBE.MC", "SAN.MC", "ENEL.MI", "ISP.MI", "MBG.DE", "BMW.DE", "BAS.DE", "ADS.DE", "INGA.AS", "NOVO-B.CO", "NESN.SW",
        "ROG.SW", "NOVN.SW", "UBSG.SW", "RACE.MI", "IFX.DE", "PRX.AS"]},
    "japan": {"name": "Japan (Nikkei)", "flag": "🇯🇵", "benchmark": "^N225", "currency": "JPY", "shortable": True, "symbols": [
        "7203.T", "6758.T", "8306.T", "6861.T", "9984.T", "8035.T", "9432.T", "6501.T", "4063.T", "7974.T", "9983.T", "8058.T",
        "6098.T", "4502.T", "7267.T", "6902.T", "8316.T", "6367.T", "7741.T", "4568.T"]},
    "hongkong": {"name": "Hong Kong / China", "flag": "🇭🇰", "benchmark": "^HSI", "currency": "HKD", "shortable": True, "symbols": [
        "0700.HK", "9988.HK", "3690.HK", "1299.HK", "0005.HK", "0941.HK", "1810.HK", "9618.HK", "2318.HK", "0388.HK", "1211.HK",
        "9999.HK", "0883.HK", "2020.HK", "0939.HK", "1398.HK"]},
    "canada": {"name": "Canada (TSX)", "flag": "🇨🇦", "benchmark": "^GSPTSE", "currency": "CAD", "shortable": True, "symbols": [
        "RY.TO", "TD.TO", "SHOP.TO", "ENB.TO", "CNR.TO", "CP.TO", "BN.TO", "BMO.TO", "BNS.TO", "CNQ.TO", "SU.TO", "ATD.TO",
        "TRI.TO", "CSU.TO", "MFC.TO", "NTR.TO"]},
    "australia": {"name": "Australia (ASX)", "flag": "🇦🇺", "benchmark": "^AXJO", "currency": "AUD", "shortable": True, "symbols": [
        "BHP.AX", "CBA.AX", "CSL.AX", "NAB.AX", "WBC.AX", "ANZ.AX", "WES.AX", "MQG.AX", "FMG.AX", "WDS.AX", "RIO.AX", "TLS.AX",
        "WOW.AX", "GMG.AX", "TCL.AX", "XRO.AX"]},
    "crypto": {"name": "Crypto", "flag": "₿", "benchmark": "BTC-USD", "currency": "USD", "shortable": True, "fractional": True, "symbols": [
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "DOT-USD",
        "LTC-USD", "TRX-USD", "BCH-USD", "XLM-USD", "NEAR-USD", "UNI7083-USD", "ATOM-USD", "SUI20947-USD"]},
    "forex": {"name": "Forex", "flag": "💱", "benchmark": None, "currency": "USD", "shortable": True, "fractional": True, "symbols": [
        "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X", "EURGBP=X", "EURJPY=X", "USDINR=X",
        "USDCNY=X", "USDMXN=X"]},
    "commodities": {"name": "Commodities (Futures)", "flag": "🛢️", "benchmark": None, "currency": "USD", "shortable": True, "fractional": True, "symbols": [
        "GC=F", "SI=F", "CL=F", "BZ=F", "NG=F", "HG=F", "PL=F", "ZC=F", "ZW=F", "ZS=F", "KC=F", "SB=F", "CC=F", "LE=F"]},
    "etfs": {"name": "Global ETFs", "flag": "📊", "benchmark": "^GSPC", "currency": "USD", "shortable": True, "symbols": [
        "SPY", "QQQ", "IWM", "DIA", "VTI", "EFA", "EEM", "VWO", "INDA", "EWJ", "FXI", "TLT", "IEF", "HYG", "GLD", "SLV", "USO",
        "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLRE", "SMH", "ARKK", "BITO", "VNQ"]},
}

MACRO = [
    ("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^DJI", "Dow"), ("^RUT", "Russell 2k"), ("^VIX", "VIX"), ("^TNX", "US 10Y"),
    ("DX-Y.NYB", "Dollar"), ("GC=F", "Gold"), ("CL=F", "Crude"), ("BTC-USD", "Bitcoin"), ("^NSEI", "Nifty 50"),
    ("^FTSE", "FTSE 100"), ("^GDAXI", "DAX"), ("^N225", "Nikkei"), ("^HSI", "Hang Seng"), ("EURUSD=X", "EUR/USD"),
]


def all_markets() -> list[dict]:
    from . import custom, simulator
    out = [{"id": k, "name": v["name"], "flag": v["flag"], "count": len(v["symbols"]), "kind": "real", "currency": v["currency"]}
           for k, v in PRESETS.items()]
    out.append({"id": "sim", "name": simulator.MARKET_NAME, "flag": "🐺", "count": len(simulator.COMPANIES), "kind": "sim", "currency": "USD"})
    for m in custom.list_markets():
        out.append({"id": m["id"], "name": m["name"], "flag": "🧪", "count": len(m["tickers"]), "kind": "custom", "currency": m.get("currency", "USD")})
    return out


def market_def(market_id: str) -> dict:
    from . import custom, simulator
    if market_id in PRESETS:
        return PRESETS[market_id]
    if market_id == "sim":
        return simulator.market_def()
    m = custom.get_market(market_id)
    if m:
        return {"name": m["name"], "benchmark": None, "currency": m.get("currency", "USD"), "shortable": True,
                "fractional": False, "symbols": [f"CUS:{market_id}:{s}" for s in m["tickers"]]}
    raise KeyError(market_id)
