"""
players.py — a curated "who's who" of each field, served on demand by the reply
bot ("players space", "players tech", …). The point is to turn floating names in
the news into a map: who the player is, which country, and roughly where they sit.

This is a hand-maintained snapshot, not a live ranking — edit freely as you learn.
Rows are (Name, ISO-2 country, one-line what-they-are).
"""

PLAYERS = {
    "space": [
        ("Leaders", [
            ("SpaceX", "US", "reusable rockets + Starlink; sets the pace"),
            ("CASC", "CN", "China's state launch & spacecraft giant"),
        ]),
        ("Challengers", [
            ("Rocket Lab", "US", "small/medium launch + spacecraft"),
            ("Blue Origin", "US", "Bezos's New Glenn + lunar ambitions"),
            ("ULA", "US", "Boeing/Lockheed heavy-lift launcher"),
            ("Arianespace", "FR", "Europe's launch provider (Ariane 6)"),
            ("ISRO", "IN", "India's fast-rising space agency"),
        ]),
        ("Emerging", [
            ("ElevationSpace", "JP", "return-from-orbit re-entry capsules"),
            ("Varda", "US", "in-space drug manufacturing + re-entry"),
            ("Stoke Space", "US", "aiming for fully reusable rockets"),
            ("ispace", "JP", "commercial lunar landers"),
            ("Skyroot", "IN", "private Indian launch startup"),
        ]),
    ],
    "minerals": [
        ("Rare earths", [
            ("China Northern REE", "CN", "dominant rare-earth refiner"),
            ("MP Materials", "US", "US mine + magnet build-out"),
            ("Lynas", "AU", "top non-China producer"),
        ]),
        ("Lithium", [
            ("Albemarle", "US", "largest lithium producer"),
            ("SQM", "CL", "Chile brine lithium"),
            ("Ganfeng", "CN", "Chinese lithium major"),
        ]),
        ("Copper & majors", [
            ("Freeport-McMoRan", "US", "major copper/gold"),
            ("Codelco", "CL", "state-owned copper giant"),
            ("BHP", "AU", "diversified mining major"),
            ("Rio Tinto", "GB", "iron ore + diversified"),
        ]),
        ("Frontier", [
            ("TMC", "CA", "deep-sea polymetallic nodules"),
            ("KoBold Metals", "US", "AI-driven mineral exploration"),
        ]),
    ],
    "tech": [
        ("Quantum", [
            ("IBM", "US", "superconducting roadmap"),
            ("Google Quantum", "US", "error-correction milestones"),
            ("IonQ", "US", "trapped-ion, public"),
            ("PsiQuantum", "US", "photonic, fault-tolerant bet"),
            ("Quantinuum", "GB", "Honeywell/CQ trapped-ion"),
        ]),
        ("Chips", [
            ("TSMC", "TW", "makes most advanced chips"),
            ("Nvidia", "US", "AI compute leader"),
            ("ASML", "NL", "sole EUV lithography maker"),
            ("Samsung", "KR", "memory + foundry"),
        ]),
        ("AI", [
            ("OpenAI", "US", "frontier models"),
            ("Anthropic", "US", "frontier models (Claude)"),
            ("Google DeepMind", "GB", "research + Gemini"),
            ("DeepSeek", "CN", "China's efficient models"),
        ]),
        ("Defense tech", [
            ("Anduril", "US", "autonomous defense systems"),
            ("Palantir", "US", "defense/gov AI software"),
            ("Lockheed Martin", "US", "prime; space + missiles"),
            ("Rheinmetall", "DE", "Europe's arms leader"),
        ]),
        ("Robotics", [
            ("Boston Dynamics", "US", "advanced mobile robots"),
            ("Figure", "US", "humanoid robots"),
            ("Unitree", "CN", "low-cost humanoids/quadrupeds"),
        ]),
        ("Nuclear & fusion", [
            ("TerraPower", "US", "Gates-backed advanced reactors"),
            ("NuScale", "US", "small modular reactors (SMRs)"),
            ("Commonwealth Fusion", "US", "leading fusion startup"),
            ("Helion", "US", "fusion, aims for electricity"),
        ]),
        ("Space bio", [
            ("Varda", "US", "pharma made in orbit"),
            ("Recursion", "US", "AI drug discovery"),
            ("Isomorphic Labs", "GB", "DeepMind's drug-design spinout"),
        ]),
    ],
    "society": [
        ("Space agencies", [
            ("NASA", "US", "leads Artemis Accords bloc"),
            ("CNSA", "CN", "China; ILRS lunar bloc w/ Russia"),
            ("ESA", "FR", "Europe's multi-nation agency"),
            ("ISRO", "IN", "India; low-cost missions"),
            ("Roscosmos", "RU", "Russia; aligned with China"),
        ]),
    ],
}

THEME_LABEL = {
    "space": "🚀 SPACE", "minerals": "⛏️ MINERALS & MATERIALS",
    "tech": "🔬 FRONTIER TECH", "society": "🌍 SOCIETY & POWER",
}


def _flag(iso):
    iso = (iso or "").strip().upper()
    if len(iso) != 2 or not iso.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso)


def render(theme):
    import html
    groups = PLAYERS.get(theme)
    if not groups:
        return None
    lines = [f"{THEME_LABEL.get(theme, theme.title())} — <b>who's who</b>"]
    for label, rows in groups:
        lines.append(f"\n<b>{html.escape(label)}</b>")
        for name, iso, desc in rows:
            fl = _flag(iso)
            fl = f"{fl} " if fl else ""
            lines.append(f"› {fl}<b>{html.escape(name)}</b> — {html.escape(desc)}")
    lines.append("\n<i>A rough map to learn the field, not a strict ranking.</i>")
    return "\n".join(lines)
