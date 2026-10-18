"""Supply-chain explorer: who a company buys from, who it sells to, and the wider industry chain.

Three layers, each labelled in the UI:
  1. VERIFIED links: a curated list of well-documented supplier -> customer relationships between listed companies,
     taken from public filings and widely reported deals (as of 2025). Relationships change; treat as a starting point.
  2. INDUSTRY value chain: which industries feed into a company's industry and which industries it sells to, filled
     with real companies from the app's market data. Works for any stock.
  3. AI suggestions (opt-in): the local model proposes extra suppliers/customers; names are resolved to tickers and
     shown as UNVERIFIED.
Importance: 3 = critical / sole-source or major share, 2 = significant, 1 = one of several.
"""
from __future__ import annotations

import json

from . import data

# (supplier, customer, what is supplied, importance)
LINKS: list[tuple[str, str, str, int]] = [
    # ---- semiconductor equipment & materials -> chipmakers
    ("ASML", "TSM", "EUV & DUV lithography systems", 3), ("ASML", "005930.KS", "Lithography systems", 3), ("ASML", "INTC", "Lithography systems", 3),
    ("ASML", "000660.KS", "Lithography systems", 2), ("ASML", "MU", "Lithography systems", 2),
    ("AMAT", "TSM", "Deposition, etch & inspection tools", 3), ("AMAT", "005930.KS", "Wafer-fab equipment", 2), ("AMAT", "INTC", "Wafer-fab equipment", 2), ("AMAT", "MU", "Wafer-fab equipment", 2),
    ("LRCX", "TSM", "Etch & deposition tools", 3), ("LRCX", "005930.KS", "Etch tools for memory", 3), ("LRCX", "MU", "Etch tools for memory", 2), ("LRCX", "000660.KS", "Etch tools for memory", 2),
    ("KLAC", "TSM", "Process control & inspection", 3), ("KLAC", "005930.KS", "Process control", 2), ("KLAC", "INTC", "Process control", 2),
    ("8035.T", "TSM", "Coater/developer, etch & deposition tools", 3), ("8035.T", "005930.KS", "Wafer-fab equipment", 2), ("8035.T", "MU", "Wafer-fab equipment", 1),
    ("6857.T", "TSM", "Semiconductor test systems", 2), ("6857.T", "NVDA", "Test systems for AI GPUs", 2),
    ("4063.T", "TSM", "Silicon wafers & photoresists", 3), ("4063.T", "005930.KS", "Silicon wafers", 2), ("3436.T", "TSM", "Silicon wafers", 2),
    ("ENTG", "TSM", "Filtration & specialty materials", 2), ("LIN", "TSM", "Industrial & specialty gases", 2), ("6146.T", "TSM", "Dicing & grinding equipment", 1),
    # ---- foundry -> chip designers
    ("TSM", "AAPL", "A-series & M-series chip fabrication", 3), ("TSM", "NVDA", "GPU fabrication & CoWoS packaging", 3), ("TSM", "AMD", "CPU & GPU fabrication", 3),
    ("TSM", "QCOM", "Snapdragon fabrication", 3), ("TSM", "AVGO", "Custom ASIC & networking chip fabrication", 3), ("TSM", "2454.TW", "Dimensity chip fabrication", 3),
    ("TSM", "MRVL", "Chip fabrication", 2), ("TSM", "INTC", "Outsourced chip tiles (Lunar Lake / Arrow Lake)", 2), ("TSM", "AMZN", "Graviton & Trainium chips", 2),
    ("TSM", "TSLA", "AI chip fabrication", 1), ("005930.KS", "TSLA", "Foundry for next-gen AI / FSD chips", 2),
    # ---- memory, packaging & server assembly -> AI chips
    ("000660.KS", "NVDA", "HBM high-bandwidth memory", 3), ("MU", "NVDA", "HBM3E memory", 2), ("005930.KS", "NVDA", "GDDR & HBM memory", 2),
    ("2317.TW", "NVDA", "AI server & rack assembly", 3), ("2382.TW", "NVDA", "AI server assembly", 2), ("3231.TW", "NVDA", "GPU baseboards & servers", 2),
    ("3711.TW", "NVDA", "Chip packaging & test", 1), ("AMKR", "NVDA", "Advanced packaging", 1), ("AMKR", "AAPL", "Chip packaging & test", 2),
    # ---- AI chips -> cloud & server makers
    ("NVDA", "MSFT", "AI GPUs & systems for Azure", 3), ("NVDA", "AMZN", "AI GPUs for AWS", 3), ("NVDA", "GOOGL", "AI GPUs for Google Cloud", 3),
    ("NVDA", "META", "AI GPUs for training clusters", 3), ("NVDA", "ORCL", "AI GPUs for Oracle Cloud", 3), ("NVDA", "TSLA", "AI training GPUs", 2),
    ("NVDA", "DELL", "GPUs for AI servers", 2), ("NVDA", "SMCI", "GPUs for AI servers", 3), ("NVDA", "HPE", "GPUs for AI servers", 2), ("NVDA", "CRWV", "GPUs for AI cloud", 3),
    ("AMD", "MSFT", "Xbox chips & Instinct GPUs for Azure", 2), ("AMD", "6758.T", "PlayStation 5 processors", 3), ("AMD", "META", "EPYC CPUs & Instinct GPUs", 2),
    ("AMD", "ORCL", "Instinct GPUs", 1), ("AMD", "DELL", "CPUs for PCs & servers", 2), ("AMD", "HPQ", "CPUs for PCs", 2), ("AMD", "0992.HK", "CPUs for PCs", 2), ("AMD", "SMCI", "CPUs & GPUs for servers", 1),
    ("INTC", "DELL", "PC & server CPUs", 3), ("INTC", "HPQ", "PC CPUs", 3), ("INTC", "0992.HK", "PC CPUs", 3),
    ("MU", "DELL", "Memory & SSDs", 1), ("AVGO", "GOOGL", "Custom TPU accelerators", 3), ("AVGO", "META", "Custom AI accelerators", 2),
    # ---- smartphone chain
    ("QCOM", "AAPL", "5G modems (being phased out)", 2), ("QCOM", "005930.KS", "Snapdragon chips for Galaxy phones", 3), ("QCOM", "1810.HK", "Snapdragon chips", 2),
    ("AVGO", "AAPL", "RF & wireless chips", 2), ("SWKS", "AAPL", "RF front-end modules", 3), ("QRVO", "AAPL", "RF chips", 2), ("CRUS", "AAPL", "Audio & mixed-signal chips", 3),
    ("TXN", "AAPL", "Analog & power chips", 1), ("GLW", "AAPL", "Ceramic Shield cover glass", 2), ("6758.T", "AAPL", "iPhone camera image sensors", 3),
    ("005930.KS", "AAPL", "OLED displays & memory", 3), ("034220.KS", "AAPL", "OLED & LCD displays", 2), ("000660.KS", "AAPL", "DRAM & NAND memory", 1), ("MU", "AAPL", "DRAM & NAND memory", 1),
    ("2317.TW", "AAPL", "iPhone & device assembly (Foxconn)", 3), ("4938.TW", "AAPL", "iPhone assembly", 1), ("002475.SZ", "AAPL", "AirPods, Watch & iPhone assembly", 2),
    ("6981.T", "AAPL", "Capacitors & RF modules", 1), ("JBL", "AAPL", "Enclosures & components", 1), ("6762.T", "AAPL", "Battery cells", 1),
    ("AAPL", "VZ", "iPhones for carrier sales", 2), ("AAPL", "T", "iPhones for carrier sales", 2), ("AAPL", "TMUS", "iPhones for carrier sales", 2), ("AAPL", "BBY", "Retail distribution", 1),
    ("AAPL", "GOOGL", "Safari default-search distribution (Google pays Apple)", 2),
    # ---- telecom equipment -> carriers
    ("ERIC", "T", "5G radio access network", 3), ("ERIC", "VZ", "5G radio equipment", 2), ("NOK", "VZ", "Network equipment", 1), ("NOK", "T", "Network equipment", 1),
    ("005930.KS", "VZ", "5G network equipment", 2), ("ERIC", "RELIANCE.NS", "5G network equipment (Jio)", 2), ("NOK", "RELIANCE.NS", "5G network equipment (Jio)", 2),
    ("ERIC", "BHARTIARTL.NS", "5G radio network", 2), ("NOK", "BHARTIARTL.NS", "5G radio network", 2), ("005930.KS", "BHARTIARTL.NS", "5G network equipment", 1),
    # ---- cloud
    ("AMZN", "NFLX", "AWS cloud hosting", 2), ("AMZN", "SNOW", "AWS cloud infrastructure", 2), ("MSFT", "SNOW", "Azure cloud infrastructure", 1), ("GOOGL", "SNOW", "Google Cloud infrastructure", 1),
    ("UPS", "AMZN", "Parcel delivery", 2),
    # ---- EV & batteries
    ("6752.T", "TSLA", "Battery cells", 3), ("300750.SZ", "TSLA", "LFP battery cells", 3), ("373220.KS", "TSLA", "Battery cells", 2),
    ("1772.HK", "TSLA", "Lithium hydroxide", 2), ("GLEN.L", "TSLA", "Cobalt", 1), ("ALB", "F", "Battery-grade lithium hydroxide", 2),
    ("300750.SZ", "BMW.DE", "Battery cells", 2), ("300750.SZ", "MBG.DE", "Battery cells", 2), ("300750.SZ", "VOW3.DE", "Battery cells", 2), ("300750.SZ", "F", "LFP battery technology licence", 1),
    ("373220.KS", "GM", "Battery cells (Ultium Cells JV)", 3),
    # ---- autos
    ("6902.T", "7203.T", "Powertrain, electronics & thermal systems", 3), ("7259.T", "7203.T", "Transmissions & drivetrain", 3), ("6201.T", "7203.T", "Engines & components", 2),
    ("6752.T", "7203.T", "Batteries (Prime Planet Energy JV)", 2), ("5108.T", "7203.T", "Tyres", 1),
    ("MGA", "GM", "Body, chassis & seating", 2), ("APTV", "GM", "Electrical architecture", 2), ("LEA", "GM", "Seats & electrical systems", 2), ("LEA", "F", "Seats", 2), ("BWA", "F", "Propulsion components", 1),
    ("7269.T", "MARUTI.NS", "Parent: technology, platforms & licensing", 3), ("MOTHERSON.NS", "MARUTI.NS", "Wiring harnesses & mirrors", 2), ("BOSCHLTD.NS", "MARUTI.NS", "Fuel-injection & electronics", 1),
    # ---- aerospace -> airlines
    ("GE", "BA", "CFM LEAP & GE9X engines", 3), ("SAF.PA", "BA", "CFM LEAP engines (with GE) & landing gear", 2), ("RTX", "BA", "Collins avionics & Pratt & Whitney engines", 2),
    ("SPR", "BA", "737 fuselages & aerostructures", 3), ("HXL", "BA", "Carbon-fibre composites", 2), ("HON", "BA", "Avionics & auxiliary power units", 1),
    ("GE", "AIR.PA", "CFM LEAP engines (A320neo)", 3), ("SAF.PA", "AIR.PA", "CFM LEAP engines, nacelles & landing gear", 3), ("RR.L", "AIR.PA", "Trent engines (A330neo, A350)", 3),
    ("RTX", "AIR.PA", "Pratt & Whitney GTF engines (A320neo)", 2), ("HXL", "AIR.PA", "Carbon-fibre composites", 2), ("SPR", "AIR.PA", "Wing & fuselage components", 1),
    ("BA", "UAL", "737 MAX & 787 aircraft", 3), ("BA", "AAL", "737 MAX & 787 aircraft", 2), ("BA", "LUV", "737 MAX (all-Boeing fleet)", 3), ("BA", "RYA.IR", "737 MAX aircraft", 3), ("BA", "DAL", "737 & 767 aircraft", 1),
    ("AIR.PA", "DAL", "A220, A321neo & A350 aircraft", 2), ("AIR.PA", "LHA.DE", "Airbus fleet", 2), ("AIR.PA", "AF.PA", "Airbus fleet", 2), ("AIR.PA", "INDIGO.NS", "A320neo-family aircraft", 3),
    ("RTX", "INDIGO.NS", "Pratt & Whitney GTF engines", 2), ("SAF.PA", "INDIGO.NS", "CFM LEAP engines", 2),
    # ---- energy
    ("SLB", "XOM", "Oilfield services & technology", 2), ("SLB", "CVX", "Oilfield services & technology", 2), ("SLB", "2222.SR", "Oilfield services", 2),
    ("HAL", "XOM", "Drilling & completion services", 2), ("HAL", "CVX", "Drilling & completion services", 2), ("BKR", "XOM", "Equipment & services", 1),
    # ---- pharma -> distributors
    ("LLY", "MCK", "Drug distribution", 2), ("LLY", "COR", "Drug distribution", 2), ("LLY", "CAH", "Drug distribution", 2),
    ("PFE", "MCK", "Drug distribution", 2), ("PFE", "COR", "Drug distribution", 2), ("PFE", "CAH", "Drug distribution", 2),
    ("MRK", "MCK", "Drug distribution", 2), ("MRK", "COR", "Drug distribution", 2), ("ABBV", "MCK", "Drug distribution", 2), ("ABBV", "CAH", "Drug distribution", 2),
    ("JNJ", "MCK", "Drug distribution", 2), ("NVO", "MCK", "Drug distribution (US)", 2), ("LONN.SW", "MRNA", "mRNA vaccine manufacturing", 1), ("TMO", "PFE", "Lab equipment, reagents & contract manufacturing", 1),
    # ---- consumer staples -> retail
    ("PG", "WMT", "Household & personal-care products", 3), ("PG", "COST", "Household products", 1), ("PG", "TGT", "Household products", 1), ("PG", "KR", "Household products", 1),
    ("PEP", "WMT", "Snacks & beverages", 2), ("CL", "WMT", "Oral & personal care", 2), ("CLX", "WMT", "Cleaning & household products", 2), ("KMB", "WMT", "Tissue & personal care", 2),
    ("HSY", "WMT", "Confectionery", 2), ("KO", "CCEP", "Concentrate & brand licence", 3), ("KO", "KOF", "Concentrate & brand licence", 3), ("KO", "COKE", "Concentrate & brand licence", 2),
    ("BALL", "KO", "Aluminium cans", 1), ("BALL", "PEP", "Aluminium cans", 1),
]


