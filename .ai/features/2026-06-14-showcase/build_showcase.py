"""Dựng trang showcase tính năng (self-contained HTML, ảnh nhúng base64).

Tự lập (reproducible) từ ảnh PNG đã commit ở screenshots/ (chụp bằng ui_smoke.py —
retina, crop gọn, ẩn banner): nén PNG → JPEG (ImageMagick `convert`), nhúng base64
vào template, ghi ra app/static/showcase.html. Route public `/showcase` (app/main.py)
phục vụ file này.

Tông màu: nhà nước / nghiêm túc — navy đậm + trắng + xám, điểm nhấn đỏ-thẫm tiết chế.

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
# về ~1240px cho nét chữ mà file vẫn gọn (HTML self-contained ~2.5 MB).
SOURCES: dict[str, tuple[Path, int, int]] = {
    "overview": (SHOTS / "01_overview.png", 1280, 84),
    "company_detail": (SHOTS / "02_company_detail.png", 1240, 84),
    "finding": (SHOTS / "03_finding_traceability.png", 1240, 84),
    "item": (SHOTS / "04_item_detail.png", 1240, 84),
    "catalog": (SHOTS / "05_catalog.png", 1240, 82),
    "admin_ai": (SHOTS / "07_admin_ai.png", 1240, 84),
    "docs": (SHOTS / "08_docs_index.png", 1240, 84),
    "scoring_doc": (SHOTS / "09_scoring_methodology.png", 1180, 82),
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
<title>Audit-HQ — Hệ thống Quản lý Rủi ro Báo cáo Quyết toán hải quan</title>
<meta name="description" content="Audit-HQ tự động đối chiếu Báo cáo Quyết toán hải quan (BCQT), chấm điểm rủi ro minh bạch, truy nguồn từng phát hiện và có Trợ lý AI dẫn nguồn. Sản phẩm Tinsu AI × Trọng Tín.">
<meta property="og:title" content="Audit-HQ — Quản lý Rủi ro BCQT cho Hải quan">
<meta property="og:description" content="16 bài kiểm tra tự động, chấm điểm rủi ro 0–1000 minh bạch, truy nguồn 100% và Trợ lý AI dẫn nguồn.">
<style>
:root{
  --navy:#102a43; --navy-2:#1d3557; --steel:#334e68;
  --ink:#1f2933; --muted:#5b6b7b; --faint:#8a99a8;
  --line:#dde3ea; --line-2:#e9edf2; --bg:#f4f6f8; --card:#fff;
  --accent:#8c1d1d; --accent-2:#a32a2a;
  --maxw:1140px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;font-family:"Be Vietnam Pro","Inter",-apple-system,"Segoe UI",Roboto,system-ui,sans-serif;
  color:var(--ink);background:var(--card);line-height:1.62;font-size:16px;-webkit-font-smoothing:antialiased}
a{color:var(--navy-2);text-decoration:none}
a:hover{text-decoration:underline}
h1,h2,h3,h4{margin:0;line-height:1.25;font-weight:700;color:var(--navy)}
p{margin:0 0 1em}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 24px}
.topline{height:4px;background:var(--accent)}
.eyebrow{font-size:12.5px;font-weight:700;letter-spacing:.13em;text-transform:uppercase;color:var(--accent);margin-bottom:14px}

/* nav */
.nav{position:sticky;top:0;z-index:50;background:var(--navy);border-bottom:1px solid rgba(255,255,255,.08)}
.nav .wrap{display:flex;align-items:center;gap:22px;height:62px}
.nav .logo{display:flex;align-items:center;gap:11px;color:#fff;font-weight:700;font-size:17px;letter-spacing:.01em}
.nav .logo .mark{width:30px;height:30px;border:1.5px solid rgba(255,255,255,.55);display:grid;place-items:center;
  color:#fff;font-weight:800;font-size:15px}
.nav .logo small{display:block;font-size:11px;font-weight:500;color:#9fb3c8;letter-spacing:.02em;margin-top:-2px}
.nav .links{display:flex;gap:24px;margin-left:auto}
.nav .links a{color:#bcccdc;font-size:14px;font-weight:500}
.nav .links a:hover{color:#fff;text-decoration:none}
.nav .cta{border:1px solid rgba(255,255,255,.4);color:#fff;padding:8px 16px;font-weight:600;font-size:14px}
.nav .cta:hover{text-decoration:none;background:rgba(255,255,255,.1)}
@media(max-width:900px){.nav .links{display:none}}

/* hero */
.hero{background:var(--navy);color:#fff;padding:66px 0 64px;border-bottom:1px solid rgba(255,255,255,.06)}
.hero .grid{display:grid;grid-template-columns:1.05fr .95fr;gap:48px;align-items:center}
@media(max-width:920px){.hero .grid{grid-template-columns:1fr;gap:34px}}
.hero .eyebrow{color:#c79a9a}
.hero h1{font-size:40px;font-weight:800;letter-spacing:-.015em;color:#fff;line-height:1.18}
.hero .sub{font-size:18px;color:#bcccdc;margin:20px 0 30px;max-width:560px}
.hero .actions{display:flex;gap:13px;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;gap:8px;padding:13px 24px;font-weight:600;font-size:15px;border:1px solid transparent}
.btn-primary{background:#fff;color:var(--navy)}
.btn-primary:hover{text-decoration:none;background:#e9edf2}
.btn-outline{background:transparent;color:#fff;border-color:rgba(255,255,255,.42)}
.btn-outline:hover{text-decoration:none;background:rgba(255,255,255,.1)}
.hero .meta{margin-top:26px;font-size:13px;color:#8aa1b8;border-top:1px solid rgba(255,255,255,.12);padding-top:18px;max-width:560px}
.hero-shot{border:1px solid rgba(255,255,255,.14);background:#fff;box-shadow:0 18px 40px rgba(0,0,0,.28)}
.hero-shot .bar{background:#f0f3f6;border-bottom:1px solid var(--line);padding:8px 12px;font:12px/1 "JetBrains Mono",monospace;color:#7a8a99}
.hero-shot img{display:block;width:100%}
@media(max-width:680px){.hero h1{font-size:30px}.hero{padding:46px 0}}

/* stats */
.stats{background:var(--bg);border-bottom:1px solid var(--line)}
.stats .grid{display:grid;grid-template-columns:repeat(5,1fr)}
.stats .it{padding:26px 18px;text-align:center;border-right:1px solid var(--line)}
.stats .it:last-child{border-right:0}
.stats .n{font-size:28px;font-weight:800;color:var(--navy)}
.stats .l{font-size:12.5px;color:var(--muted);margin-top:3px}
@media(max-width:760px){.stats .grid{grid-template-columns:repeat(2,1fr)}.stats .it:nth-child(2){border-right:0}
  .stats .it{border-bottom:1px solid var(--line)}}

/* sections */
section{padding:74px 0}
.alt{background:var(--bg);border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.section-head{max-width:780px;margin-bottom:42px}
.section-head h2{font-size:29px;letter-spacing:-.01em}
.section-head .lead{font-size:17.5px;color:var(--muted);margin-top:13px}

.split{display:grid;grid-template-columns:1fr 1fr;gap:46px;align-items:center}
.split.rev .txt{order:2}
@media(max-width:900px){.split{grid-template-columns:1fr;gap:30px}.split.rev .txt{order:0}}
.txt h3{font-size:22px;margin-bottom:13px}
.txt ul{margin:16px 0 0;padding:0;list-style:none}
.txt li{position:relative;padding-left:24px;margin-bottom:12px;color:var(--steel)}
.txt li:before{content:"";position:absolute;left:0;top:11px;width:9px;height:2px;background:var(--accent)}
.txt li b{color:var(--navy)}

/* screenshot frame — phẳng, không màu mè */
.shot{margin:0;border:1px solid var(--line);background:#fff}
.shot .bar{display:flex;align-items:center;gap:8px;background:#f0f3f6;border-bottom:1px solid var(--line);
  padding:8px 13px;font:12px/1 "JetBrains Mono",monospace;color:#7a8a99}
.shot .bar:before{content:"";width:8px;height:8px;border:1.5px solid #b4c0cc;border-radius:50%}
.shot img{display:block;width:100%;cursor:zoom-in}
.cap{font-size:13px;color:var(--muted);margin-top:11px}

/* feature grid (AI) */
.feat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin-top:8px}
@media(max-width:820px){.feat-grid{grid-template-columns:1fr}}
.feat{background:#fff;padding:24px 22px}
.feat .k{font-size:11.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:9px}
.feat h4{font-size:16.5px;margin-bottom:7px;color:var(--navy)}
.feat p{color:var(--muted);font-size:14px;margin:0}

/* tools list */
.tools{margin-top:30px;border:1px solid var(--line);background:#fff}
.tools .th{padding:13px 18px;border-bottom:1px solid var(--line);font-size:12.5px;font-weight:700;
  letter-spacing:.06em;text-transform:uppercase;color:var(--steel);background:#f7f9fb}
.tools .row{display:grid;grid-template-columns:repeat(3,1fr)}
@media(max-width:760px){.tools .row{grid-template-columns:1fr}}
.tools .t{padding:13px 18px;border-right:1px solid var(--line-2);border-bottom:1px solid var(--line-2);font-size:14px;color:var(--steel)}
.tools .t code{font:12.5px "JetBrains Mono",monospace;color:var(--navy);background:none}
.tools .t b{display:block;color:var(--navy);font-weight:600;margin-top:2px;font-size:13px}

/* generic cards */
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
@media(max-width:820px){.cards{grid-template-columns:1fr}}
.card{background:#fff;border:1px solid var(--line);padding:24px;border-top:3px solid var(--navy)}
.card h4{font-size:16.5px;margin-bottom:8px}
.card p{color:var(--muted);font-size:14.5px;margin:0}

/* checks */
.chk{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;margin-top:6px}
@media(max-width:760px){.chk{grid-template-columns:1fr}}
.chk .g{background:#fff;border:1px solid var(--line);padding:20px 22px}
.chk .g h4{font-size:15.5px;display:flex;align-items:center;gap:10px;margin-bottom:10px;color:var(--navy)}
.chk .g .gn{background:var(--navy);color:#fff;padding:3px 9px;font-size:12px;font-weight:700;letter-spacing:.03em}
.chk .g ul{margin:0;padding-left:18px;color:var(--steel);font-size:13.5px;line-height:1.7}
.legend{display:flex;gap:22px;flex-wrap:wrap;margin:22px 0 4px;font-size:13.5px;color:var(--steel)}
.legend span{display:inline-flex;align-items:center;gap:8px}
.legend i{width:10px;height:10px;border-radius:50%;display:inline-block}
.combo{margin-top:20px;background:#fff;border:1px solid var(--line);border-left:3px solid var(--accent);padding:18px 22px;color:var(--steel)}
.combo b{color:var(--navy)}

/* cta */
.cta-band{background:var(--navy);color:#fff;text-align:center;padding:62px 0}
.cta-band h2{color:#fff;font-size:27px}
.cta-band p{color:#bcccdc;max-width:600px;margin:14px auto 28px}

/* footer */
footer{background:#0b1e33;color:#9fb3c8;padding:46px 0 38px;font-size:14px}
footer .cols{display:flex;flex-wrap:wrap;gap:40px;justify-content:space-between}
footer h4{color:#fff;font-size:14px;margin-bottom:11px;letter-spacing:.02em}
footer a{color:#bcccdc}
.disclaimer{margin-top:28px;padding-top:22px;border-top:1px solid rgba(255,255,255,.1);color:#7e93a8;font-size:12.5px;max-width:880px}

/* lightbox */
#lb{position:fixed;inset:0;background:rgba(8,14,22,.93);display:none;z-index:200;
  align-items:flex-start;justify-content:center;padding:28px;overflow:auto;cursor:zoom-out}
#lb.on{display:flex}
#lb img{max-width:1180px;width:100%;height:auto;border:1px solid rgba(255,255,255,.2)}
</style>
</head>
<body>
<div class="topline"></div>

<nav class="nav"><div class="wrap">
  <div class="logo"><span class="mark">A</span><span>Audit-HQ<small>Quản lý rủi ro hải quan</small></span></div>
  <div class="links">
    <a href="#ai">Trợ lý AI</a>
    <a href="#ingest">Nạp dữ liệu</a>
    <a href="#checks">Kiểm tra</a>
    <a href="#scoring">Chấm điểm</a>
    <a href="#trace">Truy nguồn</a>
    <a href="#govern">Phân quyền</a>
  </div>
  <a class="cta" href="https://audit-hq-demo.tinsu.ai" target="_blank" rel="noopener">Mở demo</a>
</div></nav>

<header class="hero"><div class="wrap"><div class="grid">
  <div>
    <div class="eyebrow">Tinsu AI × Trọng Tín · Bản thí điểm</div>
    <h1>Quản lý rủi ro Báo cáo Quyết toán hải quan — tự động, minh bạch.</h1>
    <p class="sub">Audit-HQ đối chiếu chéo Mẫu 15 / 15a / 16 và tờ khai chi tiết, phát hiện sai lệch
      theo bộ quy tắc nghiệp vụ, chấm điểm rủi ro từng doanh nghiệp, và hỗ trợ cán bộ tra cứu bằng
      Trợ lý AI luôn dẫn nguồn về dòng dữ liệu gốc.</p>
    <div class="actions">
      <a class="btn btn-primary" href="https://audit-hq-demo.tinsu.ai" target="_blank" rel="noopener">Mở demo trực tiếp</a>
      <a class="btn btn-outline" href="#ai">Tìm hiểu Trợ lý AI</a>
    </div>
    <div class="meta">Toàn bộ số liệu minh hoạ là dữ liệu mẫu đã ẩn danh — không phản ánh doanh nghiệp có thật.</div>
  </div>
  <div>
    <div class="hero-shot">
      <div class="bar">audit-hq-demo.tinsu.ai/companies</div>
      <img loading="lazy" src="{{IMG:overview}}" alt="Bảng tổng quan doanh nghiệp theo điểm rủi ro">
    </div>
  </div>
</div></div></header>

<div class="stats"><div class="wrap"><div class="grid">
  <div class="it"><div class="n">16</div><div class="l">bài kiểm tra tự động</div></div>
  <div class="it"><div class="n">12</div><div class="l">công cụ Trợ lý AI</div></div>
  <div class="it"><div class="n">0–1000</div><div class="l">thang điểm rủi ro</div></div>
  <div class="it"><div class="n">100%</div><div class="l">phát hiện truy được nguồn</div></div>
  <div class="it"><div class="n">4</div><div class="l">tổ hợp dấu hiệu rủi ro</div></div>
</div></div></div>

<!-- ============ TRỢ LÝ AI ============ -->
<section id="ai" class="alt">
  <div class="wrap">
    <div class="section-head">
      <div class="eyebrow">Tính năng trọng tâm</div>
      <h2>Trợ lý AI — tra cứu dữ liệu BCQT, luôn dẫn nguồn</h2>
      <p class="lead">Không phải chatbot trả lời chung chung. Trợ lý gọi 12 công cụ chỉ-đọc trực tiếp
        trên cơ sở dữ liệu, trích dẫn từng phát hiện và dòng dữ liệu, và tôn trọng đúng phạm vi
        doanh nghiệp mà cán bộ được phân công.</p>
    </div>

    <div class="feat-grid">
      <div class="feat"><div class="k">Dẫn nguồn</div><h4>Trả lời có trích dẫn</h4>
        <p>Mọi con số kèm trích dẫn bấm được tới phát hiện, dòng M15/tờ khai hoặc điều khoản pháp lý — không có "hộp đen".</p></div>
      <div class="feat"><div class="k">Minh bạch</div><h4>Gọi công cụ hiển thị rõ</h4>
        <p>Mỗi lần tra cứu hiện một thẻ gọn (tên công cụ); cán bộ bấm để xem đúng dữ liệu công cụ đã đọc.</p></div>
      <div class="feat"><div class="k">An toàn</div><h4>Truy vấn SQL theo quyền</h4>
        <p>Trợ lý tự viết truy vấn tổng hợp / đếm / so sánh nhiều DN, nhưng chỉ chạy trên view đã giới hạn theo phạm vi.</p></div>
      <div class="feat"><div class="k">Ngữ cảnh</div><h4>Nhắc nhanh thực thể</h4>
        <p>Gõ ký hiệu nhắc để chèn doanh nghiệp hoặc phát hiện vào câu hỏi, đính kèm đúng ngữ cảnh cần hỏi.</p></div>
      <div class="feat"><div class="k">Kết xuất</div><h4>Soạn báo cáo &amp; xuất Excel</h4>
        <p>Yêu cầu Trợ lý tổng hợp báo cáo hoặc xuất kết quả truy vấn ra Excel kèm liên kết tải về.</p></div>
      <div class="feat"><div class="k">Thẩm quyền</div><h4>Con người quyết định</h4>
        <p>Trợ lý chỉ đề xuất chạy lại kiểm tra; việc xác nhận hay bác bỏ phát hiện luôn thuộc cán bộ.</p></div>
    </div>

    <div class="tools">
      <div class="th">12 công cụ chỉ-đọc của Trợ lý</div>
      <div class="row">
        <div class="t"><code>search_findings</code><b>Tìm phát hiện theo bộ lọc</b></div>
        <div class="t"><code>get_finding</code><b>Chi tiết một phát hiện</b></div>
        <div class="t"><code>query_raw_data</code><b>Tra cứu dữ liệu thô M15/16/tờ khai</b></div>
        <div class="t"><code>query_sql</code><b>Truy vấn tổng hợp (view theo quyền)</b></div>
        <div class="t"><code>list_companies</code><b>Liệt kê DN trong phạm vi</b></div>
        <div class="t"><code>get_legal_context</code><b>Trích dẫn TT 38/39/81</b></div>
        <div class="t"><code>explain_check</code><b>Giải thích một bài kiểm tra</b></div>
        <div class="t"><code>explain_score</code><b>Giải thích điểm rủi ro</b></div>
        <div class="t"><code>propose_check_run</code><b>Đề xuất chạy lại kiểm tra</b></div>
        <div class="t"><code>generate_report</code><b>Soạn báo cáo tổng hợp</b></div>
        <div class="t"><code>export_excel</code><b>Xuất báo cáo Excel mẫu</b></div>
        <div class="t"><code>export_query_excel</code><b>Xuất truy vấn tùy biến</b></div>
      </div>
    </div>

    <div class="split" style="margin-top:42px">
      <div>
        <figure class="shot"><div class="bar">audit-hq-demo.tinsu.ai/chat</div>
          <img loading="lazy" src="{{IMG:chat_tooluse}}" alt="Trợ lý trả lời kèm thẻ gọi công cụ"></figure>
        <div class="cap">Trả lời kèm thẻ công cụ <code>list_companies</code> bung ra đúng dữ liệu đã đọc.</div>
      </div>
      <div>
        <figure class="shot"><div class="bar">audit-hq-demo.tinsu.ai/chat</div>
          <img loading="lazy" src="{{IMG:chat_mention}}" alt="Nhắc nhanh doanh nghiệp và phát hiện"></figure>
        <div class="cap">Nhắc nhanh để đính kèm doanh nghiệp hoặc phát hiện vào câu hỏi.</div>
      </div>
    </div>
    <div style="margin-top:24px">
      <figure class="shot"><div class="bar">audit-hq-demo.tinsu.ai/admin/ai</div>
        <img loading="lazy" src="{{IMG:admin_ai}}" alt="Trang cấu hình và giám sát Trợ lý AI"></figure>
      <div class="cap">Quản trị AI: chọn mô hình (DeepSeek V4-Pro, dự phòng Gemini), đặt giới hạn gọi và ngân sách,
        bật guardrails, theo dõi token &amp; chi phí thực tế.</div>
    </div>
  </div>
</section>

<!-- ============ NẠP DỮ LIỆU ============ -->
<section id="ingest">
  <div class="wrap">
    <div class="split rev">
      <div class="txt">
        <div class="eyebrow">Onboarding thông minh</div>
        <h3>Nạp dữ liệu BCQT &amp; chẩn đoán file bằng AI</h3>
        <p>Tải lên 4 mẫu BCQT (Mẫu 15, 15a, 16 và tờ khai chi tiết). Hệ thống tự nhận dạng bố cục sheet,
          xử lý nhiều định dạng song song, và tách riêng bước nạp với bước chạy kiểm tra.</p>
        <ul>
          <li><b>AI chẩn đoán file lỗi:</b> khi cột lệch hay mẫu lạ, AI đọc trích đoạn sheet thật, đối chiếu schema mong đợi và diễn giải tiếng Việt kèm gợi ý sửa.</li>
          <li><b>Chuẩn hoá tên hàng:</b> tên nguyên vật liệu khai không nhất quán được chuẩn hoá (có cache và fallback heuristic) để đối chiếu chính xác hơn.</li>
          <li><b>Tự nhận loại hình DN</b> (SXXK / DNCX / Gia công) từ chính dữ liệu tờ khai — cán bộ không phải khai báo.</li>
          <li><b>Kiểm tra magic-byte:</b> chặn file đổi đuôi, giới hạn dung lượng và định dạng.</li>
        </ul>
      </div>
      <div>
        <figure class="shot"><div class="bar">audit-hq-demo.tinsu.ai/companies/…/upload</div>
          <img loading="lazy" src="{{IMG:upload}}" alt="Trang tải lên dữ liệu BCQT"></figure>
      </div>
    </div>
  </div>
</section>

<!-- ============ KIỂM TRA ============ -->
<section id="checks" class="alt">
  <div class="wrap">
    <div class="section-head">
      <div class="eyebrow">Lõi nghiệp vụ</div>
      <h2>16 bài kiểm tra tự động trong danh mục 49 kiểm tra</h2>
      <p class="lead">Hệ thống đối chiếu chéo giữa các mẫu BCQT và phân loại phát hiện theo ba mức rủi ro.</p>
    </div>
    <div class="legend">
      <span><i style="background:#c1272d"></i> Nghiêm trọng</span>
      <span><i style="background:#d97706"></i> Cảnh báo</span>
      <span><i style="background:#2563eb"></i> Thông tin</span>
    </div>
    <div class="chk">
      <div class="g"><h4><span class="gn">C1</span> Lệch số lượng</h4>
        <ul><li>Lệch số lượng nhập NVL (M15 ↔ tờ khai)</li><li>Lệch số lượng xuất TP (M15a ↔ tờ khai)</li>
        <li>Tờ khai có nhưng thiếu trong M15 và ngược lại</li><li>Chuyển mục đích sử dụng vượt ngưỡng / thiếu tờ khai A42</li></ul></div>
      <div class="g"><h4><span class="gn">C2</span> Cân đối kho</h4>
        <ul><li>Mất cân bằng phương trình kho NVL (M15)</li><li>Mất cân bằng phương trình kho TP (M15a)</li>
        <li>Tồn cuối nguyên vật liệu âm</li><li>Tồn cuối thành phẩm âm</li></ul></div>
      <div class="g"><h4><span class="gn">C3</span> Phân loại &amp; mã hàng</h4>
        <ul><li>Cùng mã vật tư khai nhiều loại hình mâu thuẫn</li><li>Mã HS không nhất quán trong kỳ</li>
        <li>Đơn vị tính không nhất quán</li></ul></div>
      <div class="g"><h4><span class="gn">C4–C6</span> Định mức &amp; liên kỳ</h4>
        <ul><li>NVL trong định mức M16 không có nguồn</li><li>Tổng tiêu hao M16 vượt xuất sản xuất M15</li>
        <li>NVL có xuất sản xuất nhưng không nhập, không tồn đầu</li><li>Tồn đầu kỳ N khác tồn cuối kỳ N−1</li></ul></div>
    </div>
    <div class="combo">
      <b>4 tổ hợp dấu hiệu rủi ro (meta-finding):</b> khi nhiều dấu hiệu bất thường cùng xuất hiện —
      ví dụ tồn âm kết hợp tiêu hao vượt định mức (nghi tạo định mức ảo), hoặc nhập không tờ khai kết hợp
      xuất không nguồn (nghi nguyên vật liệu nội địa lậu) — hệ thống nâng mức cảnh báo và cộng điểm tổ hợp.
    </div>
  </div>
</section>

<!-- ============ CHẤM ĐIỂM ============ -->
<section id="scoring">
  <div class="wrap">
    <div class="split">
      <div class="txt">
        <div class="eyebrow">Minh bạch</div>
        <h3>Chấm điểm rủi ro 0–1000 — giải thích được từng điểm</h3>
        <p>Điểm rủi ro không phải là tổng số phát hiện. Mỗi bài kiểm tra được chấm tối đa 10 điểm theo
          tỷ lệ giữa số phát hiện và quy mô dữ liệu của doanh nghiệp, cộng điểm tổ hợp, rồi quy về thang 0–1000.</p>
        <ul>
          <li><b>Rate-based, có trần:</b> sai lệch đủ nhiều thì bài đó "kịch khung" 10 điểm — không phình điểm theo số dòng.</li>
          <li><b>Bảng tính điểm chi tiết:</b> hiện công thức, điểm từng bài và mẫu số quy mô dữ liệu ngay trên trang DN.</li>
          <li><b>Năm hạng cảnh báo</b> phân tầng doanh nghiệp theo mức rủi ro dữ liệu.</li>
          <li>Là chỉ số rủi ro dữ liệu nội bộ — không phải đánh giá tuân thủ theo Thông tư 81/2019/TT-BTC.</li>
        </ul>
      </div>
      <div>
        <figure class="shot"><div class="bar">audit-hq-demo.tinsu.ai/companies/…?year=2022</div>
          <img loading="lazy" src="{{IMG:company_detail}}" alt="Trang doanh nghiệp với bảng tính điểm rủi ro"></figure>
        <div class="cap">Trang doanh nghiệp: điểm rủi ro theo năm kèm bảng giải thích cách tính.</div>
      </div>
    </div>
  </div>
</section>

<!-- ============ TRUY NGUỒN ============ -->
<section id="trace" class="alt">
  <div class="wrap">
    <div class="section-head">
      <div class="eyebrow">Không hộp đen</div>
      <h2>Mọi phát hiện truy được về dòng dữ liệu gốc</h2>
      <p class="lead">Từ một phát hiện, cán bộ bấm thẳng tới chứng cứ Tầng 1 — đúng dòng tờ khai, đúng mã
        hàng, đúng kỳ — để tự đối chiếu trước khi kết luận.</p>
    </div>
    <div class="split">
      <div>
        <figure class="shot"><div class="bar">audit-hq-demo.tinsu.ai/findings/1357</div>
          <img loading="lazy" src="{{IMG:finding}}" alt="Chi tiết phát hiện kèm chứng cứ truy nguồn"></figure>
        <div class="cap">Chi tiết phát hiện: mô tả nghiệp vụ kèm chứng cứ truy nguồn về đúng dòng tờ khai.</div>
      </div>
      <div>
        <figure class="shot"><div class="bar">audit-hq-demo.tinsu.ai/companies/…/items/…</div>
          <img loading="lazy" src="{{IMG:item}}" alt="Trang chi tiết mã hàng với cân đối kho"></figure>
        <div class="cap">Trang mã hàng: cân đối kho, giao dịch tờ khai và dòng đi vào thành phẩm.</div>
      </div>
    </div>
  </div>
</section>

<!-- ============ PHÂN QUYỀN ============ -->
<section id="govern">
  <div class="wrap">
    <div class="section-head">
      <div class="eyebrow">Sẵn sàng dùng nội bộ</div>
      <h2>Phân quyền theo doanh nghiệp &amp; nhật ký truy cập</h2>
      <p class="lead">Mỗi cán bộ được phân công một số doanh nghiệp; doanh nghiệp ngoài phạm vi đơn giản
        là "không tồn tại" với cán bộ đó. Ranh giới này áp dụng cho cả Trợ lý AI.</p>
    </div>
    <div class="cards" style="margin-bottom:34px">
      <div class="card"><h4>Cô lập dữ liệu</h4>
        <p>Hai vai trò quản trị / cán bộ. Cưỡng chế ở mọi lối vào phía máy chủ — ẩn menu không phải là bảo mật thật.</p></div>
      <div class="card"><h4>AI cùng ranh giới quyền</h4>
        <p>Công cụ AI bị giới hạn theo đúng DN được phân công; truy vấn chạy trên view đã lọc sẵn — không lách được.</p></div>
      <div class="card"><h4>Nhật ký truy cập</h4>
        <p>Ghi lại tải file, xuất báo cáo, xuất truy vấn, chạy kiểm tra — kèm giới hạn đăng nhập chống dò mật khẩu.</p></div>
    </div>
    <div class="split">
      <div>
        <figure class="shot"><div class="bar">audit-hq-demo.tinsu.ai/admin/audit</div>
          <img loading="lazy" src="{{IMG:access_audit}}" alt="Nhật ký truy cập"></figure>
        <div class="cap">Nhật ký truy cập — ai làm gì, trên doanh nghiệp nào, lúc nào.</div>
      </div>
      <div>
        <figure class="shot"><div class="bar">audit-hq-demo.tinsu.ai/companies</div>
          <img loading="lazy" src="{{IMG:permissions}}" alt="Cán bộ chỉ thấy doanh nghiệp được phân công"></figure>
        <div class="cap">Góc nhìn cán bộ — chỉ thấy doanh nghiệp trong phạm vi được giao.</div>
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
        <h3>Tài liệu pháp lý &amp; phương pháp luận đi kèm</h3>
        <p>Hệ thống tích hợp sẵn các văn bản nền tảng và bản giải thích cách tính điểm, để cán bộ và
          doanh nghiệp cùng hiểu mỗi phát hiện dựa trên căn cứ nào.</p>
        <ul>
          <li><b>Phương pháp tính điểm rủi ro</b> — công thức rate-based và năm hạng cảnh báo.</li>
          <li><b>TT 38/2015, TT 39/2018</b> — thủ tục hải quan, định nghĩa BCQT, mã loại hình, cân đối kho.</li>
          <li><b>TT 81/2019</b> — quản lý rủi ro nghiệp vụ hải quan (mức tuân thủ và hạng rủi ro của TCHQ).</li>
        </ul>
        <p style="margin-top:18px;font-size:14px;color:var(--muted)"><b style="color:var(--navy)">Nền tảng kỹ thuật:</b>
          Python 3.12 · FastAPI · SQLAlchemy + Alembic · pandas/openpyxl · hàng đợi công việc chạy nền · giao diện server-side gọn nhẹ.</p>
      </div>
      <div>
        <figure class="shot"><div class="bar">audit-hq-demo.tinsu.ai/tai-lieu</div>
          <img loading="lazy" src="{{IMG:docs}}" alt="Thư viện tài liệu"></figure>
        <div class="cap">Thư viện tài liệu pháp lý và phương pháp luận tích hợp sẵn.</div>
      </div>
    </div>
  </div>
</section>

<div class="cta-band"><div class="wrap">
  <h2>Trải nghiệm trực tiếp trên dữ liệu mẫu</h2>
  <p>Toàn bộ tính năng ở trên đang chạy trên bản demo công khai với dữ liệu đã ẩn danh.</p>
  <a class="btn btn-primary" href="https://audit-hq-demo.tinsu.ai" target="_blank" rel="noopener">Mở Audit-HQ demo</a>
</div></div>

<footer><div class="wrap">
  <div class="cols">
    <div>
      <h4>AUDIT-HQ</h4>
      <div>Hệ thống Quản lý Rủi ro Báo cáo Quyết toán hải quan.</div>
      <div style="margin-top:8px"><a href="https://audit-hq-demo.tinsu.ai" target="_blank" rel="noopener">audit-hq-demo.tinsu.ai</a></div>
    </div>
    <div>
      <h4>THỰC HIỆN</h4>
      <div>Tinsu AI × Trọng Tín</div>
      <div style="margin-top:8px;color:#7e93a8">Bản dùng cho thí điểm</div>
    </div>
  </div>
  <div class="disclaimer">
    Chỉ số rủi ro trên hệ thống là chỉ số rủi ro dữ liệu BCQT (chênh lệch nội bộ giữa Mẫu 15/15a/16 và
    đối chiếu tờ khai), <b style="color:#cdd9e5">không phải</b> đánh giá tuân thủ pháp luật theo Thông tư
    81/2019/TT-BTC. Phân loại tuân thủ chính thức thuộc thẩm quyền Tổng cục Hải quan. Mọi quyết định cuối
    cùng thuộc thẩm quyền cán bộ. Toàn bộ số liệu minh hoạ đã được ẩn danh, không phản ánh doanh nghiệp có thật.
  </div>
</div></footer>

<div id="lb"><img alt=""></div>
<script>
(function(){
  var lb=document.getElementById('lb'),lbimg=lb.querySelector('img');
  document.querySelectorAll('.shot img,.hero-shot img').forEach(function(im){
    im.style.cursor='zoom-in';
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
