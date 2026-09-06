from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.db")) as test_client:
        yield test_client


def payload(start=0, end=1, equipment_id=1):
    base = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=7)
    return {"equipment_id": equipment_id, "student_name": "Demo Student",
            "start_at": (base + timedelta(hours=start)).isoformat(),
            "end_at": (base + timedelta(hours=end)).isoformat()}


@pytest.mark.parametrize("start,end", [(0, 1), (-1, .5), (.5, 2), (-1, 2), (.2, .8)])
def test_overlapping_reservations_are_rejected(client, start, end):
    assert client.post("/bookings", json=payload()).status_code == 201
    assert client.post("/bookings", json=payload(start, end)).status_code == 409
    assert len(client.get("/bookings").json()) == 1


def test_adjacent_and_other_equipment_are_allowed(client):
    for booking in [payload(), payload(1, 2), payload(-1, 0), payload(equipment_id=2)]:
        assert client.post("/bookings", json=booking).status_code == 201


def test_invalid_inputs_and_missing_equipment(client):
    assert client.post("/bookings", json=payload(1, 0)).status_code == 422
    assert client.post("/bookings", json=payload(0, 0)).status_code == 422
    assert client.post("/bookings", json=payload(-500, -499)).status_code == 422
    assert client.post("/bookings", json=payload(equipment_id=999)).status_code == 404
    assert client.post("/bookings", json={**payload(), "student_name": "   "}).status_code == 422
    naive = payload()
    naive["start_at"] = naive["start_at"].replace("+00:00", "")
    assert client.post("/bookings", json=naive).status_code == 422


def test_equivalent_timezone_offsets_conflict(client):
    booking = payload()
    assert client.post("/bookings", json=booking).status_code == 201
    for field in ["start_at", "end_at"]:
        booking[field] = datetime.fromisoformat(booking[field]).astimezone(timezone(timedelta(hours=5, minutes=30))).isoformat()
    assert client.post("/bookings", json=booking).status_code == 409


def test_simultaneous_requests_only_create_one_reservation(client):
    barrier = Barrier(4)
    booking = payload()

    def reserve(_):
        barrier.wait(timeout=10)
        return client.post("/bookings", json=booking).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(reserve, range(4)))
    assert sorted(statuses) == [201, 409, 409, 409]


def test_data_survives_restart_and_can_be_filtered(tmp_path):
    path = tmp_path / "persist.db"
    with TestClient(create_app(path)) as first:
        assert first.post("/bookings", json=payload()).status_code == 201
        assert first.post("/bookings", json=payload(equipment_id=2)).status_code == 201
    with TestClient(create_app(path)) as second:
        assert len(second.get("/equipment").json()) == 3
        rows = second.get("/bookings?equipment_id=2&limit=1").json()
        assert len(rows) == 1 and rows[0]["equipment_id"] == 2
        assert len(second.get("/bookings").json()) == 2
