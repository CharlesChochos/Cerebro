"""
Trade flow visualization data — stores bilateral trade, arms, aid, and energy
flows between countries for arc-layer rendering on the globe.
"""
import json
import uuid

# Major global trade lanes (seed data)
# (origin, dest, commodity, volume_usd_billions, type, origin_lat, origin_lng, dest_lat, dest_lng)
SEED_TRADE_FLOWS = [
    ("CN", "US", "electronics", 500e9, "trade", 31.2, 121.5, 40.7, -74.0),
    ("SA", "CN", "crude_oil", 65e9, "energy", 24.7, 46.7, 31.2, 121.5),
    ("RU", "DE", "natural_gas", 20e9, "energy", 55.8, 37.6, 52.5, 13.4),
    ("US", "UA", "arms", 15e9, "arms", 38.9, -77.0, 50.4, 30.5),
    ("CN", "DE", "machinery", 120e9, "trade", 31.2, 121.5, 52.5, 13.4),
    ("AU", "CN", "iron_ore", 80e9, "trade", -33.9, 151.2, 31.2, 121.5),
    ("BR", "CN", "soybeans", 35e9, "trade", -23.6, -46.6, 31.2, 121.5),
    ("US", "IL", "aid", 3.8e9, "aid", 38.9, -77.0, 31.8, 35.2),
    ("QA", "JP", "lng", 25e9, "energy", 25.3, 51.2, 35.7, 139.7),
    ("TW", "US", "semiconductors", 45e9, "trade", 25.0, 121.5, 40.7, -74.0),
    ("RU", "IN", "arms", 8e9, "arms", 55.8, 37.6, 28.6, 77.2),
    ("SA", "IN", "crude_oil", 40e9, "energy", 24.7, 46.7, 28.6, 77.2),
    ("US", "TW", "arms", 10e9, "arms", 38.9, -77.0, 25.0, 121.5),
    ("NG", "EU", "crude_oil", 15e9, "energy", 6.5, 3.4, 50.8, 4.4),
    ("UA", "EG", "wheat", 4e9, "trade", 50.4, 30.5, 30.0, 31.0),
]


def seed_trade_flows(conn) -> int:
    count = 0
    for origin, dest, commodity, vol, ftype, olat, olng, dlat, dlng in SEED_TRADE_FLOWS:
        tid = str(uuid.uuid4())
        try:
            conn.execute(
                """INSERT OR IGNORE INTO trade_flows
                   (id, origin_country, dest_country, commodity, volume_usd,
                    flow_type, year, origin_lat, origin_lng, dest_lat, dest_lng)
                   VALUES (?, ?, ?, ?, ?, ?, 2025, ?, ?, ?, ?)""",
                (tid, origin, dest, commodity, vol, ftype,
                 olat, olng, dlat, dlng),
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    return count


def add_trade_flow(conn, origin_country: str, dest_country: str,
                   commodity: str | None = None, volume_usd: float | None = None,
                   volume_tons: float | None = None, flow_type: str = "trade",
                   year: int | None = None,
                   origin_lat: float | None = None, origin_lng: float | None = None,
                   dest_lat: float | None = None, dest_lng: float | None = None,
                   risk_level: str = "normal") -> str:
    tid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO trade_flows
           (id, origin_country, dest_country, commodity, volume_usd, volume_tons,
            flow_type, year, origin_lat, origin_lng, dest_lat, dest_lng, risk_level)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (tid, origin_country, dest_country, commodity, volume_usd, volume_tons,
         flow_type, year, origin_lat, origin_lng, dest_lat, dest_lng, risk_level),
    )
    conn.commit()
    return tid


def get_trade_flow(conn, flow_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM trade_flows WHERE id = ?",
                       (flow_id,)).fetchone()
    return dict(row) if row else None


def list_trade_flows(conn, origin_country: str | None = None,
                     dest_country: str | None = None,
                     flow_type: str | None = None,
                     commodity: str | None = None,
                     limit: int = 100) -> list[dict]:
    conditions, params = [], []
    if origin_country:
        conditions.append("origin_country = ?"); params.append(origin_country)
    if dest_country:
        conditions.append("dest_country = ?"); params.append(dest_country)
    if flow_type:
        conditions.append("flow_type = ?"); params.append(flow_type)
    if commodity:
        conditions.append("commodity = ?"); params.append(commodity)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM trade_flows{where} ORDER BY volume_usd DESC LIMIT ?",
        params + [limit]).fetchall()
    return [dict(r) for r in rows]


def get_trade_flow_arcs(conn, flow_type: str | None = None,
                        min_volume: float | None = None,
                        limit: int = 200) -> dict:
    """Return trade flows as arc GeoJSON for deck.gl ArcLayer."""
    conditions, params = [], []
    if flow_type:
        conditions.append("flow_type = ?"); params.append(flow_type)
    if min_volume:
        conditions.append("volume_usd >= ?"); params.append(min_volume)
    conditions.append("origin_lat IS NOT NULL AND dest_lat IS NOT NULL")

    where = " WHERE " + " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM trade_flows{where} ORDER BY volume_usd DESC LIMIT ?",
        params + [limit]).fetchall()

    FLOW_COLORS = {
        "trade": [59, 130, 246],     # blue
        "energy": [249, 115, 22],    # orange
        "arms": [239, 68, 68],       # red
        "aid": [34, 197, 94],        # green
        "migration": [168, 85, 247], # purple
    }

    features = []
    for r in rows:
        d = dict(r)
        color = FLOW_COLORS.get(d["flow_type"], [148, 163, 184])
        # Width proportional to log volume
        import math
        width = max(1, min(8, math.log10(max(d["volume_usd"] or 1, 1)) - 7))
        features.append({
            "origin": [d["origin_lng"], d["origin_lat"]],
            "destination": [d["dest_lng"], d["dest_lat"]],
            "origin_country": d["origin_country"],
            "dest_country": d["dest_country"],
            "commodity": d["commodity"],
            "volume_usd": d["volume_usd"],
            "flow_type": d["flow_type"],
            "color": color,
            "width": width,
        })
    return {"flows": features, "total": len(features)}
