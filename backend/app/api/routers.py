"""API routers, included by app.main."""

from app.api.account import router as account_router
from app.api.applications import router as applications_router
from app.api.cycle import router as cycle_router
from app.api.me import router as me_router
from app.api.review import router as review_router
from app.api.scans import router as scans_router

all_routers = [me_router, cycle_router, scans_router, applications_router, review_router, account_router]