def _index():
    sup, cus = {}, {}
    for s, c, what, imp in LINKS:
        sup.setdefault(c, []).append((s, what, imp))
        cus.setdefault(s, []).append((c, what, imp))
    return sup, cus


SUPPLIERS, CUSTOMERS = _index()

# industry value chain (Yahoo industry names): upstream inputs and downstream buyers
_CH = {
    "Semiconductors": (["Semiconductor Equipment & Materials", "Specialty Chemicals", "Electronic Components"],
                       ["Consumer Electronics", "Computer Hardware", "Communication Equipment", "Auto Manufacturers", "Internet Content & Information", "Software - Infrastructure"]),
    "Semiconductor Equipment & Materials": (["Specialty Industrial Machinery", "Specialty Chemicals", "Scientific & Technical Instruments"], ["Semiconductors"]),
    "Consumer Electronics": (["Semiconductors", "Electronic Components", "Communication Equipment"], ["Telecom Services", "Internet Retail", "Specialty Retail"]),
    "Computer Hardware": (["Semiconductors", "Electronic Components"], ["Software - Infrastructure", "Internet Content & Information", "Information Technology Services"]),
    "Electronic Components": (["Semiconductors", "Specialty Chemicals", "Copper"], ["Consumer Electronics", "Computer Hardware", "Auto Manufacturers", "Communication Equipment"]),
    "Communication Equipment": (["Semiconductors", "Electronic Components"], ["Telecom Services", "Software - Infrastructure"]),
    "Telecom Services": (["Communication Equipment", "Consumer Electronics", "Software - Infrastructure"], ["Internet Content & Information", "Entertainment", "Software - Application"]),
    "Software - Infrastructure": (["Semiconductors", "Computer Hardware", "Information Technology Services"], ["Software - Application", "Internet Content & Information", "Banks - Diversified"]),
    "Software - Application": (["Software - Infrastructure", "Information Technology Services"], ["Banks - Diversified", "Internet Retail", "Specialty Business Services"]),
    "Information Technology Services": (["Software - Infrastructure", "Computer Hardware"], ["Banks - Diversified", "Insurance - Diversified", "Drug Manufacturers - General", "Telecom Services"]),
    "Internet Content & Information": (["Semiconductors", "Software - Infrastructure", "Computer Hardware", "Utilities - Regulated Electric"], ["Advertising Agencies", "Internet Retail", "Entertainment"]),
    "Internet Retail": (["Integrated Freight & Logistics", "Software - Infrastructure", "Consumer Electronics", "Packaged Foods"], []),
    "Auto Manufacturers": (["Auto Parts", "Steel", "Semiconductors", "Electrical Equipment & Parts", "Aluminum", "Specialty Chemicals"], ["Auto & Truck Dealerships", "Credit Services", "Rental & Leasing Services"]),
    "Auto Parts": (["Steel", "Aluminum", "Semiconductors", "Electronic Components"], ["Auto Manufacturers", "Auto & Truck Dealerships"]),
    "Electrical Equipment & Parts": (["Copper", "Steel", "Semiconductors", "Electronic Components"], ["Utilities - Regulated Electric", "Auto Manufacturers", "Engineering & Construction", "Specialty Industrial Machinery"]),
    "Aerospace & Defense": (["Steel", "Aluminum", "Specialty Chemicals", "Electronic Components", "Semiconductors", "Specialty Industrial Machinery"], ["Airlines"]),
    "Airlines": (["Aerospace & Defense", "Oil & Gas Refining & Marketing", "Airports & Air Services"], ["Travel Services", "Lodging"]),
    "Oil & Gas Integrated": (["Oil & Gas Equipment & Services", "Oil & Gas Drilling", "Steel"], ["Oil & Gas Refining & Marketing", "Chemicals", "Specialty Chemicals", "Airlines", "Utilities - Regulated Electric"]),
    "Oil & Gas E&P": (["Oil & Gas Equipment & Services", "Oil & Gas Drilling"], ["Oil & Gas Midstream", "Oil & Gas Refining & Marketing", "Oil & Gas Integrated"]),
    "Oil & Gas Equipment & Services": (["Steel", "Specialty Industrial Machinery"], ["Oil & Gas Integrated", "Oil & Gas E&P", "Oil & Gas Drilling"]),
    "Oil & Gas Refining & Marketing": (["Oil & Gas Integrated", "Oil & Gas E&P", "Oil & Gas Midstream"], ["Airlines", "Trucking", "Chemicals", "Specialty Chemicals"]),
    "Oil & Gas Midstream": (["Oil & Gas E&P"], ["Oil & Gas Refining & Marketing", "Utilities - Regulated Gas", "Chemicals"]),
    "Chemicals": (["Oil & Gas Integrated", "Oil & Gas Midstream", "Other Industrial Metals & Mining"],
                  ["Semiconductors", "Packaged Foods", "Household & Personal Products", "Auto Manufacturers", "Building Materials", "Agricultural Inputs", "Drug Manufacturers - General"]),
    "Steel": (["Other Industrial Metals & Mining", "Coking Coal", "Utilities - Regulated Electric"],
              ["Auto Manufacturers", "Engineering & Construction", "Specialty Industrial Machinery", "Farm & Heavy Construction Machinery", "Building Materials"]),
    "Other Industrial Metals & Mining": (["Farm & Heavy Construction Machinery", "Specialty Chemicals"], ["Steel", "Aluminum", "Copper", "Electrical Equipment & Parts"]),
    "Copper": (["Farm & Heavy Construction Machinery"], ["Electrical Equipment & Parts", "Electronic Components", "Engineering & Construction"]),
    "Aluminum": (["Other Industrial Metals & Mining", "Utilities - Regulated Electric"], ["Auto Manufacturers", "Aerospace & Defense", "Packaging & Containers", "Beverages - Non-Alcoholic"]),
    "Gold": (["Farm & Heavy Construction Machinery"], ["Luxury Goods", "Capital Markets"]),
    "Farm & Heavy Construction Machinery": (["Steel", "Specialty Industrial Machinery", "Auto Parts"], ["Engineering & Construction", "Other Industrial Metals & Mining", "Agricultural Inputs", "Farm Products"]),
    "Engineering & Construction": (["Building Materials", "Steel", "Farm & Heavy Construction Machinery", "Electrical Equipment & Parts"], ["Utilities - Regulated Electric", "Real Estate - Development", "REIT - Industrial"]),
    "Building Materials": (["Oil & Gas Integrated", "Other Industrial Metals & Mining", "Utilities - Regulated Electric"], ["Engineering & Construction", "Residential Construction", "Real Estate - Development"]),
    "Utilities - Regulated Electric": (["Electrical Equipment & Parts", "Oil & Gas Midstream", "Thermal Coal", "Utilities - Renewable"], ["Internet Content & Information", "Steel", "Aluminum"]),
    "Utilities - Renewable": (["Solar", "Electrical Equipment & Parts"], ["Utilities - Regulated Electric"]),
    "Solar": (["Semiconductor Equipment & Materials", "Specialty Chemicals", "Aluminum"], ["Utilities - Renewable", "Utilities - Regulated Electric"]),
    "Drug Manufacturers - General": (["Specialty Chemicals", "Diagnostics & Research", "Biotechnology", "Medical Instruments & Supplies"], ["Medical Distribution", "Pharmaceutical Retailers", "Healthcare Plans"]),
    "Biotechnology": (["Diagnostics & Research", "Specialty Chemicals"], ["Drug Manufacturers - General", "Medical Distribution"]),
    "Medical Devices": (["Electronic Components", "Specialty Chemicals", "Semiconductors"], ["Medical Care Facilities", "Medical Distribution"]),
    "Medical Distribution": (["Drug Manufacturers - General", "Drug Manufacturers - Specialty & Generic", "Medical Instruments & Supplies"], ["Pharmaceutical Retailers", "Medical Care Facilities"]),
    "Healthcare Plans": (["Medical Care Facilities", "Drug Manufacturers - General", "Medical Distribution"], []),
    "Diagnostics & Research": (["Scientific & Technical Instruments", "Specialty Chemicals"], ["Drug Manufacturers - General", "Biotechnology", "Medical Care Facilities"]),
    "Packaged Foods": (["Farm Products", "Agricultural Inputs", "Packaging & Containers", "Specialty Chemicals"], ["Grocery Stores", "Discount Stores", "Restaurants"]),
    "Beverages - Non-Alcoholic": (["Farm Products", "Packaging & Containers", "Aluminum"], ["Grocery Stores", "Discount Stores", "Restaurants"]),
    "Household & Personal Products": (["Specialty Chemicals", "Chemicals", "Packaging & Containers"], ["Discount Stores", "Grocery Stores", "Internet Retail", "Pharmaceutical Retailers"]),
    "Tobacco": (["Farm Products", "Packaging & Containers"], ["Grocery Stores", "Discount Stores"]),
    "Farm Products": (["Agricultural Inputs", "Farm & Heavy Construction Machinery"], ["Packaged Foods", "Beverages - Non-Alcoholic", "Confectioners"]),
    "Agricultural Inputs": (["Chemicals", "Oil & Gas Integrated", "Other Industrial Metals & Mining"], ["Farm Products"]),
    "Discount Stores": (["Packaged Foods", "Household & Personal Products", "Beverages - Non-Alcoholic", "Integrated Freight & Logistics"], []),
    "Restaurants": (["Packaged Foods", "Farm Products", "Beverages - Non-Alcoholic"], []),
    "Apparel Manufacturing": (["Textile Manufacturing", "Integrated Freight & Logistics"], ["Apparel Retail", "Department Stores", "Internet Retail"]),
    "Luxury Goods": (["Gold", "Textile Manufacturing"], ["Department Stores", "Specialty Retail"]),
    "Banks - Diversified": (["Software - Application", "Information Technology Services", "Financial Data & Stock Exchanges"], ["Real Estate - Development", "Residential Construction", "Auto & Truck Dealerships"]),
    "Credit Services": (["Banks - Diversified", "Software - Infrastructure"], ["Internet Retail", "Specialty Retail", "Travel Services"]),
    "Capital Markets": (["Financial Data & Stock Exchanges", "Software - Application"], []),
    "Integrated Freight & Logistics": (["Oil & Gas Refining & Marketing", "Aerospace & Defense", "Auto Manufacturers"], ["Internet Retail", "Discount Stores", "Specialty Retail"]),
    "Railroads": (["Oil & Gas Refining & Marketing", "Steel", "Specialty Industrial Machinery"], ["Thermal Coal", "Farm Products", "Chemicals", "Auto Manufacturers", "Integrated Freight & Logistics"]),
    "Trucking": (["Auto Manufacturers", "Oil & Gas Refining & Marketing"], ["Discount Stores", "Grocery Stores", "Internet Retail"]),
    "Marine Shipping": (["Oil & Gas Refining & Marketing", "Steel"], ["Oil & Gas Integrated", "Other Industrial Metals & Mining", "Discount Stores"]),
    "Entertainment": (["Internet Content & Information", "Software - Infrastructure"], []),
    "Conglomerates": (["Steel", "Electrical Equipment & Parts", "Specialty Chemicals"], ["Engineering & Construction", "Utilities - Regulated Electric"]),
    "Specialty Industrial Machinery": (["Steel", "Electrical Equipment & Parts", "Electronic Components"], ["Auto Manufacturers", "Aerospace & Defense", "Semiconductor Equipment & Materials", "Engineering & Construction"]),
    "Scientific & Technical Instruments": (["Electronic Components", "Semiconductors"], ["Semiconductor Equipment & Materials", "Drug Manufacturers - General", "Aerospace & Defense"]),
    "Thermal Coal": (["Farm & Heavy Construction Machinery"], ["Utilities - Regulated Electric", "Steel"]),
    "Packaging & Containers": (["Aluminum", "Chemicals", "Paper & Paper Products"], ["Beverages - Non-Alcoholic", "Packaged Foods", "Household & Personal Products"]),
    "Residential Construction": (["Building Materials", "Lumber & Wood Production"], []),
    "Crypto": (["Semiconductors", "Utilities - Regulated Electric"], ["Capital Markets", "Financial Data & Stock Exchanges"]),
}
ALIAS = {"Specialty Chemicals": "Chemicals", "Drug Manufacturers - Specialty & Generic": "Drug Manufacturers - General", "Banks - Regional": "Banks - Diversified",
         "Medical Instruments & Supplies": "Medical Devices", "Grocery Stores": "Discount Stores", "Coking Coal": "Thermal Coal", "Asset Management": "Capital Markets",
         "Insurance - Life": "Capital Markets", "Insurance - Diversified": "Capital Markets", "Insurance - Property & Casualty": "Capital Markets",
         "Beverages - Brewers": "Beverages - Non-Alcoholic", "Beverages - Wineries & Distilleries": "Beverages - Non-Alcoholic", "Confectioners": "Packaged Foods",
         "Footwear & Accessories": "Apparel Manufacturing", "Utilities - Diversified": "Utilities - Regulated Electric", "Utilities - Regulated Gas": "Utilities - Regulated Electric",
         "Oil & Gas Drilling": "Oil & Gas Equipment & Services", "Steel & Iron": "Steel", "Lodging": "Restaurants", "Travel Services": "Restaurants"}
