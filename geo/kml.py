"""
KML/KMZ import and export for interoperability with GIS tools.

KML = Keyhole Markup Language (Google Earth XML format)
KMZ = Zipped KML file

Supports:
- Import: Parse KML/KMZ placemarks into events or geofences
- Export: Generate KML from events, geofences, or deployments
"""
import io
import json
import logging
import uuid
import zipfile
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

KML_NS = "http://www.opengis.net/kml/2.2"

KML_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<name>{name}</name>
<description>{description}</description>
"""

KML_FOOTER = """</Document>
</kml>"""

STYLE_TEMPLATE = """<Style id="{id}">
  <IconStyle><color>{color}</color><scale>1.0</scale></IconStyle>
  <PolyStyle><color>{poly_color}</color><outline>1</outline></PolyStyle>
</Style>
"""

PLACEMARK_POINT = """<Placemark>
  <name>{name}</name>
  <description>{description}</description>
  <styleUrl>#{style}</styleUrl>
  <Point><coordinates>{lng},{lat},{alt}</coordinates></Point>
</Placemark>
"""

PLACEMARK_POLYGON = """<Placemark>
  <name>{name}</name>
  <description>{description}</description>
  <styleUrl>#{style}</styleUrl>
  <Polygon>
    <outerBoundaryIs><LinearRing>
      <coordinates>{coordinates}</coordinates>
    </LinearRing></outerBoundaryIs>
  </Polygon>
</Placemark>
"""

# Category → KML color (aabbggrr format, reversed from typical hex)
CATEGORY_COLORS = {
    "military": "ff0000ff",      # Red
    "political": "ffff8800",     # Orange
    "economic": "ff00ff00",      # Green
    "health": "ff00ffff",        # Yellow
    "environmental": "ffffff00", # Cyan
}


def parse_kml(kml_text: str) -> list[dict]:
    """
    Parse KML text and extract placemarks.
    Returns list of dicts with name, description, geometry type, coordinates.
    """
    placemarks = []

    try:
        root = ET.fromstring(kml_text)
    except ET.ParseError as e:
        logger.error("KML parse error: %s", e)
        return []

    # Register namespace for searching
    ns = {"kml": KML_NS}

    for pm in root.iter(f"{{{KML_NS}}}Placemark"):
        placemark = {
            "id": str(uuid.uuid4()),
            "name": "",
            "description": "",
            "geometry_type": None,
            "coordinates": [],
        }

        name_el = pm.find("kml:name", ns)
        if name_el is not None and name_el.text:
            placemark["name"] = name_el.text.strip()

        desc_el = pm.find("kml:description", ns)
        if desc_el is not None and desc_el.text:
            placemark["description"] = desc_el.text.strip()

        # Parse Point
        point = pm.find(".//kml:Point/kml:coordinates", ns)
        if point is not None and point.text:
            placemark["geometry_type"] = "Point"
            coords = parse_kml_coordinates(point.text.strip())
            if coords:
                placemark["coordinates"] = coords[0]  # [lng, lat, alt]

        # Parse Polygon
        polygon = pm.find(".//kml:Polygon//kml:coordinates", ns)
        if polygon is not None and polygon.text:
            placemark["geometry_type"] = "Polygon"
            placemark["coordinates"] = parse_kml_coordinates(polygon.text.strip())

        # Parse LineString
        line = pm.find(".//kml:LineString/kml:coordinates", ns)
        if line is not None and line.text:
            placemark["geometry_type"] = "LineString"
            placemark["coordinates"] = parse_kml_coordinates(line.text.strip())

        if placemark["geometry_type"]:
            placemarks.append(placemark)

    return placemarks


def parse_kml_coordinates(coord_text: str) -> list[list[float]]:
    """
    Parse KML coordinate string: 'lng,lat,alt lng,lat,alt ...'
    Returns list of [lng, lat, alt] tuples.
    """
    coords = []
    for token in coord_text.strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lng = float(parts[0])
                lat = float(parts[1])
                alt = float(parts[2]) if len(parts) > 2 else 0.0
                coords.append([lng, lat, alt])
            except ValueError:
                continue
    return coords


def parse_kmz(kmz_bytes: bytes) -> list[dict]:
    """
    Parse KMZ (zipped KML) and extract placemarks.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(kmz_bytes)) as zf:
            for name in zf.namelist():
                if name.endswith(".kml"):
                    kml_text = zf.read(name).decode("utf-8")
                    return parse_kml(kml_text)
    except (zipfile.BadZipFile, UnicodeDecodeError) as e:
        logger.error("KMZ parse error: %s", e)
    return []


