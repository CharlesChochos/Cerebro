"""
Commodity dependency mapping — maps countries to their critical commodity
dependencies and assesses supply chain risk.

Tracks:
- Import/export dependencies (% of trade, volume, top partners)
- Risk levels based on concentration, geopolitical factors, conflict proximity
- Disruption scenarios (what happens if supply X is cut off)

Uses seeded data for major global commodity dependencies plus ability to
add custom entries from trade data (Comtrade, etc.).
"""
import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

VALID_DEP_TYPES = {"import", "export", "transit"}
VALID_RISK_LEVELS = {"normal", "elevated", "high", "critical"}

# Seeded critical dependencies for analysis
CRITICAL_DEPENDENCIES = [
    {"country_code": "CN", "commodity_name": "Crude Oil", "dependency_type": "import",
     "share_pct": 72.0, "top_partners": ["SA", "RU", "IQ", "AO", "BR"],
     "risk_factors": ["Strait of Malacca chokepoint", "Sanctions risk on Russia/Iran"]},
    {"country_code": "DE", "commodity_name": "Natural Gas", "dependency_type": "import",
     "share_pct": 55.0, "top_partners": ["NO", "NL", "US"],
     "risk_factors": ["Post-Russia diversification", "LNG infrastructure limits"]},
    {"country_code": "JP", "commodity_name": "LNG", "dependency_type": "import",
     "share_pct": 95.0, "top_partners": ["AU", "MY", "QA", "US"],
     "risk_factors": ["No pipeline alternatives", "Shipping lane vulnerability"]},
    {"country_code": "US", "commodity_name": "Rare Earth Elements", "dependency_type": "import",
     "share_pct": 80.0, "top_partners": ["CN", "MY", "JP"],
     "risk_factors": ["China dominance", "Limited alternative sources", "Defense supply chain"]},
    {"country_code": "EG", "commodity_name": "Wheat", "dependency_type": "import",
     "share_pct": 62.0, "top_partners": ["RU", "UA", "FR", "RO"],
     "risk_factors": ["Black Sea conflict disruption", "Price volatility", "Food security"]},
    {"country_code": "IN", "commodity_name": "Crude Oil", "dependency_type": "import",
     "share_pct": 85.0, "top_partners": ["IQ", "SA", "RU", "AE", "KW"],
     "risk_factors": ["Strait of Hormuz chokepoint", "Sanctions compliance"]},
    {"country_code": "TW", "commodity_name": "Semiconductors", "dependency_type": "export",
     "share_pct": 63.0, "top_partners": ["US", "CN", "JP", "KR"],
     "risk_factors": ["Cross-strait tension", "Single point of failure for global chip supply"]},
    {"country_code": "AU", "commodity_name": "Iron Ore", "dependency_type": "export",
     "share_pct": 55.0, "top_partners": ["CN", "JP", "KR"],
     "risk_factors": ["China demand dependency", "Trade tensions"]},
]


def seed_dependencies(conn) -> int:
    """Seed critical commodity dependencies if table is empty."""
    existing = conn.execute("SELECT COUNT(*) as c FROM commodity_dependencies").fetchone()["c"]
    if existing > 0:
        return 0

    count = 0
    for dep in CRITICAL_DEPENDENCIES:
        did = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO commodity_dependencies
               (id, country_code, commodity_name, dependency_type, share_pct,
                top_partners, risk_level, risk_factors)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                did, dep["country_code"], dep["commodity_name"],
                dep["dependency_type"], dep["share_pct"],
                json.dumps(dep["top_partners"]),
                "elevated" if dep["share_pct"] > 70 else "normal",
                json.dumps(dep["risk_factors"]),
            ),
        )
        count += 1

    conn.commit()
    return count


def add_dependency(
    conn,
    country_code: str,
    commodity_name: str,
    dependency_type: str = "import",
    share_pct: float | None = None,
    volume_usd: float | None = None,
    top_partners: list[str] | None = None,
    risk_level: str = "normal",
    risk_factors: list[str] | None = None,
    commodity_code: str | None = None,
) -> str:
    """Add a commodity dependency record."""
    did = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO commodity_dependencies
           (id, country_code, commodity_name, commodity_code, dependency_type,
            share_pct, volume_usd, top_partners, risk_level, risk_factors)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            did, country_code, commodity_name, commodity_code,
            dependency_type if dependency_type in VALID_DEP_TYPES else "import",
            share_pct, volume_usd,
            json.dumps(top_partners or []),
            risk_level if risk_level in VALID_RISK_LEVELS else "normal",
            json.dumps(risk_factors or []),
        ),
    )
    conn.commit()
    return did


