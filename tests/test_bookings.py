"""Behavioral API tests. Every test owns an isolated database and account."""
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError

from app.database import make_engine, transaction
from app.main import create_app
from app.models import auth_attempts, bookings, sessions, users
from app.security import COOKIE, digest, now

PASSWORD = 'Demo-Test-Password-42'


@pytest.fixture
def application(tmp_path):
    postgres_url = os.getenv('TEST_DATABASE_URL')
    if postgres_url:
        # Tests are serial; a unique schema prevents touching existing application data.
        engine = make_engine(postgres_url)
        schema = 'test_' + uuid4().hex
        with engine.begin() as db:
            db.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
            db.execute(text(f'CREATE SCHEMA {schema}'))
        separator = '&' if '?' in postgres_url else '?'
        url = postgres_url + separator + 'options=-csearch_path%3D' + schema + ',public'
        app = create_app(url=url)
        yield app
        app.state.engine.dispose()
        with engine.begin() as db:
            db.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        engine.dispose()
    else:
        yield create_app(tmp_path / 'test.db')


def register(client, email='student@example.com'):
    result = client.post('/auth/register', json={'name':'Demo Student','email':email,'password':PASSWORD})
    assert result.status_code == 201, result.text
    client.headers['X-CSRF-Token'] = result.json()['csrf_token']
    return result.json()['user']


@pytest.fixture
def client(application):
    with TestClient(application) as client:
        register(client)
        yield client


def payload(start=0, end=1, equipment_id=1):
    base = datetime.now(timezone.utc).replace(hour=10,minute=0,second=0,microsecond=0)+timedelta(days=7)
    return {'equipment_id':equipment_id,'purpose':'Lab project',
            'start_at':(base+timedelta(hours=start)).isoformat(),
            'end_at':(base+timedelta(hours=end)).isoformat()}


def make_booking(client, **kwargs):
    response=client.post('/bookings',json=payload(**kwargs))
    assert response.status_code==201,response.text
    return response.json()


@pytest.mark.parametrize('start,end',[(0,1),(-1,.5),(.5,2),(-1,2),(.2,.8)])
def test_overlapping_reservations_are_rejected(client,start,end):
    make_booking(client)
    assert client.post('/bookings',json=payload(start,end)).status_code==409
    assert client.get('/bookings').json()['total']==1


def test_adjacent_and_different_items_are_allowed(client):
    for booking in [payload(),payload(1,2),payload(-1,0),payload(equipment_id=2)]:
        assert client.post('/bookings',json=booking).status_code==201


@pytest.mark.parametrize('changes',[
    {'equipment_id':-1}, {'student_name':'Forged identity'}, {'user_id':999},
    {'purpose':'x'*241}, {'start_at':'2020-01-01T00:00:00Z'},
    {'start_at':'2030-01-01T10:00:00'},
])
def test_invalid_or_forged_booking_input_is_rejected(client,changes):
    assert client.post('/bookings',json={**payload(),**changes}).status_code==422


def test_bad_intervals_and_unknown_equipment(client):
    for request in [payload(1,0),payload(0,0),payload(0,25)]:
        assert client.post('/bookings',json=request).status_code==422
    assert client.post('/bookings',json=payload(equipment_id=9999)).status_code==404


def test_timezone_equivalence(client):
    booking=payload();make_booking(client)
    for key in ['start_at','end_at']:
        booking[key]=datetime.fromisoformat(booking[key]).astimezone(timezone(timedelta(hours=5,minutes=30))).isoformat()
    assert client.post('/bookings',json=booking).status_code==409


def test_four_concurrent_requests_create_exactly_one_booking(client):
    barrier=Barrier(4);request=payload()
    def reserve(_):
        barrier.wait(timeout=10)
        return client.post('/bookings',json=request).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        result=list(pool.map(reserve,range(4)))
    assert sorted(result)==[201,409,409,409]


def test_authentication_required(application):
    with TestClient(application) as anonymous:
        assert anonymous.get('/equipment').status_code==200
        assert anonymous.get('/bookings').status_code==401
        assert anonymous.post('/bookings',json=payload()).status_code==401
        assert anonymous.get('/admin/equipment').status_code==401


def test_identity_is_derived_from_session(client):
    booking=make_booking(client)
    assert booking['student_name']=='Demo Student'
    assert booking['user_id']==client.get('/auth/me').json()['user']['id']
    assert client.get(f"/bookings/{booking['id']}").json()['id']==booking['id']


def test_other_users_cannot_read_or_cancel(client,application):
    booking=make_booking(client)
    with TestClient(application) as other:
        register(other,'other@example.com')
        assert other.get('/bookings?view=all').json()['total']==0
        assert other.get(f"/bookings/{booking['id']}").status_code==404
        assert other.post(f"/bookings/{booking['id']}/cancel").status_code==404
        assert other.get('/bookings?all_users=true').status_code==403
        assert other.get('/admin/equipment').status_code==403
        assert other.post('/admin/equipment',json=equipment_payload()).status_code==403


