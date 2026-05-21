from app.checks.c1_quantity import CHECKS as C1_CHECKS
from app.checks.c2_balance import CHECKS as C2_CHECKS
from app.checks.c3_classify import CHECKS as C3_CHECKS
from app.checks.c4_norm import CHECKS as C4_CHECKS
from app.checks.c5_trace import CHECKS as C5_CHECKS
from app.checks.c6_cross_period import CHECKS as C6_CHECKS

ALL_CHECKS = {**C1_CHECKS, **C2_CHECKS, **C3_CHECKS, **C4_CHECKS, **C5_CHECKS, **C6_CHECKS}

__all__ = [
    "ALL_CHECKS",
    "C1_CHECKS",
    "C2_CHECKS",
    "C3_CHECKS",
    "C4_CHECKS",
    "C5_CHECKS",
    "C6_CHECKS",
]
