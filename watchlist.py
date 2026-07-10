"""
Curated ticker watchlist for MicroDigests_bot.

WHY THIS EXISTS:
The old bot let the model invent tickers from a bare headline, so you got
plausible-but-fake symbols you couldn't trust. Now the analysis model may ONLY
cite tickers that appear in this file. If the real company is private or doesn't
fit, the model must say "no clean public proxy" (and may name the nearest listed
read-through from this same list, e.g. Varda -> RKLB).

MAINTENANCE:
- Keep symbols real and liquid. Exchange suffixes matter for yfinance price lookups
  (e.g. LYC.AX = Lynas on the ASX; no suffix = US listing).
- Add/remove names as your interests move. This is your personal universe.
Format per row: (TICKER, "Name", "one-line what-it-is")
"""

WATCHLIST = {
    "rare_earths_critical_minerals": [
        ("MP",     "MP Materials",              "US rare-earth miner (Mountain Pass)"),
        ("LYC.AX", "Lynas Rare Earths",         "Largest non-China rare-earth producer (ASX)"),
        ("REMX",   "VanEck Rare Earth ETF",     "Rare-earth / strategic-metals basket"),
        ("TMC",    "TMC the metals company",    "Deep-sea polymetallic nodules"),
        ("UUUU",   "Energy Fuels",              "US uranium + rare-earth processing"),
        ("VUL.AX", "Vulcan Energy",             "Lithium + geothermal (ASX)"),
    ],
    "lithium": [
        ("ALB",  "Albemarle",                   "Largest lithium producer"),
        ("SQM",  "Sociedad Quimica (SQM)",      "Chile lithium & chemicals"),
        ("LAC",  "Lithium Americas",            "US (Thacker Pass) lithium"),
        ("LIT",  "Global X Lithium ETF",        "Lithium + battery-tech basket"),
    ],
    "copper": [
        ("FCX",  "Freeport-McMoRan",            "Major copper / gold miner"),
        ("SCCO", "Southern Copper",             "Low-cost copper producer"),
        ("COPX", "Global X Copper Miners ETF",  "Copper miners basket"),
        ("TECK", "Teck Resources",              "Copper / zinc diversified miner"),
    ],
    "uranium_nuclear": [
        ("CCJ",  "Cameco",                      "Largest Western uranium miner"),
        ("URA",  "Global X Uranium ETF",        "Uranium miners + fuel-cycle basket"),
        ("URNM", "Sprott Uranium Miners ETF",   "Pure-play uranium miners"),
    ],
    "space_launch_primes": [
        ("RKLB", "Rocket Lab",                  "Small-launch + spacecraft"),
        ("LMT",  "Lockheed Martin",             "Defense / space prime"),
        ("RTX",  "RTX (Raytheon)",              "Defense / space systems"),
        ("BA",   "Boeing",                      "Aerospace / defense / space prime"),
        ("NOC",  "Northrop Grumman",            "Defense / space prime"),
        ("LHX",  "L3Harris",                    "Defense / space electronics"),
    ],
    "satellites_space_economy": [
        ("ASTS", "AST SpaceMobile",             "Direct-to-cell satellite broadband"),
        ("PL",   "Planet Labs",                 "Earth-observation satellites"),
        ("LUNR", "Intuitive Machines",          "Lunar landers / services"),
        ("RDW",  "Redwire",                     "Space infrastructure / manufacturing"),
        ("IRDM", "Iridium",                     "Satellite comms network"),
        ("GSAT", "Globalstar",                  "Satellite connectivity"),
    ],
    "space_defense_etfs": [
        ("UFO",  "Procure Space ETF",           "Pure-play space basket"),
        ("ARKX", "ARK Space Exploration ETF",   "Space + adjacents basket"),
        ("ITA",  "iShares US Aerospace & Defense ETF", "Aerospace / defense basket"),
    ],
    "quantum_computing": [
        ("IONQ", "IonQ",                        "Trapped-ion quantum computing"),
        ("RGTI", "Rigetti Computing",           "Superconducting quantum chips"),
        ("QBTS", "D-Wave Quantum",              "Quantum annealing"),
        ("ARQQ", "Arqit Quantum",               "Quantum-safe encryption"),
    ],
    "semiconductors_compute": [
        ("NVDA", "Nvidia",                      "AI / compute GPUs"),
        ("AMD",  "AMD",                         "CPUs / GPUs / AI accelerators"),
        ("TSM",  "TSMC",                        "Leading-edge chip foundry"),
        ("ASML", "ASML",                        "EUV lithography (chip-making)"),
        ("SMH",  "VanEck Semiconductor ETF",    "Chip-sector basket"),
    ],
    "defense_tech": [
        ("PLTR", "Palantir",                    "Defense / gov AI software"),
        ("KTOS", "Kratos Defense",              "Drones, hypersonics, space"),
        ("AVAV", "AeroVironment",               "Military drones / UAS"),
        ("LDOS", "Leidos",                      "Defense IT / tech"),
        ("GD",   "General Dynamics",            "Defense prime"),
    ],
    "ai_biotech": [
        ("RXRX", "Recursion Pharmaceuticals",   "AI-driven drug discovery"),
        ("SDGR", "Schrodinger",                 "Physics/ML drug design"),
        ("TEM",  "Tempus AI",                   "AI diagnostics / precision medicine"),
    ],
}


def all_tickers():
    """Flat set of every allowed ticker symbol."""
    return {t for rows in WATCHLIST.values() for (t, _, _) in rows}


def render_for_prompt():
    """Human-readable block injected into the analysis prompt so the model
    only cites tickers that actually exist in your universe."""
    lines = []
    for sector, rows in WATCHLIST.items():
        pretty = sector.replace("_", " ").title()
        lines.append(f"{pretty}:")
        for (t, name, desc) in rows:
            lines.append(f"  {t} = {name} ({desc})")
    return "\n".join(lines)
