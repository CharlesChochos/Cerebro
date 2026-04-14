"""
Map annotations / drawing tools — CRUD for user-drawn markers, lines,
polygons, circles, freehand sketches, and text labels on the map.
"""
import json
import uuid

VALID_TYPES = {"marker", "line", "polygon", "circle", "freehand", "text", "rectangle"}


def create_annotation(conn, annotation_type: str, geometry_json: str | dict,
                      properties_json: dict | None = None,
                      title: str | None = None,
                      description: str | None = None,
                      created_by: str | None = None,
                      layer_name: str = "default") -> str:
    aid = str(uuid.uuid4())
    atype = annotation_type if annotation_type in VALID_TYPES else "marker"
    geo = json.dumps(geometry_json) if isinstance(geometry_json, dict) else geometry_json
    props = json.dumps(properties_json) if properties_json else None
    conn.execute(
        """INSERT INTO map_annotations
           (id, annotation_type, geometry_json, properties_json,
            title, description, created_by, layer_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (aid, atype, geo, props, title, description, created_by, layer_name),
    )
    conn.commit()
    return aid


def get_annotation(conn, annotation_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM map_annotations WHERE id = ?",
                       (annotation_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["geometry"] = json.loads(d["geometry_json"])
    d["properties"] = json.loads(d["properties_json"]) if d["properties_json"] else None
    return d


def list_annotations(conn, layer_name: str | None = None,
                     annotation_type: str | None = None,
                     created_by: str | None = None,
                     limit: int = 200) -> list[dict]:
    conditions, params = ["visible = 1"], []
    if layer_name:
        conditions.append("layer_name = ?"); params.append(layer_name)
    if annotation_type:
        conditions.append("annotation_type = ?"); params.append(annotation_type)
    if created_by:
        conditions.append("created_by = ?"); params.append(created_by)

    where = " WHERE " + " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM map_annotations{where} ORDER BY created_at DESC LIMIT ?",
        params + [limit]).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["geometry"] = json.loads(d["geometry_json"])
        d["properties"] = json.loads(d["properties_json"]) if d["properties_json"] else None
        results.append(d)
    return results


def update_annotation(conn, annotation_id: str,
                      geometry_json: str | dict | None = None,
                      properties_json: dict | None = None,
                      title: str | None = None,
                      description: str | None = None,
                      visible: bool | None = None) -> bool:
    updates, params = [], []
    if geometry_json is not None:
        geo = json.dumps(geometry_json) if isinstance(geometry_json, dict) else geometry_json
        updates.append("geometry_json = ?"); params.append(geo)
    if properties_json is not None:
        updates.append("properties_json = ?"); params.append(json.dumps(properties_json))
    if title is not None:
        updates.append("title = ?"); params.append(title)
    if description is not None:
        updates.append("description = ?"); params.append(description)
    if visible is not None:
        updates.append("visible = ?"); params.append(1 if visible else 0)

    if not updates:
        return False

    updates.append("updated_at = datetime('now')")
    params.append(annotation_id)
    result = conn.execute(
        f"UPDATE map_annotations SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    return result.rowcount > 0


def delete_annotation(conn, annotation_id: str) -> bool:
    result = conn.execute("DELETE FROM map_annotations WHERE id = ?",
                          (annotation_id,))
    conn.commit()
    return result.rowcount > 0


def get_annotations_geojson(conn, layer_name: str | None = None) -> dict:
    """Return annotations as GeoJSON FeatureCollection."""
    items = list_annotations(conn, layer_name=layer_name, limit=500)
    features = []
    for a in items:
        features.append({
            "type": "Feature",
            "geometry": a["geometry"],
            "properties": {
                "id": a["id"],
                "annotation_type": a["annotation_type"],
                "title": a["title"],
                "description": a["description"],
                "layer_name": a["layer_name"],
                "created_by": a["created_by"],
                **(a["properties"] or {}),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def list_layers(conn) -> list[dict]:
    """List all annotation layers with counts."""
    rows = conn.execute(
        """SELECT layer_name, COUNT(*) as annotation_count
           FROM map_annotations WHERE visible = 1
           GROUP BY layer_name ORDER BY annotation_count DESC"""
    ).fetchall()
    return [dict(r) for r in rows]
