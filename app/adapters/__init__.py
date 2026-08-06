from app.adapters.bcct import BcctFile, BcctRow
from app.adapters.bcct import parse_bcct as _parse_bcct
from app.adapters.m15 import M15File, M15Row
from app.adapters.m15 import parse_m15 as _parse_m15
from app.adapters.m15a import M15aFile, M15aRow
from app.adapters.m15a import parse_m15a as _parse_m15a
from app.adapters.m16 import M16File, M16Row
from app.adapters.m16 import parse_m16 as _parse_m16
from app.adapters.parse_cache import memoize_parse, parse_cache

# Bản có nhớ: trong `with parse_cache()` (một lượt nạp) mỗi file chỉ mở một lần.
# Import thẳng từ `app.adapters.m15` v.v. vẫn được bản không nhớ.
parse_bcct = memoize_parse(_parse_bcct)
parse_m15 = memoize_parse(_parse_m15)
parse_m15a = memoize_parse(_parse_m15a)
parse_m16 = memoize_parse(_parse_m16)

__all__ = [
    "BcctFile",
    "BcctRow",
    "M15File",
    "M15Row",
    "M15aFile",
    "M15aRow",
    "M16File",
    "M16Row",
    "parse_bcct",
    "parse_cache",
    "parse_m15",
    "parse_m15a",
    "parse_m16",
]
