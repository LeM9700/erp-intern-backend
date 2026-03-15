from slowapi import Limiter
from slowapi.util import get_remote_address

# Single shared instance — imported by main.py (app.state.limiter) and api/auth.py (@limiter.limit)
limiter = Limiter(key_func=get_remote_address)
