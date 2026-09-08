"""Campus Equipment Booking: authenticated API and same-origin web application."""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AwareDatetime, ValidationError
from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.database import ROOT, make_engine, migrate, transaction
from app.models import bookings, equipment, sessions, users
from app.schemas import AuthResponse, Booking, BookingPage, BookingRequest, Equipment, EquipmentInput, Interval, Login, Registration, utc
from app.security import COOKIE, DUMMY_HASH, current_user, digest, issue_session, now, passwords, require_admin, set_cookie, throttle

Identity = Annotated[dict, Depends(current_user)]


def booking_query():
    return select(bookings, equipment.c.name.label('equipment_name'), equipment.c.location).join(equipment)


def seed_equipment(engine):
    samples = [
        ('Oscilloscope 01', 'Electronics Lab', 'Electronics', 'Inspect waveforms and debug circuits. Two-channel bench instrument for lab and project work.'),
        ('Arduino Kit 01', 'Project Lab', 'Electronics', 'A development board with a breadboard, jumper wires, and a selection of common sensors.'),
        ('Projector 01', 'Seminar Room', 'Presentation', 'Present your project, lead a workshop, or run a team review. HDMI connection available.'),
        ('Raspberry Pi Kit', 'Project Lab', 'Computing', 'Single-board computer with a power supply and microSD card for software and IoT projects.'),
        ('Digital Multimeter', 'Electronics Lab', 'Electronics', 'Measure voltage, current, and resistance for circuit troubleshooting and lab experiments.'),
        ('Soldering Station', 'Fabrication Lab', 'Fabrication', 'Temperature-controlled station for assembling and repairing electronic prototypes.'),
    ]
    with transaction(engine, write=True) as db:
        # PostgreSQL startup seeding is serialized across workers as well.
        if engine.dialect.name == 'postgresql':
            db.exec_driver_sql('LOCK TABLE equipment IN SHARE ROW EXCLUSIVE MODE')
        if db.execute(select(func.count()).select_from(equipment)).scalar_one() == 0:
            db.execute(equipment.insert(), [dict(name=n, location=l, category=c, description=d, active=True) for n,l,c,d in samples])


