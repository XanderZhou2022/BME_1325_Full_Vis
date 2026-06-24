from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.seed import sync_locations_and_beds, validate_rule_room_references


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def test_catalog_sync_adds_new_rooms_and_preserves_occupied_beds():
    conn = make_db()
    initial = {
        "floors": [
            {
                "id": 2,
                "rooms": [
                    {"id": "R-OP-INTERNAL", "label": "Internal A", "kind": "internal_medicine"},
                ],
            }
        ]
    }
    room_state = {"rooms": {"R-OP-INTERNAL": {"capacityBeds": 1}}}
    sync_locations_and_beds(conn, map_config=initial, room_state=room_state)
    conn.execute(
        "INSERT INTO patients (patient_id,name,status,profile_json,created_at,updated_at) VALUES ('P-a1b2c3d4','Test','ACTIVE','{}','now','now')"
    )
    conn.execute(
        "UPDATE beds SET status='occupied', patient_id='P-a1b2c3d4' WHERE room_id='R-OP-INTERNAL' AND bed_index=1"
    )

    updated = {
        "floors": [
            {
                "id": 2,
                "rooms": [
                    {
                        "id": "R-OP-INTERNAL",
                        "label": "Internal Medicine A",
                        "kind": "internal_medicine",
                        "consultSlots": 1,
                    },
                    {
                        "id": "R-OP-QUEUE-INTERNAL",
                        "label": "Internal Queue",
                        "kind": "waiting",
                        "queueAnchor": True,
                        "queueFor": ["R-OP-INTERNAL"],
                    },
                ],
            }
        ]
    }
    updated_state = {"rooms": {"R-OP-INTERNAL": {"capacityBeds": 2}}}
    result = sync_locations_and_beds(conn, map_config=updated, room_state=updated_state)

    occupied = conn.execute(
        "SELECT status, patient_id FROM beds WHERE room_id='R-OP-INTERNAL' AND bed_index=1"
    ).fetchone()
    assert dict(occupied) == {"status": "occupied", "patient_id": "P-a1b2c3d4"}
    assert conn.execute("SELECT COUNT(*) FROM beds WHERE room_id='R-OP-INTERNAL'").fetchone()[0] == 2
    queue = conn.execute("SELECT map_json FROM locations WHERE room_id='R-OP-QUEUE-INTERNAL'").fetchone()
    assert json.loads(queue["map_json"])["queueFor"] == ["R-OP-INTERNAL"]
    assert result["inserted_rooms"] == 1
    assert result["inserted_beds"] == 1


def test_rule_validation_rejects_missing_canonical_room(tmp_path):
    conn = make_db()
    sync_locations_and_beds(
        conn,
        map_config={"floors": [{"id": 2, "rooms": [{"id": "R-OP-TRIAGE", "kind": "triage"}]}]},
        room_state={},
    )
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "outpatient.json").write_text(
        json.dumps({"rules": [{"movement": {"from": "R-OP-TRIAGE", "to": "R-OP-MISSING"}}]}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="R-OP-MISSING"):
        validate_rule_room_references(conn, rules_dir=rules_dir)