def get_dependency(conn, dep_id: str) -> dict | None:
    """Get a single dependency record."""
    row = conn.execute("SELECT * FROM commodity_dependencies WHERE id = ?", (dep_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["top_partners"] = json.loads(d["top_partners"]) if d["top_partners"] else []
    d["risk_factors"] = json.loads(d["risk_factors"]) if d["risk_factors"] else []
    return d


def list_dependencies(
    conn,
    country_code: str | None = None,
    commodity_name: str | None = None,
    dependency_type: str | None = None,
    risk_level: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """List commodity dependencies with optional filters."""
    conditions = []
    params: list = []

    if country_code:
        conditions.append("country_code = ?")
        params.append(country_code)
    if commodity_name:
        conditions.append("commodity_name LIKE ?")
        params.append(f"%{commodity_name}%")
    if dependency_type and dependency_type in VALID_DEP_TYPES:
        conditions.append("dependency_type = ?")
        params.append(dependency_type)
    if risk_level and risk_level in VALID_RISK_LEVELS:
        conditions.append("risk_level = ?")
        params.append(risk_level)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM commodity_dependencies{where} ORDER BY share_pct DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["top_partners"] = json.loads(d["top_partners"]) if d["top_partners"] else []
        d["risk_factors"] = json.loads(d["risk_factors"]) if d["risk_factors"] else []
        results.append(d)
    return results


def assess_country_risk(conn, country_code: str) -> dict:
    """
    Assess overall commodity risk for a country — how vulnerable is it
    to supply chain disruptions?
    """
    deps = list_dependencies(conn, country_code=country_code)
    if not deps:
        return {
            "country_code": country_code,
            "total_dependencies": 0,
            "overall_risk": "unknown",
            "critical_commodities": [],
        }

    critical = [d for d in deps if d["share_pct"] and d["share_pct"] > 50]
    high_risk = [d for d in deps if d["risk_level"] in ("high", "critical")]

    risk_score = 0
    for d in deps:
        share = d["share_pct"] or 0
        risk_mult = {"normal": 1, "elevated": 1.5, "high": 2, "critical": 3}.get(d["risk_level"], 1)
        risk_score += (share / 100) * risk_mult

    overall = "low"
    if risk_score > 3.0:
        overall = "critical"
    elif risk_score > 2.0:
        overall = "high"
    elif risk_score > 1.0:
        overall = "elevated"

    return {
        "country_code": country_code,
        "total_dependencies": len(deps),
        "critical_dependencies": len(critical),
        "high_risk_dependencies": len(high_risk),
        "risk_score": round(risk_score, 2),
        "overall_risk": overall,
        "critical_commodities": [
            {"commodity": d["commodity_name"], "share_pct": d["share_pct"],
             "risk_level": d["risk_level"]}
            for d in critical
        ],
        "dependencies": deps,
    }


def find_disruption_impact(conn, commodity_name: str) -> dict:
    """
    Assess which countries would be most impacted by a disruption
    in supply of a given commodity.
    """
    deps = list_dependencies(conn, commodity_name=commodity_name)
    importers = [d for d in deps if d["dependency_type"] == "import"]
    exporters = [d for d in deps if d["dependency_type"] == "export"]

    importers.sort(key=lambda d: d["share_pct"] or 0, reverse=True)

    return {
        "commodity": commodity_name,
        "total_dependencies": len(deps),
        "import_dependent_countries": len(importers),
        "export_countries": len(exporters),
        "most_vulnerable": [
            {"country_code": d["country_code"], "share_pct": d["share_pct"],
             "risk_level": d["risk_level"]}
            for d in importers[:10]
        ],
        "exporters": [
            {"country_code": d["country_code"], "share_pct": d["share_pct"]}
            for d in exporters[:10]
        ],
    }