def equipment_payload(**changes):
    return {'name':'Test kit','location':'Project Lab','category':'Electronics','description':'Demo equipment','active':True,**changes}


def promote(client):
    user_id=client.get('/auth/me').json()['user']['id']
    with transaction(client.app.state.engine,write=True) as db:
        db.execute(update(users).where(users.c.id==user_id).values(role='admin'))


def test_cancel_is_idempotent_and_releases_availability(client):
    booking=make_booking(client)
    interval=payload();query={k:interval[k] for k in ['start_at','end_at']}
    before=client.get('/equipment',params=query).json()
    assert next(item for item in before if item['id']==1)['available'] is False
    for _ in range(2):
        result=client.post(f"/bookings/{booking['id']}/cancel")
        assert result.status_code==200
        assert result.json()['status']=='cancelled'
    assert client.get('/bookings?view=cancelled').json()['total']==1
    assert client.get('/bookings').json()['total']==0
    assert next(item for item in client.get('/equipment',params=query).json() if item['id']==1)['available'] is True
    make_booking(client)


def test_started_booking_cannot_be_cancelled_by_student(client):
    booking=make_booking(client)
    with transaction(client.app.state.engine,write=True) as db:
        db.execute(update(bookings).where(bookings.c.id==booking['id']).values(start_at=now()-timedelta(hours=1)))
    assert client.post(f"/bookings/{booking['id']}/cancel").status_code==409
    promote(client)
    assert client.post(f"/bookings/{booking['id']}/cancel").status_code==200


def test_admin_management_and_offline_equipment(client):
    promote(client)
    result=client.post('/admin/equipment',json=equipment_payload())
    assert result.status_code==201
    identifier=result.json()['id']
    booking=make_booking(client,equipment_id=identifier)
    offline=equipment_payload(active=False)
    assert client.put(f'/admin/equipment/{identifier}',json=offline).status_code==409
    assert client.post(f"/bookings/{booking['id']}/cancel").status_code==200
    assert client.put(f'/admin/equipment/{identifier}',json=offline).status_code==200
    assert not any(item['id']==identifier for item in client.get('/equipment').json())
    assert client.post('/bookings',json=payload(equipment_id=identifier)).status_code==409
    assert client.put(f'/admin/equipment/{identifier}',json=equipment_payload()).status_code==200
    make_booking(client,equipment_id=identifier)
    assert client.get('/bookings?all_users=true').json()['total']==1


def test_csrf_origin_and_logout(client):
    csrf=client.headers.pop('X-CSRF-Token')
    assert client.post('/bookings',json=payload()).status_code==403
    client.headers['X-CSRF-Token']='incorrect'
    assert client.post('/bookings',json=payload()).status_code==403
    client.headers['X-CSRF-Token']=csrf
    assert client.post('/bookings',json=payload(),headers={'Origin':'https://evil.example'}).status_code==403
    token=client.cookies.get(COOKIE)
    assert client.post('/auth/logout').status_code==204
    assert client.get('/auth/me').status_code==401
    client.cookies.set(COOKIE,token)
    assert client.get('/auth/me').status_code==401


def test_registration_login_password_storage_and_cookie_flags(application):
    with TestClient(application) as client:
        register(client,'Student@Example.com')
        assert client.get('/auth/me').json()['user']['email']=='student@example.com'
        with transaction(application.state.engine) as db:
            user=db.execute(select(users)).mappings().one()
            assert user['password_hash'].startswith('$argon2id$')
            assert user['password_hash']!=PASSWORD
            session=db.execute(select(sessions)).mappings().one()
            assert session['token_hash']==digest(client.cookies.get(COOKIE))
        duplicate=client.post('/auth/register',json={'name':'X','email':'student@example.com','password':PASSWORD})
        assert duplicate.status_code==409
        assert client.post('/auth/register',json={'name':'X','email':'new@example.com','password':'short'}).status_code==422
        assert client.post('/auth/login',json={'email':'student@example.com','password':'incorrect'}).status_code==401
        result=client.post('/auth/login',json={'email':'student@example.com','password':PASSWORD})
        assert result.status_code==200
        assert 'password_hash' not in result.text
        cookie=result.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=strict' in cookie


def test_expired_session_rejected(client):
    with transaction(client.app.state.engine,write=True) as db:
        db.execute(update(sessions).values(expires_at=now()-timedelta(seconds=1)))
    assert client.get('/auth/me').status_code==401


def test_login_throttling_persists(client):
    result=client.post('/auth/login',json={'email':'student@example.com','password':'wrong'})
    assert result.status_code==401
    with transaction(client.app.state.engine,write=True) as db:
        db.execute(update(auth_attempts).where(auth_attempts.c.key.like('login:%')).values(count=30))
    result=client.post('/auth/login',json={'email':'student@example.com','password':PASSWORD})
    assert result.status_code==429
    assert int(result.headers['retry-after'])>0