def export_events_kml(conn, name: str = "Cerebro Events", **filters) -> str:
    """
    Export events as KML placemarks.
    Filters: category, severity_min, hours, country_code.
    """
    conditions = ["latitude IS NOT NULL", "longitude IS NOT NULL"]
    params: list = []

    if filters.get("category"):
        conditions.append("category = ?")
        params.append(filters["category"])
    if filters.get("severity_min"):
        conditions.append("severity >= ?")
        params.append(filters["severity_min"])
    if filters.get("hours"):
        conditions.append("julianday('now') - julianday(timestamp) <= ?")
        params.append(filters["hours"] / 24.0)
    if filters.get("country_code"):
        conditions.append("country_code = ?")
        params.append(filters["country_code"])

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""SELECT id, title, summary, category, severity, latitude, longitude, timestamp
            FROM events WHERE {where}
            ORDER BY severity DESC LIMIT 500""",
        params,
    ).fetchall()

    kml = KML_HEADER.format(name=_escape_xml(name), description="Exported from Cerebro")

    # Add styles
    for cat, color in CATEGORY_COLORS.items():
        kml += STYLE_TEMPLATE.format(id=cat, color=color, poly_color="7f" + color[2:])

    # Add placemarks
    for row in rows:
        e = dict(row)
        style = e.get("category", "military") or "military"
        desc = f"Severity: {e['severity']}\nSource: {e.get('timestamp', '')}\n{e.get('summary', '') or ''}"
        kml += PLACEMARK_POINT.format(
            name=_escape_xml(e["title"]),
            description=_escape_xml(desc),
            style=style,
            lng=e["longitude"], lat=e["latitude"], alt=0,
        )

    kml += KML_FOOTER
    return kml


def export_geofences_kml(conn, name: str = "Cerebro Geofences") -> str:
    """Export geofences as KML polygons."""
    rows = conn.execute(
        "SELECT id, name, description, polygon_json, category FROM geofences WHERE active = 1"
    ).fetchall()

    kml = KML_HEADER.format(name=_escape_xml(name), description="Geofences from Cerebro")

    for cat, color in CATEGORY_COLORS.items():
        kml += STYLE_TEMPLATE.format(id=cat, color=color, poly_color="4d" + color[2:])

    for row in rows:
        f = dict(row)
        try:
            geojson = json.loads(f["polygon_json"])
            coords = geojson["coordinates"][0]
            coord_str = " ".join(f"{c[0]},{c[1]},0" for c in coords)
        except (json.JSONDecodeError, KeyError, IndexError):
            continue

        style = f.get("category", "custom") or "military"
        kml += PLACEMARK_POLYGON.format(
            name=_escape_xml(f["name"]),
            description=_escape_xml(f.get("description", "") or ""),
            style=style,
            coordinates=coord_str,
        )

    kml += KML_FOOTER
    return kml


def export_deployments_kml(conn, name: str = "Weapons Deployments") -> str:
    """Export weapons deployments as KML placemarks with range info."""
    rows = conn.execute(
        """SELECT wd.*, ws.name as system_name, ws.max_range_km, ws.system_type
           FROM weapons_deployments wd
           JOIN weapons_systems ws ON ws.id = wd.system_id
           WHERE wd.status = 'active'"""
    ).fetchall()

    kml = KML_HEADER.format(name=_escape_xml(name), description="Weapons deployments from Cerebro")
    kml += STYLE_TEMPLATE.format(id="deployment", color="ff0000ff", poly_color="4d0000ff")

    for row in rows:
        d = dict(row)
        desc = (
            f"System: {d['system_name']}\n"
            f"Type: {d['system_type']}\n"
            f"Range: {d['max_range_km']} km\n"
            f"Status: {d['status']}\n"
            f"Confidence: {d.get('confidence', 'N/A')}"
        )
        kml += PLACEMARK_POINT.format(
            name=_escape_xml(d.get("name", d["system_name"])),
            description=_escape_xml(desc),
            style="deployment",
            lng=d["lng"], lat=d["lat"], alt=0,
        )

    kml += KML_FOOTER
    return kml


def generate_kmz(kml_text: str) -> bytes:
    """Pack a KML string into a KMZ (zip) file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml_text)
    return buf.getvalue()


def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