def create_app(db_path: Path | None = None, *, url: str | None = None, secure_cookies: bool | None = None):
    engine = make_engine('sqlite:///' + db_path.resolve().as_posix() if db_path else url)
    secure = os.getenv('COOKIE_SECURE', 'false').lower() == 'true' if secure_cookies is None else secure_cookies

    @asynccontextmanager
    async def lifespan(app):
        if os.getenv('AUTO_MIGRATE', 'true').lower() == 'true':
            migrate(engine)
        seed_equipment(engine)
        yield
        engine.dispose()

    app = FastAPI(title='Campus Equipment Booking', version='1.0.0', lifespan=lifespan,
        description='Equipment reservations with account ownership, cancellation, availability, and administrator controls. '
        'Sign in through the web interface or /auth/login. Protected writes require the returned csrf_token in X-CSRF-Token.')
    app.state.engine = engine
    allowed_hosts = [host.strip() for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    @app.middleware('http')
    async def browser_security(request, call_next):
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('origin')
            expected = str(request.base_url).rstrip('/')
            configured = os.getenv('APP_ORIGIN', '').rstrip('/')
            if origin and origin not in {expected, configured}:
                return JSONResponse({'detail': 'Cross-origin request rejected'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        if request.url.path not in {'/docs', '/redoc', '/docs/oauth2-redirect'}:
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if not request.url.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(OperationalError)
    async def database_busy(request, error):
        import logging
        logging.getLogger(__name__).warning('Database operation unavailable: %s', type(error.orig).__name__)
        return JSONResponse({'detail': 'The database is busy or unavailable. Please retry shortly.'}, 503, headers={'Retry-After': '2'})

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(ROOT / 'app/static/index.html')

    @app.get('/health', tags=['System'])
    def health():
        with transaction(engine) as db:
            db.execute(select(1))
        return {'status': 'ok', 'version': '1.0.0'}

    @app.post('/auth/register', response_model=AuthResponse, status_code=201, tags=['Accounts'])
    def register(payload: Registration, request: Request, response: Response):
        throttle(request, 'register', 10)
        hashed = passwords.hash(payload.password)
        try:
            with transaction(engine, write=True) as db:
                user = db.execute(users.insert().values(name=payload.name, email=str(payload.email),
                    password_hash=hashed, role='student', created_at=now()).returning(users)).mappings().one()
                if request.cookies.get(COOKIE):
                    db.execute(delete(sessions).where(sessions.c.token_hash == digest(request.cookies[COOKIE])))
                token, csrf = issue_session(db, user['id'])
        except IntegrityError:
            raise HTTPException(409, 'An account already uses this email. Please sign in instead')
        set_cookie(response, token, secure)
        return {'user': dict(user), 'csrf_token': csrf}

    @app.post('/auth/login', response_model=AuthResponse, tags=['Accounts'])
    def login(payload: Login, request: Request, response: Response):
        throttle(request, 'login', 30)
        with transaction(engine) as db:
            user = db.execute(select(users).where(users.c.email == str(payload.email))).mappings().first()
        valid = passwords.verify(payload.password, user['password_hash'] if user else DUMMY_HASH)
        if not user or not valid:
            raise HTTPException(401, 'Email or password is incorrect')
        with transaction(engine, write=True) as db:
            if request.cookies.get(COOKIE):
                db.execute(delete(sessions).where(sessions.c.token_hash == digest(request.cookies[COOKIE])))
            token, csrf = issue_session(db, user['id'])
        set_cookie(response, token, secure)
        return {'user': dict(user), 'csrf_token': csrf}

    @app.get('/auth/me', response_model=AuthResponse, tags=['Accounts'])
    def me(user: Identity):
        return {'user': user, 'csrf_token': user['csrf_token']}

    @app.post('/auth/logout', status_code=204, tags=['Accounts'])
    def logout(request: Request, user: Identity):
        with transaction(engine, write=True) as db:
            db.execute(delete(sessions).where(sessions.c.token_hash == digest(request.cookies[COOKIE])))
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, path='/', secure=secure, httponly=True, samesite='strict')
        return response

    @app.get('/equipment', response_model=list[Equipment], tags=['Equipment'])
    def list_equipment(q: str = Query('', max_length=100), category: str = Query('', max_length=40),
            start_at: AwareDatetime | None = None, end_at: AwareDatetime | None = None,
            limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), available_only: bool = False):
        query = select(equipment).where(equipment.c.active.is_(True))
        if q.strip():
            term = q.strip()
            query = query.where(or_(equipment.c.name.icontains(term, autoescape=True), equipment.c.location.icontains(term, autoescape=True)))
        if category:
            query = query.where(equipment.c.category == category)
        if (start_at is None) != (end_at is None):
            raise HTTPException(422, 'Provide both start_at and end_at')
        if start_at is not None:
            try:
                interval = Interval(start_at=start_at, end_at=end_at)
            except ValidationError as error:
                raise HTTPException(422, error.errors()[0]['msg'])
            conflict = exists(select(bookings.c.id).where(bookings.c.equipment_id == equipment.c.id,
                bookings.c.status == 'confirmed', bookings.c.start_at < interval.end_at, bookings.c.end_at > interval.start_at))
            query = query.add_columns((~conflict).label('available'))
            if available_only:
                query = query.where(~conflict)
        with transaction(engine) as db:
            return [dict(row) for row in db.execute(query.order_by(equipment.c.id).limit(limit).offset(offset)).mappings()]

    @app.get('/equipment/{equipment_id}/schedule', tags=['Equipment'])
    def schedule(equipment_id: int, start_at: AwareDatetime, end_at: AwareDatetime):
        start_at, end_at = utc(start_at), utc(end_at)
        if end_at <= start_at or end_at - start_at > timedelta(days=7):
            raise HTTPException(422, 'Choose an interval of up to seven days')
        with transaction(engine) as db:
            if not db.execute(select(equipment.c.id).where(equipment.c.id == equipment_id, equipment.c.active.is_(True))).first():
                raise HTTPException(404, 'Equipment not found')
            rows = db.execute(select(bookings.c.start_at, bookings.c.end_at).where(
                bookings.c.equipment_id == equipment_id, bookings.c.status == 'confirmed',
                bookings.c.start_at < end_at, bookings.c.end_at > start_at).order_by(bookings.c.start_at)).mappings()
            # Public availability reveals times only, never student names or booking IDs.
            return [{'start_at': utc(row['start_at']), 'end_at': utc(row['end_at'])} for row in rows]

    @app.post('/bookings', response_model=Booking, status_code=201, tags=['Reservations'])
    def create_booking(payload: BookingRequest, user: Identity):
        try:
            with transaction(engine, write=True) as db:
                item = db.execute(select(equipment).where(equipment.c.id == payload.equipment_id).with_for_update()).mappings().first()
                if not item:
                    raise HTTPException(404, 'Equipment not found')
                if not item['active']:
                    raise HTTPException(409, 'This item is currently unavailable for reservations')
                if payload.start_at <= now():
                    raise HTTPException(422, 'Start time must be in the future')
                conflict = db.execute(select(bookings.c.id).where(bookings.c.equipment_id == payload.equipment_id,
                    bookings.c.status == 'confirmed', bookings.c.start_at < payload.end_at, bookings.c.end_at > payload.start_at).limit(1)).first()
                if conflict:
                    raise HTTPException(409, 'This item is already reserved during that time. Choose another slot')
                identifier = db.execute(bookings.insert().values(**payload.model_dump(), user_id=user['id'],
                    student_name=user['name'], status='confirmed', created_at=now()).returning(bookings.c.id)).scalar_one()
                return dict(db.execute(booking_query().where(bookings.c.id == identifier)).mappings().one())
        except IntegrityError as error:
            if getattr(error.orig, 'sqlstate', None) == '23P01':
                raise HTTPException(409, 'This item is already reserved during that time. Choose another slot')
            raise

    @app.get('/bookings', response_model=BookingPage, tags=['Reservations'])
    def list_bookings(user: Identity, view: Literal['upcoming', 'past', 'cancelled', 'all'] = 'upcoming',
            equipment_id: int | None = Query(None, gt=0), all_users: bool = False,
            limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
        clauses = []
        if all_users:
            require_admin(user)
        else:
            clauses.append(bookings.c.user_id == user['id'])
        if equipment_id:
            clauses.append(bookings.c.equipment_id == equipment_id)
        if view == 'upcoming':
            clauses.extend([bookings.c.status == 'confirmed', bookings.c.end_at > now()])
        elif view == 'past':
            clauses.extend([bookings.c.status == 'confirmed', bookings.c.end_at <= now()])
        elif view == 'cancelled':
            clauses.append(bookings.c.status == 'cancelled')
        order = bookings.c.start_at.asc() if view == 'upcoming' else bookings.c.start_at.desc()
        with transaction(engine) as db:
            total = db.execute(select(func.count()).select_from(bookings).where(*clauses)).scalar_one()
            rows = db.execute(booking_query().where(*clauses).order_by(order, bookings.c.id).limit(limit).offset(offset)).mappings()
            return {'items': [dict(row) for row in rows], 'total': total, 'limit': limit, 'offset': offset}

    @app.get('/bookings/{booking_id}', response_model=Booking, tags=['Reservations'])
    def get_booking(booking_id: int, user: Identity):
        with transaction(engine) as db:
            row = db.execute(booking_query().where(bookings.c.id == booking_id)).mappings().first()
            if not row or (row['user_id'] != user['id'] and user['role'] != 'admin'):
                raise HTTPException(404, 'Booking not found')
            return dict(row)

    @app.post('/bookings/{booking_id}/cancel', response_model=Booking, tags=['Reservations'])
    def cancel_booking(booking_id: int, user: Identity):
        with transaction(engine, write=True) as db:
            row = db.execute(select(bookings).where(bookings.c.id == booking_id).with_for_update()).mappings().first()
            if not row or (row['user_id'] != user['id'] and user['role'] != 'admin'):
                raise HTTPException(404, 'Booking not found')
            if row['status'] != 'cancelled':
                if utc(row['start_at']) <= now() and user['role'] != 'admin':
                    raise HTTPException(409, 'A reservation can only be cancelled before it starts')
                db.execute(update(bookings).where(bookings.c.id == booking_id).values(status='cancelled'))
            return dict(db.execute(booking_query().where(bookings.c.id == booking_id)).mappings().one())

    @app.get('/admin/equipment', response_model=list[Equipment], tags=['Administration'])
    def admin_equipment(user: Identity):
        require_admin(user)
        with transaction(engine) as db:
            return [dict(row) for row in db.execute(select(equipment).order_by(equipment.c.id)).mappings()]

    @app.post('/admin/equipment', response_model=Equipment, status_code=201, tags=['Administration'])
    def add_equipment(payload: EquipmentInput, user: Identity):
        require_admin(user)
        with transaction(engine, write=True) as db:
            return dict(db.execute(equipment.insert().values(**payload.model_dump()).returning(equipment)).mappings().one())

    @app.put('/admin/equipment/{equipment_id}', response_model=Equipment, tags=['Administration'])
    def edit_equipment(equipment_id: int, payload: EquipmentInput, user: Identity):
        require_admin(user)
        with transaction(engine, write=True) as db:
            item = db.execute(select(equipment).where(equipment.c.id == equipment_id).with_for_update()).mappings().first()
            if not item:
                raise HTTPException(404, 'Equipment not found')
            if not payload.active and item['active']:
                pending = db.execute(select(bookings.c.id).where(bookings.c.equipment_id == equipment_id,
                    bookings.c.status == 'confirmed', bookings.c.end_at > now()).limit(1)).first()
                if pending:
                    raise HTTPException(409, 'Cancel this item’s upcoming reservations before taking it offline')
            return dict(db.execute(update(equipment).where(equipment.c.id == equipment_id)
                .values(**payload.model_dump()).returning(equipment)).mappings().one())

    app.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')
    return app


app = create_app()
