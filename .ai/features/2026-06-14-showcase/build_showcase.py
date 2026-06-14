"""Dựng trang showcase tính năng (self-contained HTML, ảnh nhúng base64).

Tự lập (reproducible) từ ảnh PNG đã commit ở screenshots/ (chụp bằng ui_smoke.py —
retina, crop gọn, ẩn banner): nén PNG → JPEG (ImageMagick `convert`), nhúng base64
vào template, ghi ra app/static/showcase.html. Route public `/showcase` (app/main.py)
phục vụ file này.

Phong cách: ĐỒNG NHẤT với chính hệ thống Audit-HQ — dùng lại design token của
`app/static/style.css` (nền sáng #f6f7f9, header navy #1d3557, card/button/badge
của hệ thống). Sáng sủa, chuyên nghiệp; KHÔNG tạo style lạ.

Yêu cầu: ImageMagick (`convert`) có trong PATH.
Chạy:
    .venv/bin/python .ai/features/2026-06-14-showcase/build_showcase.py
"""
from __future__ import annotations

import base64
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHOTS = Path(__file__).resolve().parent / "screenshots"
OUT = ROOT / "app" / "static" / "showcase.html"

# key → (png nguồn, bề rộng tối đa px, JPEG quality). Ảnh chụp retina 2× → hạ
# về ~1240px cho nét chữ mà file vẫn gọn.
SOURCES: dict[str, tuple[Path, int, int]] = {
    "overview": (SHOTS / "01_overview.png", 1280, 84),
    "company_detail": (SHOTS / "02_company_detail.png", 1240, 84),
    "finding": (SHOTS / "03_finding_traceability.png", 1240, 84),
    "item": (SHOTS / "04_item_detail.png", 1240, 84),
    "docs": (SHOTS / "08_docs_index.png", 1240, 84),
    "upload": (SHOTS / "10_upload.png", 1240, 84),
    "access_audit": (SHOTS / "11_access_audit.png", 1240, 84),
    "permissions": (SHOTS / "12_permissions_officer.png", 1240, 84),
    "chat_tooluse": (SHOTS / "20_chat_tooluse.png", 1280, 84),
    "chat_mention": (SHOTS / "21_chat_mention.png", 1280, 84),
}


def _data_uri(png: Path, width: int, quality: int, tmp: Path) -> str:
    jpg = tmp / f"{png.stem}.jpg"
    subprocess.run(
        ["convert", str(png), "-resize", f"{width}x>", "-strip",
         "-quality", str(quality), str(jpg)],
        check=True,
    )
    b64 = base64.b64encode(jpg.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def main() -> None:
    html = TEMPLATE
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for key, (png, width, quality) in SOURCES.items():
            if not png.exists():
                raise SystemExit(f"Thiếu ảnh nguồn: {png}")
            html = html.replace(f"{{{{IMG:{key}}}}}", _data_uri(png, width, quality, tmp))
    if "{{IMG:" in html:
        raise SystemExit("Còn placeholder ảnh chưa thay — kiểm tra SOURCES")
    OUT.write_text(html, encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"Wrote {OUT} ({kb:.0f} KB)")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audit-HQ — Hệ thống quản lý rủi ro Báo cáo Quyết toán hải quan</title>
<meta name="description" content="Audit-HQ tự động đối chiếu Báo cáo Quyết toán hải quan, chấm điểm rủi ro minh bạch, truy nguồn từng phát hiện và có Trợ lý ảo luôn dẫn nguồn. Sản phẩm của Tinsu AI và Trọng Tín.">
<meta property="og:title" content="Audit-HQ — Quản lý rủi ro Báo cáo Quyết toán hải quan">
<meta property="og:description" content="Mười sáu bài kiểm tra tự động, chấm điểm rủi ro minh bạch, truy nguồn 100% và Trợ lý ảo luôn dẫn nguồn.">
<style>
:root{
  --c-brand-50:#eef2f7; --c-brand-100:#d6dfeb; --c-brand-500:#1d3557; --c-brand-600:#16294a; --c-brand-700:#0f1d3b;
  --c-bg:#f6f7f9; --c-surface:#fff; --c-surface-alt:#f8fafc;
  --c-text:#0f172a; --c-text-muted:#475569; --c-text-subtle:#64748b; --c-inverse:#fff;
  --c-border:#e2e8f0; --c-border-strong:#cbd5e1;
  --c-critical:#c1272d; --c-warning:#d97706; --c-info:#2563eb; --c-success:#15803d;
  --font-sans:"Inter","Be Vietnam Pro",-apple-system,"Segoe UI","Roboto",system-ui,sans-serif;
  --font-mono:"JetBrains Mono","SF Mono",Consolas,monospace;
  --radius-sm:3px; --radius-md:5px; --radius-lg:8px;
  --shadow-sm:0 1px 2px rgba(15,29,59,.06); --shadow-md:0 4px 12px rgba(15,29,59,.08);
  --maxw:1180px;
}
*,*::before,*::after{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--c-bg);color:var(--c-text);font-family:var(--font-sans);
  font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
a{color:var(--c-brand-500);text-decoration:none}
a:hover{text-decoration:underline}
h1,h2,h3,h4{margin:0;line-height:1.25;font-weight:700;color:var(--c-text)}
p{margin:0 0 1em}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 24px}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--c-brand-500);margin-bottom:12px}

