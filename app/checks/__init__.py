from app.checks.c1_quantity import CHECKS as C1_CHECKS
from app.checks.c2_balance import CHECKS as C2_CHECKS

ALL_CHECKS = {**C1_CHECKS, **C2_CHECKS}

__all__ = ["ALL_CHECKS", "C1_CHECKS", "C2_CHECKS"]