SECTOR_DEFAULT = {"Technology": "Software - Infrastructure", "Energy": "Oil & Gas Integrated", "Healthcare": "Drug Manufacturers - General", "Financial Services": "Banks - Diversified",
                  "Consumer Cyclical": "Auto Manufacturers", "Consumer Defensive": "Packaged Foods", "Industrials": "Specialty Industrial Machinery", "Basic Materials": "Chemicals",
                  "Communication Services": "Telecom Services", "Utilities": "Utilities - Regulated Electric", "Real Estate": "Building Materials"}


def industry_chain(industry: str, sector: str) -> tuple[str, list[str], list[str]]:
    key = industry if industry in _CH else ALIAS.get(industry) if ALIAS.get(industry) in _CH else SECTOR_DEFAULT.get(sector, "")
    up, down = _CH.get(key, ([], []))
    return key, up, down


def _companies_by_industry() -> dict[str, list[str]]:
    by: dict[str, list[str]] = {}
    for sym, info in data._meta.items():
        if isinstance(info, dict) and info.get("industry"):
            by.setdefault(info["industry"], []).append(sym)
    return by


def build(symbol: str, scan_rows: dict[str, dict]) -> dict:
    """Assemble the chain graph around `symbol`: tiers -2..+2, plus 'siblings' that share its suppliers."""
    tier: dict[str, int] = {symbol: 0}
    role: dict[str, str] = {symbol: "focus"}
    edges: list[dict] = []

    def add(s, t, r):
        if s not in tier:
            tier[s], role[s] = t, r
    t1s = sorted(SUPPLIERS.get(symbol, []), key=lambda x: -x[2])[:14]
    t1c = sorted(CUSTOMERS.get(symbol, []), key=lambda x: -x[2])[:14]
    for s, _, _ in t1s:
        add(s, -1, "supplier")
    for c, _, _ in t1c:
        add(c, 1, "customer")
    for s, _, _ in t1s:                                   # suppliers' suppliers
        for s2, _, _ in sorted(SUPPLIERS.get(s, []), key=lambda x: -x[2])[:6]:
            add(s2, -2, "supplier2")
    for c, _, _ in t1c:                                   # customers' customers
        for c2, _, _ in sorted(CUSTOMERS.get(c, []), key=lambda x: -x[2])[:6]:
            add(c2, 2, "customer2")
    shared: dict[str, list[str]] = {}                     # who else my suppliers sell to
    for s, _, _ in t1s:
        for c, _, _ in CUSTOMERS.get(s, []):
            if c != symbol:
                shared.setdefault(c, []).append(s)
    for c, via in sorted(shared.items(), key=lambda x: -len(x[1]))[:12]:
        add(c, 0, "sibling")
    nodes = set(tier)
    for s, c, what, imp in LINKS:
        if s in nodes and c in nodes:
            edges.append({"from": s, "to": c, "what": what, "importance": imp, "kind": "verified"})

    # industry layer (works for any company)
    info = data.info_of(symbol)
    key, up, down = industry_chain(info.get("industry", ""), info.get("sector", ""))
    by = _companies_by_industry()

    def members(ind):
        pool = by.get(ind, []) + by.get(next((k for k, v in ALIAS.items() if v == ind), ""), [])
        ranked = sorted(set(pool) - {symbol}, key=lambda s: (s not in scan_rows, s))
        return ranked[:8]
    ind = {"industry": info.get("industry"), "sector": info.get("sector"), "chainKey": key,
           "up": [{"industry": i, "companies": members(i), "up": industry_chain(i, "")[1][:4]} for i in up],
           "down": [{"industry": i, "companies": members(i), "down": industry_chain(i, "")[2][:4]} for i in down],
           "peers": members(info.get("industry", ""))}
    return {"symbol": symbol, "tier": tier, "role": role, "edges": edges, "shared": {c: v for c, v in shared.items() if c in nodes},
            "industry": ind, "verified": bool(t1s or t1c)}


