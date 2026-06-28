# app/middleware/__init__.py
"""
Agent Ochuko — FastAPI Middleware Stack.

Registration order in main.py (last registered = first executed):
  1. AuditLogMiddleware      (last to register → runs after all others)
  2. QuotaGuardMiddleware    (agent endpoint quota enforcement)
  3. TokenBudgetMiddleware   (chat endpoint budget enforcement)
  4. BlockGuardMiddleware    (blocked identity check)
  5. MaintenanceGuardMiddleware (global kill switch)
  ↑ JWTValidatorMiddleware is a FastAPI Depends, not middleware

Execution order on each request:
  MaintenanceGuard → BlockGuard → TokenBudget → QuotaGuard → AuditLog → Handler
"""

from app.middleware.maintenance_guard import MaintenanceGuardMiddleware
from app.middleware.block_guard import BlockGuardMiddleware
from app.middleware.token_budget import TokenBudgetMiddleware
from app.middleware.quota_guard import QuotaGuardMiddleware
from app.middleware.audit_logger import AuditLogMiddleware

__all__ = [
    "MaintenanceGuardMiddleware",
    "BlockGuardMiddleware",
    "TokenBudgetMiddleware",
    "QuotaGuardMiddleware",
    "AuditLogMiddleware",
]
