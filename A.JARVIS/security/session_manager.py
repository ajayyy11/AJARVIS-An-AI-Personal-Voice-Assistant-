# security/session_manager.py

from flask import session
import datetime
from config import Config

def grant_access(username):
    session['user'] = username
    session['login_time'] = datetime.datetime.now().isoformat()

def revoke_access():
    session.pop('user', None)
    session.pop('login_time', None)

def is_authenticated():
    if 'user' not in session:
        return False

    # Session timeout check
    login_time_str = session.get('login_time')
    if login_time_str:
        login_time = datetime.datetime.fromisoformat(login_time_str)
        elapsed = (datetime.datetime.now() - login_time).total_seconds() / 60
        if elapsed > Config.SESSION_TIMEOUT_MINUTES:
            revoke_access()
            return False

    return True