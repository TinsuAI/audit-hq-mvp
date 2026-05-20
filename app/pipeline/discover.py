"""Auto-discover canonical BCQT files for a given company × year."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DiscoveredFiles:
    m15: Path | None
    m15a: Path | None
    m16: Path | None
    bcct: Path | None


# Lower index = higher priority. Files matching ignore patterns are dropped.
_DRAFT_HINTS = ("draft", "check lại", "check_", " - check", "fn", "(1)", "(2)", "old", "cu", "(nk")
_DUP_HINTS = ("__dup", "__rec")


def _is_draft(name: str) -> bool:
    lower = name.lower()
    return any(h in lower for h in _DRAFT_HINTS) or any(h in name for h in _DUP_HINTS)


def _pick_best(candidates: list[Path]) -> Path | None:
    if not candidates:
        return None
    primary = [c for c in candidates if not _is_draft(c.name)]
    pool = primary or candidates
    # Prefer .xlsx over .xls when both present, otherwise newest mtime.
    return max(pool, key=lambda p: (p.suffix.lower() == ".xlsx", p.stat().st_mtime))


def discover(company: str, year: int, raw_root: Path) -> DiscoveredFiles:
    """Find one canonical file per category under raw_root/<company>/<year>/."""
    base = raw_root / company / str(year)
    if not base.exists():
        raise FileNotFoundError(f"Không thấy thư mục dữ liệu: {base}")

    m15_candidates: list[Path] = []
    m15a_candidates: list[Path] = []
    m16_candidates: list[Path] = []
    bcct_candidates: list[Path] = []

    bcqt_dir = base / "BCQT"
    if bcqt_dir.exists():
        for p in bcqt_dir.iterdir():
            if not p.is_file() or p.suffix.lower() not in {".xls", ".xlsx"}:
                continue
            name = p.name.lower()
            if "_nvl" in name.replace(" ", "_") or "nvl " in name or "_npl" in name.replace(" ", "_"):
                m15_candidates.append(p)
            elif "_sp" in name.replace(" ", "_") or " sp " in f" {name} ":
                m15a_candidates.append(p)
            else:
                # Older mẫu cũ (TT38) — may contain both; skip for MVP
                continue

    dm_dir = base / "DINH_MUC"
    if dm_dir.exists():
        # Prefer BCDM_TT39_* (mẫu 16 chính); fallback DINHMUC_*.xlsx
        tt39 = [p for p in dm_dir.iterdir() if p.is_file() and p.name.lower().startswith("bcdm_tt39")]
        if tt39:
            m16_candidates.extend(tt39)
        else:
            m16_candidates.extend(
                p for p in dm_dir.iterdir()
                if p.is_file() and p.suffix.lower() in {".xls", ".xlsx"}
            )

    hct_dir = base / "HANG_CHI_TIET"
    if hct_dir.exists():
        bcct_candidates.extend(
            p for p in hct_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".xls", ".xlsx"}
        )

    return DiscoveredFiles(
        m15=_pick_best(m15_candidates),
        m15a=_pick_best(m15a_candidates),
        m16=_pick_best(m16_candidates),
        bcct=_pick_best(bcct_candidates),
    )