/* — demo banner (đồng nhất hệ thống) — */
.demo-banner{background:#fef3c7;color:#78350f;border-bottom:1px solid #fcd34d;font-size:12.5px;line-height:1.45;
  padding:8px 0}
.demo-banner strong{color:#92400e}

/* — header (đồng nhất hệ thống) — */
.app-header{position:sticky;top:0;z-index:50;height:56px;background:var(--c-brand-500);color:var(--c-inverse);
  box-shadow:var(--shadow-sm)}
.app-header .wrap{height:56px;display:flex;align-items:center;gap:20px}
.brand{display:flex;align-items:center;gap:12px;color:#fff;font-weight:700;font-size:15px;letter-spacing:.02em}
.brand:hover{text-decoration:none}
.brand-logo{width:28px;height:28px;border-radius:var(--radius-sm);background:#fff;color:var(--c-brand-500);
  display:grid;place-items:center;font-weight:800;font-size:13px}
.brand small{display:block;font-size:11px;font-weight:400;color:rgba(255,255,255,.7);letter-spacing:0;margin-top:-1px}
.app-nav{display:flex;gap:4px;margin-left:auto}
.app-nav a{color:rgba(255,255,255,.85);font-size:13.5px;padding:5px 10px;border-radius:var(--radius-sm)}
.app-nav a:hover{background:rgba(255,255,255,.1);color:#fff;text-decoration:none}
.app-nav .demo-link{border:1px solid rgba(255,255,255,.25);margin-left:6px}
@media(max-width:880px){.app-nav a:not(.demo-link){display:none}}

/* — buttons (đồng nhất hệ thống) — */
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 18px;font-size:14px;font-weight:500;
  border-radius:var(--radius-sm);border:1px solid transparent;background:var(--c-surface);color:var(--c-text);cursor:pointer}
.btn:hover{text-decoration:none}
.btn-primary{background:var(--c-brand-500);color:#fff;border-color:var(--c-brand-500)}
.btn-primary:hover{background:var(--c-brand-600);border-color:var(--c-brand-600)}
.btn-secondary{background:#fff;color:var(--c-brand-500);border-color:var(--c-border-strong)}
.btn-secondary:hover{background:var(--c-brand-50);border-color:var(--c-brand-500)}

/* — hero (nền tint nhạt, sáng) — */
.hero{background:var(--c-brand-50);border-bottom:1px solid var(--c-border)}
.hero .wrap{padding-top:56px;padding-bottom:56px}
.hero .grid{display:grid;grid-template-columns:1.02fr .98fr;gap:46px;align-items:center}
@media(max-width:940px){.hero .grid{grid-template-columns:1fr;gap:32px}}
.hero h1{font-size:34px;letter-spacing:-.01em;line-height:1.2;color:var(--c-brand-700)}
.hero .sub{font-size:17px;color:var(--c-text-muted);margin:18px 0 28px;max-width:560px}
.hero .actions{display:flex;gap:12px;flex-wrap:wrap}
@media(max-width:680px){.hero h1{font-size:26px}}

/* — screenshot frame (card hệ thống) — */
.shot{margin:0;background:#fff;border:1px solid var(--c-border);border-radius:var(--radius-md);
  box-shadow:var(--shadow-md);overflow:hidden}
.shot .path{font:12px/1 var(--font-mono);color:var(--c-text-subtle);background:var(--c-surface-alt);
  border-bottom:1px solid var(--c-border);padding:9px 13px;display:flex;align-items:center;gap:8px}
.shot .path::before{content:"";width:8px;height:8px;border:1.5px solid var(--c-border-strong);border-radius:50%}
.shot img{display:block;width:100%;cursor:zoom-in}
.cap{font-size:13px;color:var(--c-text-subtle);margin:10px 2px 0}

/* — sections — */
section{padding:66px 0}
.alt{background:var(--c-surface);border-top:1px solid var(--c-border);border-bottom:1px solid var(--c-border)}
.section-head{max-width:800px;margin-bottom:40px}
.section-head h2{font-size:26px;letter-spacing:-.01em}
.section-head .lead{font-size:16.5px;color:var(--c-text-muted);margin-top:12px}
.split{display:grid;grid-template-columns:1fr 1fr;gap:46px;align-items:center}
.split.rev .txt{order:2}
@media(max-width:900px){.split{grid-template-columns:1fr;gap:28px}.split.rev .txt{order:0}}
.txt h3{font-size:21px;margin-bottom:13px;color:var(--c-brand-700)}
.txt ul{margin:14px 0 0;padding:0;list-style:none}
.txt li{position:relative;padding-left:24px;margin-bottom:13px;color:var(--c-text-muted)}
.txt li::before{content:"";position:absolute;left:0;top:9px;width:8px;height:8px;border-radius:50%;
  background:var(--c-brand-500)}
.txt li b{color:var(--c-text)}

/* — stat strip (card hệ thống, viền trái navy) — */
.stats{background:var(--c-bg)}
.stats .wrap{padding:34px 24px}
.stats .grid{display:grid;grid-template-columns:repeat(5,1fr);gap:16px}
@media(max-width:760px){.stats .grid{grid-template-columns:repeat(2,1fr)}}
.stat{background:#fff;border:1px solid var(--c-border);border-left:3px solid var(--c-brand-500);
  border-radius:var(--radius-md);padding:18px 20px;box-shadow:var(--shadow-sm)}
.stat .n{font-size:26px;font-weight:800;color:var(--c-brand-600);line-height:1.1}
.stat .l{font-size:12.5px;color:var(--c-text-subtle);margin-top:5px}

/* — capability cards — */
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
@media(max-width:820px){.cards{grid-template-columns:1fr}}
.card{background:#fff;border:1px solid var(--c-border);border-radius:var(--radius-md);padding:22px;box-shadow:var(--shadow-sm)}
.card h4{font-size:16px;margin-bottom:8px;color:var(--c-brand-700)}
.card p{color:var(--c-text-muted);font-size:14px;margin:0}
.callout{background:var(--c-brand-50);border:1px solid var(--c-brand-100);border-radius:var(--radius-md);
  padding:18px 22px;margin-top:24px;color:var(--c-text-muted);font-size:14.5px}
.callout b{color:var(--c-brand-700)}

/* — checks — */
.legend{display:flex;gap:22px;flex-wrap:wrap;margin:0 0 22px;font-size:13.5px;color:var(--c-text-muted)}
.legend span{display:inline-flex;align-items:center;gap:8px}
.legend i{width:10px;height:10px;border-radius:50%}
.chk{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}
@media(max-width:760px){.chk{grid-template-columns:1fr}}
.chk .g{background:#fff;border:1px solid var(--c-border);border-radius:var(--radius-md);padding:20px 22px;box-shadow:var(--shadow-sm)}
.chk .g h4{font-size:15px;display:flex;align-items:center;gap:10px;margin-bottom:10px;color:var(--c-brand-700)}
.chk .g .gn{background:var(--c-brand-500);color:#fff;padding:2px 9px;border-radius:var(--radius-sm);font-size:12px;font-weight:700}
.chk .g ul{margin:0;padding-left:18px;color:var(--c-text-muted);font-size:13.5px;line-height:1.75}

/* — cta — */
.cta{background:var(--c-brand-50);border-top:1px solid var(--c-border);text-align:center;padding:58px 0}
.cta h2{font-size:24px;color:var(--c-brand-700)}
.cta p{color:var(--c-text-muted);max-width:600px;margin:13px auto 26px}

/* — footer (đồng nhất hệ thống) — */
.app-footer{background:#fff;border-top:1px solid var(--c-border);color:var(--c-text-subtle);font-size:12.5px;
  padding:34px 0}
.app-footer .wrap{text-align:center}
.app-footer .line{margin-bottom:6px}
.app-footer .disc{max-width:880px;margin:16px auto 0;color:var(--c-text-subtle);line-height:1.6}

/* — lightbox — */
#lb{position:fixed;inset:0;background:rgba(15,23,42,.9);display:none;z-index:200;align-items:flex-start;
  justify-content:center;padding:28px;overflow:auto;cursor:zoom-out}
#lb.on{display:flex}
#lb img{max-width:1180px;width:100%;height:auto;border-radius:var(--radius-md);border:1px solid rgba(255,255,255,.2)}
</style>
</head>
<body>

<div class="demo-banner"><div class="wrap">
  <strong>Dữ liệu mẫu</strong> — tên doanh nghiệp, mã số thuế và đối tác đều đã được giả lập từ hồ sơ thực,
  chỉ phục vụ mục đích trình diễn. Các số liệu không phản ánh bất kỳ doanh nghiệp có thật nào.
</div></div>

<header class="app-header"><div class="wrap">
  <a class="brand" href="#top"><span class="brand-logo">A</span>
    <span>Audit-HQ<small>Quản lý rủi ro hải quan</small></span></a>
  <nav class="app-nav">
    <a href="#ai">Trợ lý ảo</a>
    <a href="#ingest">Tiếp nhận dữ liệu</a>
    <a href="#checks">Kiểm tra</a>
    <a href="#scoring">Chấm điểm</a>
    <a href="#trace">Truy nguồn</a>
    <a href="#govern">Phân quyền</a>
    <a class="demo-link" href="https://audit-hq-demo.tinsu.ai" target="_blank" rel="noopener">Mở demo</a>
  </nav>
</div></header>

<a id="top"></a>
<section class="hero"><div class="wrap"><div class="grid">
  <div>
    <div class="eyebrow">Sản phẩm của Tinsu AI và Trọng Tín · Bản thí điểm</div>
    <h1>Hệ thống quản lý rủi ro Báo cáo Quyết toán hải quan</h1>
    <p class="sub">Audit-HQ tự động đối chiếu chéo dữ liệu giữa các biểu mẫu quyết toán và tờ khai hải quan,
      phát hiện những điểm sai lệch theo bộ quy tắc nghiệp vụ, chấm điểm rủi ro cho từng doanh nghiệp, và
      hỗ trợ cán bộ tra cứu thông qua một Trợ lý ảo luôn dẫn nguồn về dữ liệu gốc.</p>
    <div class="actions">
      <a class="btn btn-primary" href="https://audit-hq-demo.tinsu.ai" target="_blank" rel="noopener">Mở bản demo trực tiếp</a>
      <a class="btn btn-secondary" href="#ai">Tìm hiểu Trợ lý ảo</a>
    </div>
  </div>
  <div>
    <figure class="shot"><div class="path">audit-hq-demo.tinsu.ai/doanh-nghiep</div>
      <img loading="lazy" src="{{IMG:overview}}" alt="Bảng tổng quan doanh nghiệp xếp theo điểm rủi ro"></figure>
  </div>
</div></div></section>

<div class="stats"><div class="wrap"><div class="grid">
  <div class="stat"><div class="n">16</div><div class="l">bài kiểm tra tự động</div></div>
  <div class="stat"><div class="n">49</div><div class="l">kiểm tra trong danh mục đầy đủ</div></div>
  <div class="stat"><div class="n">0–1000</div><div class="l">thang điểm rủi ro</div></div>
  <div class="stat"><div class="n">100%</div><div class="l">phát hiện đều truy được nguồn</div></div>
  <div class="stat"><div class="n">4</div><div class="l">nhóm tổ hợp dấu hiệu rủi ro</div></div>
</div></div></div>

<!-- ============ TRỢ LÝ ẢO ============ -->
<section id="ai" class="alt">
  <div class="wrap">
    <div class="section-head">
      <div class="eyebrow">Tính năng trọng tâm</div>
      <h2>Trợ lý ảo — tra cứu dữ liệu quyết toán, luôn dẫn nguồn</h2>
      <p class="lead">Trợ lý ảo của Audit-HQ không trả lời chung chung. Mỗi câu trả lời đều được tổng hợp
        trực tiếp từ cơ sở dữ liệu của hệ thống, kèm theo trích dẫn tới từng phát hiện và từng dòng dữ liệu
        để cán bộ có thể tự đối chiếu. Trợ lý chỉ làm việc trong đúng phạm vi doanh nghiệp mà cán bộ được
        phân công, và luôn ở chế độ chỉ đọc.</p>
    </div>

    <div class="cards">
      <div class="card"><h4>Tra cứu phát hiện</h4>
        <p>Tìm và liệt kê các phát hiện của một doanh nghiệp theo năm, theo mức độ nghiêm trọng hoặc theo
          từng bài kiểm tra, đồng thời mở chi tiết và căn cứ của mỗi phát hiện.</p></div>
      <div class="card"><h4>Tổng hợp và so sánh</h4>
        <p>Thống kê, xếp hạng và so sánh nhiều doanh nghiệp với nhau, cũng như tra cứu dữ liệu gốc của các
          biểu mẫu báo cáo khi cần đối chiếu sâu hơn.</p></div>
      <div class="card"><h4>Giải thích nghiệp vụ</h4>
        <p>Giải thích ý nghĩa của từng bài kiểm tra và cách hình thành điểm rủi ro, giúp cán bộ hiểu rõ vì
          sao một dấu hiệu được nêu lên.</p></div>
      <div class="card"><h4>Dẫn chiếu pháp lý</h4>
        <p>Trích dẫn các điều khoản liên quan trong Thông tư 38, Thông tư 39 và Thông tư 81 để làm rõ căn cứ
          pháp lý cho mỗi nhận định.</p></div>
      <div class="card"><h4>Soạn và xuất báo cáo</h4>
        <p>Tổng hợp báo cáo theo yêu cầu và kết xuất ra tệp Excel kèm liên kết tải về, phục vụ việc lưu hồ
          sơ và báo cáo cấp trên.</p></div>
      <div class="card"><h4>Tôn trọng thẩm quyền cán bộ</h4>
        <p>Trợ lý chỉ đề xuất các thao tác như chạy lại kiểm tra; việc xác nhận hay bác bỏ một phát hiện
          luôn do cán bộ quyết định.</p></div>
    </div>

    <div class="callout">
      Mọi truy vấn của Trợ lý đều bị giới hạn trong phần dữ liệu mà cán bộ được phép xem và chỉ ở chế độ
      chỉ đọc, nên Trợ lý không thể tự ý thay đổi dữ liệu. Hệ thống còn có lớp kiểm soát an toàn nhằm hạn
      chế thông tin sai và nhắc Trợ lý luôn kèm theo nguồn cho mỗi con số.
    </div>

    <div class="split" style="margin-top:40px">
      <div>
        <figure class="shot"><div class="path">audit-hq-demo.tinsu.ai/chat</div>
          <img loading="lazy" src="{{IMG:chat_tooluse}}" alt="Trợ lý trả lời kèm dữ liệu đã tra cứu"></figure>
        <div class="cap">Mỗi lần tra cứu được trình bày rõ ràng; cán bộ có thể mở ra để xem đúng dữ liệu Trợ lý đã sử dụng.</div>
      </div>
      <div>
        <figure class="shot"><div class="path">audit-hq-demo.tinsu.ai/chat</div>
          <img loading="lazy" src="{{IMG:chat_mention}}" alt="Chọn nhanh doanh nghiệp hoặc phát hiện để hỏi"></figure>
        <div class="cap">Có thể chọn nhanh một doanh nghiệp hoặc một phát hiện để đính kèm đúng ngữ cảnh vào câu hỏi.</div>
      </div>
    </div>
  </div>
</section>

<!-- ============ TIẾP NHẬN DỮ LIỆU ============ -->
<section id="ingest">
  <div class="wrap">
    <div class="split rev">
      <div class="txt">
        <div class="eyebrow">Tiếp nhận dữ liệu</div>
        <h3>Tải lên và kiểm tra dữ liệu quyết toán có hỗ trợ của trí tuệ nhân tạo</h3>
        <p>Cán bộ tải lên bốn biểu mẫu của báo cáo quyết toán gồm Mẫu 15, Mẫu 15a, Mẫu 16 và tờ khai chi
          tiết. Hệ thống tự nhận dạng cấu trúc của từng tệp, xử lý song song nhiều định dạng khác nhau, và
          tách riêng bước nạp dữ liệu với bước chạy kiểm tra để cán bộ chủ động rà soát.</p>
        <ul>
          <li><b>Chẩn đoán tệp lỗi bằng trí tuệ nhân tạo:</b> khi một tệp có cấu trúc lạ hoặc lệch cột, hệ thống đọc trích đoạn thực tế của tệp, đối chiếu với cấu trúc chuẩn rồi diễn giải bằng tiếng Việt và gợi ý cách khắc phục.</li>
          <li><b>Chuẩn hoá tên hàng hoá:</b> những tên nguyên vật liệu được khai không thống nhất sẽ được chuẩn hoá lại để việc đối chiếu trở nên chính xác hơn.</li>
          <li><b>Tự nhận diện loại hình doanh nghiệp</b> (sản xuất xuất khẩu, doanh nghiệp chế xuất, gia công) ngay từ dữ liệu tờ khai, cán bộ không cần khai báo thủ công.</li>
          <li><b>Kiểm tra định dạng thực của tệp</b> để ngăn các trường hợp đổi đuôi tệp, đồng thời giới hạn dung lượng và định dạng được phép tải lên.</li>
        </ul>
      </div>
      <div>
        <figure class="shot"><div class="path">audit-hq-demo.tinsu.ai/doanh-nghiep/…/tai-len</div>
          <img loading="lazy" src="{{IMG:upload}}" alt="Trang tải lên dữ liệu quyết toán"></figure>
      </div>
    </div>
  </div>
</section>

<!-- ============ KIỂM TRA ============ -->
<section id="checks" class="alt">
  <div class="wrap">
    <div class="section-head">
      <div class="eyebrow">Nghiệp vụ cốt lõi</div>
      <h2>Mười sáu bài kiểm tra tự động trong danh mục bốn mươi chín kiểm tra</h2>
      <p class="lead">Hệ thống đối chiếu chéo giữa các biểu mẫu quyết toán và tờ khai, sau đó phân loại mỗi
        phát hiện theo ba mức độ rủi ro.</p>
    </div>
    <div class="legend">
      <span><i style="background:var(--c-critical)"></i> Nghiêm trọng</span>
      <span><i style="background:var(--c-warning)"></i> Cảnh báo</span>
      <span><i style="background:var(--c-info)"></i> Thông tin</span>
    </div>
    <div class="chk">
      <div class="g"><h4><span class="gn">Nhóm 1</span> Lệch số lượng</h4>
        <ul><li>Lệch số lượng nguyên vật liệu nhập giữa Mẫu 15 và tờ khai</li>
        <li>Lệch số lượng thành phẩm xuất giữa Mẫu 15a và tờ khai</li>
        <li>Có tờ khai nhưng thiếu trong Mẫu 15, hoặc ngược lại</li>
        <li>Chuyển mục đích sử dụng vượt ngưỡng hoặc thiếu tờ khai A42</li></ul></div>
      <div class="g"><h4><span class="gn">Nhóm 2</span> Cân đối kho</h4>
        <ul><li>Mất cân bằng phương trình kho nguyên vật liệu (Mẫu 15)</li>
        <li>Mất cân bằng phương trình kho thành phẩm (Mẫu 15a)</li>
        <li>Tồn cuối kỳ nguyên vật liệu mang giá trị âm</li>
        <li>Tồn cuối kỳ thành phẩm mang giá trị âm</li></ul></div>
      <div class="g"><h4><span class="gn">Nhóm 3</span> Phân loại và mã hàng</h4>
        <ul><li>Cùng một mã vật tư nhưng khai nhiều loại hình mâu thuẫn</li>
        <li>Mã HS không nhất quán trong cùng kỳ</li>
        <li>Đơn vị tính không nhất quán</li></ul></div>
      <div class="g"><h4><span class="gn">Nhóm 4–6</span> Định mức và liên kỳ</h4>
        <ul><li>Nguyên vật liệu trong định mức Mẫu 16 không có nguồn gốc</li>
        <li>Tổng tiêu hao theo Mẫu 16 vượt lượng xuất sản xuất ở Mẫu 15</li>
        <li>Nguyên vật liệu có xuất sản xuất nhưng không nhập và không tồn đầu</li>
        <li>Tồn đầu kỳ này khác tồn cuối kỳ liền trước</li></ul></div>
    </div>
    <div class="callout">
      <b>Bốn nhóm tổ hợp dấu hiệu rủi ro:</b> khi nhiều dấu hiệu bất thường cùng xuất hiện trên một doanh
      nghiệp — chẳng hạn tồn kho âm đi kèm mức tiêu hao vượt định mức (dấu hiệu lập định mức không có thật),
      hoặc nhập kho không có tờ khai đi kèm xuất sản xuất không rõ nguồn (dấu hiệu sử dụng nguyên vật liệu
      nội địa ngoài luồng) — hệ thống sẽ nâng mức cảnh báo và cộng thêm điểm rủi ro.
    </div>
  </div>
</section>

<!-- ============ CHẤM ĐIỂM ============ -->
<section id="scoring">
  <div class="wrap">
    <div class="split">
      <div class="txt">
        <div class="eyebrow">Minh bạch</div>
        <h3>Điểm rủi ro từ 0 đến 1000, giải thích được đến từng thành phần</h3>
        <p>Điểm rủi ro không phải là tổng số phát hiện. Mỗi bài kiểm tra được chấm tối đa mười điểm dựa trên
          tỷ lệ giữa số phát hiện và quy mô dữ liệu của doanh nghiệp; điểm của các bài được cộng lại cùng
          điểm tổ hợp, rồi quy về thang điểm chung từ 0 đến 1000.</p>
        <ul>
          <li><b>Chấm theo tỷ lệ và có mức trần:</b> khi sai lệch đã đủ lớn so với quy mô dữ liệu, điểm của bài kiểm tra dừng lại ở mức tối đa, tránh việc điểm phình lên chỉ vì có nhiều dòng dữ liệu.</li>
          <li><b>Bảng tính điểm chi tiết</b> hiển thị ngay trên trang doanh nghiệp, gồm công thức, điểm của từng bài và quy mô dữ liệu được dùng làm mẫu số.</li>
          <li><b>Năm hạng cảnh báo</b> giúp phân tầng doanh nghiệp theo mức độ rủi ro của dữ liệu.</li>
          <li>Đây là chỉ số rủi ro về chất lượng dữ liệu nội bộ, không phải là kết luận về mức độ tuân thủ pháp luật.</li>
        </ul>
      </div>
      <div>
        <figure class="shot"><div class="path">audit-hq-demo.tinsu.ai/doanh-nghiep/…?nam=2022</div>
          <img loading="lazy" src="{{IMG:company_detail}}" alt="Trang doanh nghiệp kèm bảng tính điểm rủi ro"></figure>
        <div class="cap">Trang doanh nghiệp hiển thị điểm rủi ro theo từng năm, kèm bảng thuyết minh cách tính điểm.</div>
      </div>
    </div>
  </div>
</section>

<!-- ============ TRUY NGUỒN ============ -->
<section id="trace" class="alt">
  <div class="wrap">
    <div class="section-head">
      <div class="eyebrow">Không có hộp đen</div>
      <h2>Mọi phát hiện đều truy được về dòng dữ liệu gốc</h2>
      <p class="lead">Từ một phát hiện, cán bộ có thể mở thẳng tới chứng cứ gốc — đúng dòng tờ khai, đúng mã
        hàng, đúng kỳ báo cáo — để tự kiểm chứng trước khi đưa ra kết luận.</p>
    </div>
    <div class="split">
      <div>
        <figure class="shot"><div class="path">audit-hq-demo.tinsu.ai/phat-hien/1357</div>
          <img loading="lazy" src="{{IMG:finding}}" alt="Chi tiết phát hiện kèm chứng cứ truy nguồn"></figure>
        <div class="cap">Chi tiết một phát hiện: mô tả nghiệp vụ kèm chứng cứ truy nguồn về đúng dòng tờ khai.</div>
      </div>
      <div>
        <figure class="shot"><div class="path">audit-hq-demo.tinsu.ai/doanh-nghiep/…/ma-hang/…</div>
          <img loading="lazy" src="{{IMG:item}}" alt="Trang mã hàng với cân đối kho"></figure>
        <div class="cap">Trang mã hàng: tình hình cân đối kho, các giao dịch trên tờ khai và dòng đi vào thành phẩm.</div>
      </div>
    </div>
  </div>
</section>

<!-- ============ PHÂN QUYỀN ============ -->
<section id="govern">
  <div class="wrap">
    <div class="section-head">
      <div class="eyebrow">Phù hợp sử dụng nội bộ</div>
      <h2>Phân quyền theo doanh nghiệp và nhật ký truy cập</h2>
      <p class="lead">Mỗi cán bộ được phân công phụ trách một số doanh nghiệp nhất định; những doanh nghiệp
        ngoài phạm vi sẽ không hiển thị đối với cán bộ đó. Ranh giới phân quyền này được áp dụng cho cả Trợ lý ảo.</p>
    </div>
    <div class="cards" style="margin-bottom:32px">
      <div class="card"><h4>Cô lập dữ liệu</h4>
        <p>Hệ thống có hai vai trò là quản trị viên và cán bộ. Việc kiểm soát truy cập được thực hiện ở phía
          máy chủ tại mọi lối vào, chứ không chỉ ẩn bớt giao diện.</p></div>
      <div class="card"><h4>Trợ lý ảo cùng chung phạm vi</h4>
        <p>Các truy vấn của Trợ lý chỉ làm việc trên phần dữ liệu mà cán bộ được phép xem, do đó không thể
          dùng Trợ lý để vượt quá phạm vi được giao.</p></div>
      <div class="card"><h4>Nhật ký truy cập</h4>
        <p>Hệ thống ghi lại các thao tác như tải tệp, xuất báo cáo và chạy kiểm tra, đồng thời giới hạn số
          lần đăng nhập sai nhằm chống dò mật khẩu.</p></div>
    </div>
    <div class="split">
      <div>
        <figure class="shot"><div class="path">audit-hq-demo.tinsu.ai/admin/nhat-ky</div>
          <img loading="lazy" src="{{IMG:access_audit}}" alt="Nhật ký truy cập"></figure>
        <div class="cap">Nhật ký truy cập ghi lại ai đã thực hiện thao tác gì, trên doanh nghiệp nào và vào thời điểm nào.</div>
      </div>
      <div>
        <figure class="shot"><div class="path">audit-hq-demo.tinsu.ai/doanh-nghiep</div>
          <img loading="lazy" src="{{IMG:permissions}}" alt="Góc nhìn của cán bộ chỉ thấy doanh nghiệp được giao"></figure>
        <div class="cap">Góc nhìn của cán bộ: chỉ thấy những doanh nghiệp nằm trong phạm vi được phân công.</div>
      </div>
    </div>
  </div>
</section>

<!-- ============ TÀI LIỆU ============ -->
<section id="docs" class="alt">
  <div class="wrap">
    <div class="split rev">
      <div class="txt">
        <div class="eyebrow">Có căn cứ</div>
        <h3>Tài liệu pháp lý và phương pháp luận đi kèm</h3>
        <p>Hệ thống tích hợp sẵn các văn bản nền tảng cùng bản thuyết minh cách tính điểm, để cán bộ và
          doanh nghiệp cùng hiểu rõ căn cứ của mỗi phát hiện.</p>
        <ul>
          <li><b>Phương pháp tính điểm rủi ro</b> — trình bày công thức tính theo tỷ lệ và năm hạng cảnh báo.</li>
          <li><b>Thông tư 38/2015 và Thông tư 39/2018</b> — thủ tục hải quan, định nghĩa báo cáo quyết toán, mã loại hình tờ khai và phương trình cân đối kho.</li>
          <li><b>Thông tư 81/2019</b> — quản lý rủi ro trong nghiệp vụ hải quan.</li>
        </ul>
        <p style="margin-top:18px;font-size:13.5px;color:var(--c-text-subtle)"><b style="color:var(--c-text)">Nền tảng kỹ thuật:</b>
          hệ thống được xây dựng trên Python và FastAPI, lưu trữ dữ liệu qua SQLAlchemy, xử lý tệp Excel
          bằng pandas, có hàng đợi tác vụ chạy nền và giao diện gọn nhẹ kết xuất từ máy chủ.</p>
      </div>
      <div>
        <figure class="shot"><div class="path">audit-hq-demo.tinsu.ai/tai-lieu</div>
          <img loading="lazy" src="{{IMG:docs}}" alt="Thư viện tài liệu"></figure>
        <div class="cap">Thư viện tài liệu pháp lý và phương pháp luận được tích hợp sẵn trong hệ thống.</div>
      </div>
    </div>
  </div>
</section>

<div class="cta"><div class="wrap">
  <h2>Mời quý vị trải nghiệm trực tiếp</h2>
  <p>Toàn bộ các tính năng nêu trên đang vận hành trên bản demo công khai, với dữ liệu đã được ẩn danh.</p>
  <a class="btn btn-primary" href="https://audit-hq-demo.tinsu.ai" target="_blank" rel="noopener">Mở Audit-HQ demo</a>
</div></div>

<footer class="app-footer"><div class="wrap">
  <div class="line"><strong>Audit-HQ</strong> — Hệ thống quản lý rủi ro Báo cáo Quyết toán hải quan · Tinsu AI và Trọng Tín · Bản dùng cho thí điểm</div>
  <div class="disc">
    Chỉ số rủi ro trên hệ thống là chỉ số về chất lượng dữ liệu báo cáo quyết toán (chênh lệch nội bộ giữa
    các Mẫu 15, 15a, 16 và đối chiếu với tờ khai), <strong>không phải</strong> là đánh giá mức độ tuân thủ
    pháp luật theo Thông tư 81/2019/TT-BTC. Việc phân loại tuân thủ chính thức thuộc thẩm quyền của Tổng cục
    Hải quan, và mọi quyết định cuối cùng đều thuộc thẩm quyền của cán bộ. Toàn bộ số liệu minh hoạ đã được
    ẩn danh và không phản ánh bất kỳ doanh nghiệp có thật nào.
  </div>
</div></footer>

<div id="lb"><img alt=""></div>
<script>
(function(){
  var lb=document.getElementById('lb'),lbimg=lb.querySelector('img');
  document.querySelectorAll('.shot img').forEach(function(im){
    im.addEventListener('click',function(){lbimg.src=im.src;lb.classList.add('on');});
  });
  lb.addEventListener('click',function(){lb.classList.remove('on');lbimg.src='';});
  document.addEventListener('keydown',function(e){if(e.key==='Escape'){lb.classList.remove('on');lbimg.src='';}});
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
