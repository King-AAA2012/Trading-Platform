"""Markets: curated asset-class presets plus every country's stock market (largest companies by market cap, pulled
live from the Yahoo screener). Any Yahoo symbol worldwide can also be analysed directly through search."""

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

PRESETS.update({
    "indices": {"name": "World Stock Indices", "flag": "🌍", "benchmark": None, "currency": "USD", "shortable": True, "fractional": True, "group": "Asset classes", "symbols": [
        "^GSPC", "^IXIC", "^DJI", "^RUT", "^GSPTSE", "^BVSP", "^MXX", "^MERV", "^FTSE", "^GDAXI", "^FCHI", "^STOXX50E", "^IBEX", "FTSEMIB.MI",
        "^AEX", "^SSMI", "^OMX", "^N225", "^HSI", "000001.SS", "^KS11", "^TWII", "^NSEI", "^BSESN", "^AXJO", "^NZ50", "^STI", "^JKSE", "^KLSE",
        "^SET.BK", "XU100.IS", "TA35.TA", "^TASI.SR", "^J203.JO", "^CASE30"]},
    "bonds": {"name": "Bonds & Rates (ETFs)", "flag": "🏦", "benchmark": "AGG", "currency": "USD", "shortable": True, "group": "Asset classes", "symbols": [
        "AGG", "BND", "TLT", "IEF", "SHY", "TIP", "LQD", "HYG", "JNK", "EMB", "BNDX", "MUB", "VCIT", "VGSH", "GOVT", "IGOV", "BWX", "SGOV", "MBB", "FLOT"]},
})
for k in PRESETS:
    PRESETS[k].setdefault("group", "Asset classes" if k in ("crypto", "forex", "commodities", "etfs") else "Curated stock markets")

# Every country Yahoo covers: (name, flag, benchmark index, shortable, continent group)
REGIONS = {
    "us": ("United States · top 100", "🇺🇸", "^GSPC", True, "Americas"), "ca": ("Canada", "🇨🇦", "^GSPTSE", True, "Americas"),
    "br": ("Brazil", "🇧🇷", "^BVSP", True, "Americas"), "mx": ("Mexico", "🇲🇽", "^MXX", True, "Americas"),
    "ar": ("Argentina", "🇦🇷", "^MERV", False, "Americas"), "cl": ("Chile", "🇨🇱", "^IPSA", False, "Americas"),
    "gb": ("United Kingdom", "🇬🇧", "^FTSE", True, "Europe"), "de": ("Germany", "🇩🇪", "^GDAXI", True, "Europe"),
    "fr": ("France", "🇫🇷", "^FCHI", True, "Europe"), "ch": ("Switzerland", "🇨🇭", "^SSMI", True, "Europe"),
    "nl": ("Netherlands", "🇳🇱", "^AEX", True, "Europe"), "es": ("Spain", "🇪🇸", "^IBEX", True, "Europe"),
    "it": ("Italy", "🇮🇹", "FTSEMIB.MI", True, "Europe"), "se": ("Sweden", "🇸🇪", "^OMX", True, "Europe"),
    "no": ("Norway", "🇳🇴", None, True, "Europe"), "dk": ("Denmark", "🇩🇰", None, True, "Europe"),
    "fi": ("Finland", "🇫🇮", None, True, "Europe"), "be": ("Belgium", "🇧🇪", "^BFX", True, "Europe"),
    "at": ("Austria", "🇦🇹", "^ATX", True, "Europe"), "ie": ("Ireland", "🇮🇪", None, True, "Europe"),
    "pt": ("Portugal", "🇵🇹", None, True, "Europe"), "pl": ("Poland", "🇵🇱", None, False, "Europe"),
    "gr": ("Greece", "🇬🇷", None, False, "Europe"), "cz": ("Czechia", "🇨🇿", None, False, "Europe"),
    "hu": ("Hungary", "🇭🇺", None, False, "Europe"), "tr": ("Turkey", "🇹🇷", "XU100.IS", False, "Europe"),
    "is": ("Iceland", "🇮🇸", None, False, "Europe"), "ee": ("Estonia", "🇪🇪", None, False, "Europe"),
    "jp": ("Japan", "🇯🇵", "^N225", True, "Asia-Pacific"), "cn": ("China (Shanghai/Shenzhen)", "🇨🇳", "000001.SS", False, "Asia-Pacific"),
    "hk": ("Hong Kong", "🇭🇰", "^HSI", True, "Asia-Pacific"), "in": ("India", "🇮🇳", "^NSEI", False, "Asia-Pacific"),
    "kr": ("South Korea", "🇰🇷", "^KS11", False, "Asia-Pacific"), "tw": ("Taiwan", "🇹🇼", "^TWII", False, "Asia-Pacific"),
    "au": ("Australia", "🇦🇺", "^AXJO", True, "Asia-Pacific"), "nz": ("New Zealand", "🇳🇿", "^NZ50", True, "Asia-Pacific"),
    "sg": ("Singapore", "🇸🇬", "^STI", True, "Asia-Pacific"), "my": ("Malaysia", "🇲🇾", "^KLSE", False, "Asia-Pacific"),
    "id": ("Indonesia", "🇮🇩", "^JKSE", False, "Asia-Pacific"), "th": ("Thailand", "🇹🇭", "^SET.BK", False, "Asia-Pacific"),
    
    "il": ("Israel", "🇮🇱", "TA35.TA", True, "Middle East & Africa"), "sa": ("Saudi Arabia", "🇸🇦", "^TASI.SR", False, "Middle East & Africa"),
    "qa": ("Qatar", "🇶🇦", None, False, "Middle East & Africa"),
    "za": ("South Africa", "🇿🇦", "^J203.JO", True, "Middle East & Africa"),
}