AI_PROMPT = """List the most important publicly known SUPPLIERS and CUSTOMERS of {name} ({symbol}), a company in {industry}.
Only include relationships you are confident are real and publicly reported. Only listed companies. At most 8 of each.
Respond with ONLY JSON: {{"suppliers": [{{"company": "<company name>", "supplies": "<what they supply>"}}],
"customers": [{{"company": "<company name>", "buys": "<what they buy>"}}]}}"""


def ai_suggest(symbol: str, name: str, industry: str) -> dict:
    import requests
    from . import ai
    st = ai.status()
    if not st["online"]:
        return {"error": "The local AI (Ollama) isn't running.", "suppliers": [], "customers": []}
    r = requests.post(f"{ai.OLLAMA}/api/chat", json={"model": st["model"], "stream": False, "format": "json", "options": {"temperature": 0.1},
                                                  "messages": [{"role": "user", "content": AI_PROMPT.format(name=name, symbol=symbol, industry=industry or "its industry")}]}, timeout=180)
    try:
        j = json.loads(r.json()["message"]["content"])
    except Exception:
        return {"error": "The AI returned an unreadable answer. Try again.", "suppliers": [], "customers": []}

    def resolve(items, key):
        out = []
        for it in (items or [])[:8]:
            nm = str(it.get("company") or "").strip()
            if not nm or nm.lower() in (name or "").lower():
                continue
            hits = [h for h in data.search(nm) if h.get("type", "").lower() in ("equity", "")]
            if hits:
                out.append({"symbol": hits[0]["symbol"], "name": hits[0]["name"], "what": str(it.get(key) or "")[:80], "query": nm})
        return out
    return {"suppliers": resolve(j.get("suppliers"), "supplies"), "customers": resolve(j.get("customers"), "buys"), "model": st["model"]}
