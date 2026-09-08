"""Local operator commands. No default passwords or public admin registration."""
import argparse
from getpass import getpass
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.database import make_engine, migrate, transaction
from app.models import users
from app.schemas import Registration
from app.security import now, passwords


def main():
    parser = argparse.ArgumentParser(description='Campus booking administration')
    parser.add_argument('command', choices=['migrate', 'create-admin', 'promote'])
    parser.add_argument('--email')
    args = parser.parse_args()
    engine = make_engine()
    try:
        migrate(engine)
        if args.command == 'migrate':
            print('Database is up to date.')
            return
        email = (args.email or input('Email: ')).strip().lower()
        if args.command == 'promote':
            with transaction(engine, write=True) as db:
                user = db.execute(select(users).where(users.c.email == email)).mappings().first()
                if not user:
                    raise ValueError('No account has that email. Register through the app first.')
                db.execute(update(users).where(users.c.id == user['id']).values(role='admin'))
            print('Administrator access enabled. Refresh the application.')
            return
        name = input('Display name: ').strip()
        password = getpass('Password (at least 12 characters): ')
        if password != getpass('Confirm password: '):
            raise ValueError('Passwords do not match.')
        data = Registration(name=name, email=email, password=password)
        with transaction(engine, write=True) as db:
            db.execute(users.insert().values(name=data.name, email=str(data.email),
                password_hash=passwords.hash(data.password), role='admin', created_at=now()))
        print('Administrator created. Sign in through the application.')
    except IntegrityError:
        parser.exit(1, 'That email already exists. Use promote to grant administrator access.\n')
    except ValueError:
        # Do not print Pydantic validation dumps: they may contain the entered password.
        parser.exit(1, 'Could not complete the command. Check the account details and password length.\n')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