MACRO = [
    ("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^DJI", "Dow"), ("^RUT", "Russell 2k"), ("^VIX", "VIX"), ("^TNX", "US 10Y"),
    ("DX-Y.NYB", "Dollar"), ("GC=F", "Gold"), ("CL=F", "Crude"), ("BTC-USD", "Bitcoin"), ("^NSEI", "Nifty 50"),
    ("^FTSE", "FTSE 100"), ("^GDAXI", "DAX"), ("^N225", "Nikkei"), ("^HSI", "Hang Seng"), ("EURUSD=X", "EUR/USD"),
]
# home-exchange suffixes ("" = no suffix, i.e. US listings) and extra reporting currencies allowed for real domestic firms
SUFFIX = {"us": ("",), "ca": (".TO", ".V"), "br": (".SA",), "mx": (".MX",), "ar": (".BA",), "cl": (".SN",), "co": (".CL",), "pe": (".LM",),
          "gb": (".L",), "de": (".DE",), "fr": (".PA",), "ch": (".SW",), "nl": (".AS",), "es": (".MC",), "it": (".MI",), "se": (".ST",),
          "no": (".OL",), "dk": (".CO",), "fi": (".HE",), "be": (".BR",), "at": (".VI",), "ie": (".IR",), "pt": (".LS",), "pl": (".WA",),
          "gr": (".AT",), "cz": (".PR",), "hu": (".BD",), "tr": (".IS",), "is": (".IC",), "ee": (".TL",), "jp": (".T",), "cn": (".SS", ".SZ"),
          "hk": (".HK",), "in": (".NS",), "kr": (".KS", ".KQ"), "tw": (".TW", ".TWO"), "au": (".AX",), "nz": (".NZ",), "sg": (".SI",),
          "my": (".KL",), "id": (".JK",), "th": (".BK",), "ph": (".PS",), "vn": (".VN",), "pk": (".KA",), "lk": (".CM",), "il": (".TA",),
          "sa": (".SR",), "qa": (".QA",), "kw": (".KW",), "eg": (".CA",), "za": (".JO",)}
HOME_CCY = {"ar": "ARS"}
# exchanges where cross-listings can't be filtered reliably: use the official index members instead
CURATED = {
    "de": [x + ".DE" for x in "ADS AIR ALV BAS BAYN BEI BMW BNR CBK CON DB1 DBK DHL DTE DTG ENR EOAN FRE FME G1A HEI HEN3 HNR1 IFX MBG MRK MTX MUV2 P911 PAH3 QIA RHM RWE SAP SHL SIE SRT3 SY1 VNA VOW3 ZAL".split()],
    "at": [x + ".VI" for x in "ANDR BG CAI DOC EBS EVN IIA LNZ OMV POST RBI SBO STR TKA UQA VER VIG VOE WIE ATS".split()],
}
FIN_CCY = {"gb": ("GBP", "USD", "EUR"), "hk": ("HKD", "CNY", "USD"), "nl": ("EUR", "USD"), "no": ("NOK", "USD", "EUR"), "il": ("ILS", "USD"),
           "ch": ("CHF", "USD", "EUR"), "sg": ("SGD", "USD"), "dk": ("DKK", "EUR", "USD"), "se": ("SEK", "EUR", "USD"), "ie": ("EUR", "USD"),
           "za": ("ZAR", "USD"), "au": ("AUD", "USD"), "ca": ("CAD", "USD"), "us": ()}


def all_markets() -> list[dict]:
    out = [{"id": k, "name": v["name"], "flag": v["flag"], "count": len(v["symbols"]), "group": v["group"], "currency": v["currency"]}
           for k, v in PRESETS.items()]
    for code, (name, flag, _, _, grp) in REGIONS.items():
        out.append({"id": f"r-{code}", "name": name, "flag": flag, "count": 100 if code == "us" else 60, "group": grp, "currency": ""})
    return out


def market_def(market_id: str) -> dict:
    if market_id in PRESETS:
        return PRESETS[market_id]
    if market_id.startswith("r-") and market_id[2:] in REGIONS:
        code = market_id[2:]
        name, flag, bench, shortable, grp = REGIONS[code]
        from . import data
        if code in CURATED:
            return {"name": name, "flag": flag, "benchmark": bench, "currency": "EUR", "shortable": shortable, "group": grp,
                    "symbols": CURATED[code], "equalWeightBench": bench is None}
        rows = data.screener(code, 100 if code == "us" else 60, SUFFIX.get(code, ()), FIN_CCY.get(code, ("__local__",)), HOME_CCY.get(code))
        return {"name": name, "flag": flag, "benchmark": bench, "currency": (rows[0]["currency"] if rows else ""), "shortable": shortable,
                "group": grp, "symbols": [r["symbol"] for r in rows], "equalWeightBench": bench is None}
    raise KeyError(market_id)