def test_availability_search_and_public_schedule_privacy(client):
    booking=make_booking(client)
    params={k:v for k,v in payload().items() if k in ['start_at','end_at']}
    result=client.get('/equipment',params={**params,'q':'oscillo','category':'Electronics'})
    assert len(result.json())==1 and result.json()[0]['available'] is False
    schedule=client.get('/equipment/1/schedule',params=params).json()
    assert set(schedule[0])=={'start_at','end_at'}
    assert 'student_name' not in str(schedule)
    assert client.get('/equipment',params={'start_at':params['start_at']}).status_code==422
    assert client.get('/equipment',params={**params,'end_at':params['start_at']}).status_code==422
    assert client.get('/equipment',params={'q':"%' OR 1=1 --"}).json()==[]


def test_filtering_and_pagination(client):
    make_booking(client)
    make_booking(client,start=1,end=2)
    make_booking(client,equipment_id=2)
    result=client.get('/bookings?equipment_id=1&limit=1&offset=1').json()
    assert result['total']==2 and len(result['items'])==1
    assert result['items'][0]['equipment_id']==1


def test_frontend_assets_and_headers(client):
    response=client.get('/')
    assert response.status_code==200 and 'Equipment library' in response.text
    assert response.headers['x-content-type-options']=='nosniff'
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert client.get('/static/app.js').status_code==200
    assert client.get('/static/styles.css').status_code==200
    assert client.get('/health').json()['status']=='ok'
    assert client.get('/openapi.json').status_code==200


def test_database_survives_restart(client,application):
    booking=make_booking(client)
    token=client.cookies.get(COOKIE)
    with TestClient(application) as restarted:
        restarted.cookies.set(COOKIE,token)
        assert restarted.get(f"/bookings/{booking['id']}").status_code==200
        assert len(restarted.get('/equipment').json())==6


def test_legacy_sqlite_migration_preserves_data(tmp_path):
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE equipment(id INTEGER PRIMARY KEY,name TEXT NOT NULL,location TEXT NOT NULL);'
            'CREATE TABLE bookings(id INTEGER PRIMARY KEY,equipment_id INTEGER NOT NULL REFERENCES equipment(id),'
            'student_name TEXT NOT NULL,start_at TEXT NOT NULL,end_at TEXT NOT NULL,CHECK(start_at<end_at));'
            "INSERT INTO equipment VALUES(1,'Old scope','Original Lab');")
        request=payload()
        db.execute('INSERT INTO bookings VALUES(7,1,?,?,?)',('Legacy Student',request['start_at'],request['end_at']))
    with TestClient(create_app(path)) as client:
        register(client)
        assert client.get('/bookings?view=all').json()['total']==0
        assert client.post('/bookings',json=payload()).status_code==409
        promote(client)
        row=client.get('/bookings/7').json()
        assert row['student_name']=='Legacy Student' and row['user_id'] is None
        assert row['equipment_name']=='Old scope'
        assert path.with_name('legacy.pre-v1.db').exists()
        assert client.post('/bookings/7/cancel').status_code==200
        assert make_booking(client)['id']>7


def test_postgres_constraint_rejects_direct_overlapping_insert(client):
    if client.app.state.engine.dialect.name!='postgresql':
        pytest.skip('PostgreSQL exclusion constraint is tested in the PostgreSQL CI job')
    booking=make_booking(client)
    with pytest.raises(IntegrityError):
        with transaction(client.app.state.engine,write=True) as db:
            request=payload()
            db.execute(bookings.insert().values(equipment_id=1,user_id=booking['user_id'],student_name='Demo',purpose='',
                start_at=datetime.fromisoformat(request['start_at']),end_at=datetime.fromisoformat(request['end_at']),
                status='confirmed',created_at=now()))


def test_secure_cookie_setting(tmp_path):
    with TestClient(create_app(tmp_path/'secure.db',secure_cookies=True),base_url='https://testserver') as client:
        result=client.post('/auth/register',json={'name':'Demo','email':'secure@example.com','password':PASSWORD})
        assert result.status_code==201
        assert 'secure' in result.headers['set-cookie'].lower()
        assert client.get('/auth/me').status_code==200


def test_catalog_pagination_and_available_only(client):
    make_booking(client)
    params={k:v for k,v in payload().items() if k in ['start_at','end_at']}
    assert len(client.get('/equipment',params={**params,'available_only':True}).json())==5
    first=client.get('/equipment',params={'limit':2,'offset':0}).json()
    second=client.get('/equipment',params={'limit':2,'offset':2}).json()
    assert len(first)==len(second)==2
    assert not ({item['id'] for item in first}&{item['id'] for item in second})
