"""Dựng trang showcase tính năng (self-contained HTML, ảnh nhúng base64).

Tự lập (reproducible) từ ảnh PNG đã commit: nén PNG → JPEG (ImageMagick `convert`),
nhúng base64 vào template, ghi ra app/static/showcase.html. Route public `/showcase`
(app/main.py) phục vụ file này.

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
HERE = Path(__file__).resolve().parent
SHOTS = HERE / "screenshots"
CHAT = ROOT / ".ai" / "features" / "2026-06-14-chat-redesign" / "screenshots"
PERM = ROOT / ".ai" / "features" / "2026-06-14-permissions-auth-and-chat" / "screenshots"
OUT = ROOT / "app" / "static" / "showcase.html"

# key → (png nguồn, bề rộng tối đa px, JPEG quality). Bề rộng/quality cân giữa
# độ nét chữ và dung lượng file (HTML self-contained ~3 MB).
SOURCES: dict[str, tuple[Path, int, int]] = {
    "overview": (SHOTS / "01_overview.png", 1240, 86),
    "chat_tooluse": (CHAT / "02_tool_pill_expanded.png", 1240, 86),
    "chat_mention": (CHAT / "04_mention_dropdown.png", 1240, 86),
    "admin_ai": (SHOTS / "07_admin_ai.png", 1080, 86),
    "upload": (SHOTS / "10_upload.png", 1100, 86),
    "catalog": (SHOTS / "05_catalog.png", 980, 79),
    "company_detail": (SHOTS / "02_company_detail.png", 1100, 86),
    "finding": (SHOTS / "03_finding_traceability.png", 1200, 86),
    "item": (SHOTS / "04_item_detail.png", 1200, 86),
    "access_audit": (PERM / "05_auth_access_audit.png", 1200, 86),
    "permissions": (PERM / "01_permissions_officer_scoped.png", 1240, 86),
    "docs": (SHOTS / "08_docs_index.png", 1100, 86),
    "scoring_doc": (SHOTS / "09_scoring_methodology.png", 960, 80),
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
<title>Audit-HQ — Hệ thống Quản lý Rủi ro BCQT cho Hải quan</title>
<meta name="description" content="Audit-HQ tự động đối chiếu Báo cáo Quyết toán hải quan (BCQT), chấm điểm rủi ro minh bạch và có Trợ lý AI dẫn nguồn. Sản phẩm Tinsu AI × Trọng Tín.">
<meta property="og:title" content="Audit-HQ — Quản lý Rủi ro BCQT cho Hải quan">
<meta property="og:description" content="16 bài kiểm tra tự động, chấm điểm rủi ro 0–1000 minh bạch, truy nguồn 100% và Trợ lý AI dẫn nguồn.">
<style>
:root{
  --navy:#1d3557; --navy-deep:#14213a; --blue:#2563eb; --blue-soft:#dbeafe;
  --gold:#d97706; --gold-soft:#fef3c7; --red:#c1272d;
  --green:#166534; --green-soft:#dcfce7;
  --ink:#1f2937; --muted:#6b7280; --line:#e5e7eb; --bg:#f7f8fa; --card:#fff;
  --radius:14px; --shadow:0 1px 3px rgba(16,24,40,.06),0 8px 24px rgba(16,24,40,.06);
  --maxw:1120px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;font-family:"Be Vietnam Pro","Inter",-apple-system,"Segoe UI",Roboto,system-ui,sans-serif;
  color:var(--ink);background:var(--bg);line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:var(--blue);text-decoration:none}
a:hover{text-decoration:underline}
h1,h2,h3,h4{margin:0;line-height:1.25;font-weight:700;color:#0f172a}
p{margin:0 0 1em}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 22px}
.eyebrow{font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--blue)}

/* top nav */
.nav{position:sticky;top:0;z-index:50;background:rgba(20,33,58,.92);backdrop-filter:blur(8px);
  border-bottom:1px solid rgba(255,255,255,.08)}
.nav .wrap{display:flex;align-items:center;gap:18px;height:60px}
.nav .logo{display:flex;align-items:center;gap:10px;color:#fff;font-weight:800;font-size:18px}
.nav .logo .mark{width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,#2563eb,#60a5fa);
  display:grid;place-items:center;color:#fff;font-weight:900}
.nav .links{display:flex;gap:20px;margin-left:auto}
.nav .links a{color:#cbd5e1;font-size:14px;font-weight:500}
.nav .links a:hover{color:#fff;text-decoration:none}
.nav .cta{background:#fff;color:var(--navy);padding:8px 16px;border-radius:9px;font-weight:700;font-size:14px}
.nav .cta:hover{text-decoration:none;background:#f1f5f9}
@media(max-width:860px){.nav .links{display:none}}

/* hero */
.hero{background:radial-gradient(1200px 500px at 78% -10%,rgba(37,99,235,.35),transparent 60%),
  linear-gradient(160deg,#14213a 0%,#1d3557 60%,#24426b 100%);color:#fff;padding:78px 0 64px}
.hero .badge{display:inline-flex;align-items:center;gap:8px;background:rgba(255,255,255,.12);
  border:1px solid rgba(255,255,255,.18);padding:6px 14px;border-radius:999px;font-size:13px;font-weight:600;margin-bottom:22px}
.hero h1{font-size:46px;font-weight:800;letter-spacing:-.02em;max-width:880px}
.hero .sub{font-size:19px;color:#cbd5e1;max-width:680px;margin:18px 0 30px}
.hero .actions{display:flex;gap:14px;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;gap:8px;padding:13px 22px;border-radius:11px;font-weight:700;font-size:15px}
.btn-primary{background:#fff;color:var(--navy)}
.btn-primary:hover{text-decoration:none;background:#eef2f7}
.btn-ghost{background:rgba(255,255,255,.10);color:#fff;border:1px solid rgba(255,255,255,.25)}
.btn-ghost:hover{text-decoration:none;background:rgba(255,255,255,.18)}
.hero .note{margin-top:26px;font-size:13.5px;color:#93a4bd;display:flex;align-items:center;gap:8px}
@media(max-width:680px){.hero h1{font-size:33px}.hero{padding:54px 0 44px}}

/* stats */
.stats{background:var(--navy-deep);color:#fff;border-top:1px solid rgba(255,255,255,.08);padding:30px 0}
.stats .grid{display:grid;grid-template-columns:repeat(5,1fr);gap:18px;text-align:center}
.stats .n{font-size:30px;font-weight:800;color:#fff}
.stats .l{font-size:12.5px;color:#9fb0c9;margin-top:2px}
@media(max-width:760px){.stats .grid{grid-template-columns:repeat(2,1fr);gap:24px}}

/* sections */
section{padding:72px 0}
.section-head{max-width:760px;margin-bottom:40px}
.section-head h2{font-size:32px;letter-spacing:-.01em}
.section-head .lead{font-size:18px;color:var(--muted);margin-top:12px}
.alt{background:#fff;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}

.split{display:grid;grid-template-columns:1fr 1fr;gap:44px;align-items:center}
.split.rev .txt{order:2}
@media(max-width:880px){.split{grid-template-columns:1fr;gap:28px}.split.rev .txt{order:0}}
.txt h3{font-size:23px;margin-bottom:12px}
.txt ul{margin:14px 0 0;padding:0;list-style:none}
.txt li{position:relative;padding-left:28px;margin-bottom:11px;color:#374151}
.txt li:before{content:"";position:absolute;left:2px;top:9px;width:8px;height:8px;border-radius:50%;
  background:var(--blue)}
.txt li b{color:#0f172a}

/* browser frame */
.frame{background:#fff;border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden}
.frame .bar{display:flex;align-items:center;gap:7px;padding:10px 14px;background:#f1f3f6;border-bottom:1px solid var(--line)}
.frame .dot{width:11px;height:11px;border-radius:50%}
.frame .dot.r{background:#ef6a5e}.frame .dot.y{background:#f4be4f}.frame .dot.g{background:#62c554}
.frame .url{margin-left:10px;font-size:12px;color:#7a8699;background:#fff;border:1px solid var(--line);
  border-radius:7px;padding:4px 12px;font-family:"JetBrains Mono",monospace;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.frame img{display:block;width:100%;cursor:zoom-in}
.cap{font-size:13px;color:var(--muted);margin-top:10px;text-align:center}

/* AI band */
.ai-band{background:linear-gradient(160deg,#101b30,#1b2f52);color:#fff}
.ai-band .section-head h2,.ai-band .txt h3{color:#fff}
.ai-band .section-head .lead{color:#aebfd8}
.ai-pill-row{display:flex;flex-wrap:wrap;gap:9px;margin:26px 0 8px}
.ai-pill{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.08);
  border:1px solid rgba(255,255,255,.16);border-radius:999px;padding:7px 14px;font-size:13.5px;color:#e2e8f0;font-weight:500}
.ai-pill code{font-family:"JetBrains Mono",monospace;font-size:12px;color:#93c5fd;background:none}
.feat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:14px}
@media(max-width:880px){.feat-grid{grid-template-columns:1fr}}
.feat{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:13px;padding:22px}
.feat .ic{font-size:24px;margin-bottom:10px}
.feat h4{color:#fff;font-size:16.5px;margin-bottom:6px}
.feat p{color:#aebfd8;font-size:14px;margin:0}
.ai-shots{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:40px}
@media(max-width:880px){.ai-shots{grid-template-columns:1fr}}
.ai-shots .full{grid-column:1/-1}

/* feature cards generic */
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
@media(max-width:880px){.cards{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:24px;box-shadow:var(--shadow)}
.card .ic{font-size:26px;margin-bottom:12px}
.card h4{font-size:17px;margin-bottom:7px}
.card p{color:var(--muted);font-size:14.5px;margin:0}

.tag{display:inline-block;background:var(--blue-soft);color:#1e40af;border-radius:7px;padding:3px 10px;
  font-size:12.5px;font-weight:700;margin-bottom:14px}
.tag.gold{background:var(--gold-soft);color:#92400e}
.tag.green{background:var(--green-soft);color:#166534}

/* checks groups */
.chk{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:8px}
@media(max-width:760px){.chk{grid-template-columns:1fr}}
.chk .g{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px 20px}
.chk .g h4{font-size:15.5px;display:flex;align-items:center;gap:8px;margin-bottom:8px}
.chk .g .gn{background:var(--navy);color:#fff;width:26px;height:26px;border-radius:7px;display:grid;place-items:center;font-size:13px}
.chk .g ul{margin:0;padding-left:18px;color:#475467;font-size:13.5px}
.chk .g li{margin-bottom:4px}
.combo{margin-top:18px;background:var(--gold-soft);border:1px solid #fcd99a;border-radius:12px;padding:18px 20px}
.combo b{color:#92400e}

/* footer */
footer{background:var(--navy-deep);color:#cbd5e1;padding:48px 0 40px;font-size:14px}
footer .wrap{display:flex;flex-wrap:wrap;gap:30px;justify-content:space-between}
footer h4{color:#fff;font-size:15px;margin-bottom:12px}
footer a{color:#cbd5e1}
.disclaimer{margin-top:30px;padding-top:22px;border-top:1px solid rgba(255,255,255,.1);
  color:#8a9bb5;font-size:12.5px;max-width:820px}

/* lightbox */
#lb{position:fixed;inset:0;background:rgba(8,12,22,.92);display:none;z-index:200;
  align-items:flex-start;justify-content:center;padding:30px;overflow:auto;cursor:zoom-out}
#lb.on{display:flex}
#lb img{max-width:1100px;width:100%;height:auto;border-radius:10px;box-shadow:0 20px 60px rgba(0,0,0,.5)}
</style>
</head>
<body>

<nav class="nav"><div class="wrap">
  <div class="logo"><span class="mark">A</span> Audit-HQ</div>
  <div class="links">
    <a href="#ai">Trợ lý AI</a>
    <a href="#ingest">Nạp dữ liệu</a>
    <a href="#checks">Kiểm tra</a>
    <a href="#scoring">Chấm điểm</a>
    <a href="#trace">Truy nguồn</a>
    <a href="#govern">Phân quyền</a>
  </div>
  <a class="cta" href="https://audit-hq-demo.tinsu.ai" target="_blank" rel="noopener">Mở demo →</a>
</div></nav>

<header class="hero"><div class="wrap">
  <span class="badge">⚡ Tinsu AI × Trọng Tín · Bản thí điểm</span>
  <h1>Quản lý rủi ro Báo cáo Quyết toán hải quan — tự động, minh bạch, có Trợ lý AI.</h1>
  <p class="sub">Audit-HQ đối chiếu chéo M15 / M15a / M16 / tờ khai BCCT, phát hiện sai lệch theo
    bộ quy tắc nghiệp vụ, chấm điểm rủi ro từng doanh nghiệp và để cán bộ hỏi đáp bằng
    một Trợ lý AI luôn dẫn nguồn về dòng dữ liệu gốc.</p>
  <div class="actions">
    <a class="btn btn-primary" href="https://audit-hq-demo.tinsu.ai" target="_blank" rel="noopener">🔎 Mở demo trực tiếp</a>
    <a class="btn btn-ghost" href="#ai">🤖 Xem Trợ lý AI</a>
  </div>
  <div class="note">🟢 Toàn bộ số liệu minh hoạ là <b style="color:#cbd5e1;margin:0 4px">dữ liệu mẫu đã ẩn danh</b> — không phản ánh doanh nghiệp có thật.</div>
</div></header>

<div class="stats"><div class="wrap"><div class="grid">
  <div><div class="n">16</div><div class="l">bài kiểm tra tự động</div></div>
  <div><div class="n">12</div><div class="l">công cụ của Trợ lý AI</div></div>
  <div><div class="n">0–1000</div><div class="l">thang điểm rủi ro</div></div>
  <div><div class="n">100%</div><div class="l">phát hiện truy được nguồn</div></div>
  <div><div class="n">4</div><div class="l">tổ hợp dấu hiệu rủi ro</div></div>
</div></div></div>

<!-- ===================== AI ASSISTANT (trọng tâm) ===================== -->
<section id="ai" class="ai-band">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow" style="color:#7dd3fc">Tính năng nổi bật</span>
      <h2>Trợ lý AI — hỏi đáp dữ liệu BCQT, luôn dẫn nguồn</h2>
      <p class="lead">Không phải chatbot trả lời chung chung. Trợ lý gọi <b style="color:#fff">12 công cụ chỉ-đọc</b>
        trực tiếp trên cơ sở dữ liệu, trích dẫn từng phát hiện / dòng dữ liệu, và tôn trọng đúng
        phạm vi doanh nghiệp mà cán bộ được phân công.</p>
    </div>

    <div class="feat-grid">
      <div class="feat"><div class="ic">🔗</div><h4>Trả lời có dẫn nguồn</h4>
        <p>Mọi con số đều kèm trích dẫn bấm được tới phát hiện, dòng M15/BCCT hay điều khoản pháp lý — không có "hộp đen".</p></div>
      <div class="feat"><div class="ic">🛠️</div><h4>Gọi công cụ minh bạch</h4>
        <p>Mỗi lần tra cứu hiện một thẻ gọn (✓ tên công cụ); bấm để xem đúng dữ liệu công cụ đã đọc.</p></div>
      <div class="feat"><div class="ic">🧮</div><h4>Truy vấn SQL an toàn</h4>
        <p>Trợ lý tự viết SELECT để tổng hợp/đếm/so sánh nhiều DN, nhưng chỉ chạy trên view đã giới hạn theo quyền.</p></div>
      <div class="feat"><div class="ic">@</div><h4>Nhắc thực thể</h4>
        <p>Gõ <code>@</code> để chèn nhanh doanh nghiệp hoặc phát hiện vào câu hỏi, đính kèm đúng ngữ cảnh.</p></div>
      <div class="feat"><div class="ic">📝</div><h4>Soạn báo cáo & xuất Excel</h4>
        <p>Yêu cầu Trợ lý tổng hợp báo cáo hoặc xuất kết quả truy vấn ra Excel kèm liên kết tải.</p></div>
      <div class="feat"><div class="ic">🧭</div><h4>Con người quyết định</h4>
        <p>Trợ lý chỉ <b style="color:#fff">đề xuất</b> chạy lại kiểm tra; việc xác nhận / bác bỏ phát hiện luôn thuộc cán bộ.</p></div>
    </div>

    <div class="ai-pill-row">
      <span class="ai-pill">🔎 <code>search_findings</code></span>
      <span class="ai-pill">📄 <code>get_finding</code></span>
      <span class="ai-pill">📊 <code>query_raw_data</code></span>
      <span class="ai-pill">🧮 <code>query_sql</code></span>
      <span class="ai-pill">🏢 <code>list_companies</code></span>
      <span class="ai-pill">⚖️ <code>get_legal_context</code></span>
      <span class="ai-pill">📘 <code>explain_check</code></span>
      <span class="ai-pill">🎯 <code>explain_score</code></span>
      <span class="ai-pill">▶️ <code>propose_check_run</code></span>
      <span class="ai-pill">📑 <code>generate_report</code></span>
      <span class="ai-pill">📥 <code>export_excel</code></span>
      <span class="ai-pill">📤 <code>export_query_excel</code></span>
    </div>

    <div class="ai-shots">
      <div>
        <div class="frame">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
            <span class="url">audit-hq-demo.tinsu.ai/chat</span></div>
          <img loading="lazy" src="{{IMG:chat_tooluse}}" alt="Trợ lý AI trả lời kèm thẻ gọi công cụ và dẫn nguồn">
        </div>
        <div class="cap" style="color:#9fb0c9">Trả lời "Top 3 DN rủi ro" kèm thẻ công cụ <code>list_companies</code> bung ra đúng dữ liệu đã đọc.</div>
      </div>
      <div>
        <div class="frame">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
            <span class="url">audit-hq-demo.tinsu.ai/chat</span></div>
          <img loading="lazy" src="{{IMG:chat_mention}}" alt="Gõ @ để nhắc doanh nghiệp hoặc phát hiện">
        </div>
        <div class="cap" style="color:#9fb0c9">Gõ <code>@</code> ra danh sách doanh nghiệp &amp; phát hiện để đính kèm ngữ cảnh.</div>
      </div>
      <div class="full">
        <div class="frame">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
            <span class="url">audit-hq-demo.tinsu.ai/admin/ai</span></div>
          <img loading="lazy" src="{{IMG:admin_ai}}" alt="Trang cấu hình & giám sát Trợ lý AI">
        </div>
        <div class="cap" style="color:#9fb0c9">Quản trị AI: chọn mô hình (DeepSeek V4-Pro, dự phòng Gemini), đặt giới hạn gọi/ngân sách,
          bật guardrails và theo dõi token &amp; chi phí thực tế.</div>
      </div>
    </div>
  </div>
</section>

<!-- ===================== NẠP DỮ LIỆU THÔNG MINH ===================== -->
<section id="ingest">
  <div class="wrap">
    <div class="split rev">
      <div class="txt">
        <span class="tag gold">Thông minh khi onboarding</span>
        <h3>Nạp dữ liệu BCQT &amp; chẩn đoán file bằng AI</h3>
        <p>Kéo–thả 4 mẫu BCQT (Mẫu 15, 15a, 16 và tờ khai chi tiết BCCT). Hệ thống tự nhận dạng
          bố cục sheet, xử lý nhiều định dạng song song và <b>tách riêng bước nạp với bước chạy kiểm tra</b>.</p>
        <ul>
          <li><b>AI chẩn đoán file lỗi:</b> khi cột lệch hay mẫu lạ, AI đọc trích đoạn sheet thật, đối chiếu schema mong đợi và <b>diễn giải tiếng Việt + gợi ý sửa</b>.</li>
          <li><b>Chuẩn hoá tên hàng:</b> tên nguyên vật liệu khai không nhất quán được chuẩn hoá (có cache + fallback heuristic), giúp đối chiếu chính xác hơn.</li>
          <li><b>Tự nhận loại hình DN</b> (SXXK / DNCX / Gia công) từ chính dữ liệu tờ khai — cán bộ không phải khai báo.</li>
          <li><b>Kiểm tra magic-byte:</b> chặn file đổi đuôi, giới hạn dung lượng &amp; định dạng.</li>
        </ul>
      </div>
      <div>
        <div class="frame">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
            <span class="url">audit-hq-demo.tinsu.ai/companies/…/upload</span></div>
          <img loading="lazy" src="{{IMG:upload}}" alt="Trang tải lên dữ liệu BCQT">
        </div>
      </div>
    </div>
  </div>
</section>

<!-- ===================== KIỂM TRA TỰ ĐỘNG ===================== -->
<section id="checks" class="alt">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Lõi nghiệp vụ</span>
      <h2>16 bài kiểm tra tự động trong danh mục 49 kiểm tra</h2>
      <p class="lead">Mỗi phát hiện được phân loại 3 mức — <b style="color:var(--red)">Nghiêm trọng</b>,
        <b style="color:var(--gold)">Cảnh báo</b>, <b style="color:var(--blue)">Thông tin</b> —
        và đối chiếu chéo giữa các mẫu BCQT.</p>
    </div>
    <div class="chk">
      <div class="g"><h4><span class="gn">C1</span> Lệch số lượng</h4>
        <ul><li>Lệch số lượng nhập NVL (M15 ↔ tờ khai)</li><li>Lệch số lượng xuất TP (M15a ↔ tờ khai)</li>
        <li>Tờ khai có nhưng thiếu trong M15 / ngược lại</li><li>Chuyển mục đích sử dụng vượt ngưỡng / thiếu tờ khai A42</li></ul></div>
      <div class="g"><h4><span class="gn">C2</span> Cân đối kho</h4>
        <ul><li>Mất cân bằng phương trình kho NVL (M15)</li><li>Mất cân bằng phương trình kho TP (M15a)</li>
        <li>Tồn cuối NVL âm</li><li>Tồn cuối thành phẩm âm</li></ul></div>
      <div class="g"><h4><span class="gn">C3</span> Phân loại &amp; mã hàng</h4>
        <ul><li>Cùng mã vật tư khai nhiều loại hình mâu thuẫn</li><li>Mã HS không nhất quán trong kỳ</li>
        <li>Đơn vị tính không nhất quán</li></ul></div>
      <div class="g"><h4><span class="gn">C4–C6</span> Định mức &amp; liên kỳ</h4>
        <ul><li>NVL trong định mức M16 không có nguồn</li><li>Tổng tiêu hao M16 vượt xuất sản xuất M15</li>
        <li>NVL có xuất SX nhưng không nhập, không tồn đầu</li><li>Tồn đầu kỳ N khác tồn cuối kỳ N−1</li></ul></div>
    </div>
    <div class="combo">
      <b>🧩 4 tổ hợp dấu hiệu rủi ro (meta-finding):</b> khi nhiều dấu hiệu bất thường cùng xuất hiện
      — ví dụ <i>tồn âm + tiêu hao vượt định mức</i> (nghi tạo định mức ảo), hay <i>nhập không tờ khai +
      xuất không nguồn</i> (nghi NVL nội địa lậu) — hệ thống nâng mức cảnh báo và cộng điểm tổ hợp.
    </div>
    <div style="margin-top:34px">
      <div class="frame">
        <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
          <span class="url">audit-hq-demo.tinsu.ai/danh-muc-kiem-tra</span></div>
        <img loading="lazy" src="{{IMG:catalog}}" alt="Danh mục đầy đủ các bài kiểm tra">
      </div>
      <div class="cap">Danh mục kiểm tra đầy đủ — bài đã triển khai trong MVP được đánh dấu rõ.</div>
    </div>
  </div>
</section>

<!-- ===================== CHẤM ĐIỂM ===================== -->
<section id="scoring">
  <div class="wrap">
    <div class="split">
      <div class="txt">
        <span class="tag">Minh bạch</span>
        <h3>Chấm điểm rủi ro 0–1000 — giải thích được từng điểm</h3>
        <p>Điểm rủi ro <b>không</b> phải là tổng số phát hiện. Mỗi bài kiểm tra chấm tối đa 10 điểm
          theo <b>tỷ lệ</b> giữa số phát hiện và quy mô dữ liệu của doanh nghiệp, cộng điểm tổ hợp, rồi quy về thang 0–1000.</p>
        <ul>
          <li><b>Rate-based, có trần:</b> sai lệch đủ nhiều thì bài đó "kịch khung" 10 điểm — không phình điểm theo số dòng.</li>
          <li><b>Bảng tính điểm chi tiết:</b> hiện công thức, điểm từng bài và mẫu số quy mô dữ liệu ngay trên trang DN.</li>
          <li><b>5 hạng cảnh báo</b> phân tầng doanh nghiệp theo mức rủi ro dữ liệu.</li>
          <li>Là <b>chỉ số rủi ro dữ liệu</b> nội bộ — không phải đánh giá tuân thủ theo TT 81/2019/TT-BTC.</li>
        </ul>
      </div>
      <div>
        <div class="frame">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
            <span class="url">audit-hq-demo.tinsu.ai/companies/…?year=2022</span></div>
          <img loading="lazy" src="{{IMG:company_detail}}" alt="Trang doanh nghiệp với bảng tính điểm rủi ro">
        </div>
        <div class="cap">Trang doanh nghiệp: điểm rủi ro theo năm + bảng giải thích cách tính.</div>
      </div>
    </div>
  </div>
</section>

<!-- ===================== TRUY NGUỒN ===================== -->
<section id="trace" class="alt">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Không hộp đen</span>
      <h2>Mọi phát hiện truy được về dòng dữ liệu gốc</h2>
      <p class="lead">Từ một phát hiện, cán bộ bấm thẳng tới chứng cứ Tầng 1 — đúng dòng tờ khai,
        đúng mã hàng, đúng kỳ — để tự đối chiếu trước khi kết luận.</p>
    </div>
    <div class="split">
      <div>
        <div class="frame">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
            <span class="url">audit-hq-demo.tinsu.ai/findings/1357</span></div>
          <img loading="lazy" src="{{IMG:finding}}" alt="Chi tiết phát hiện kèm chứng cứ truy nguồn">
        </div>
        <div class="cap">Chi tiết phát hiện: mô tả nghiệp vụ + chứng cứ truy nguồn về đúng dòng tờ khai.</div>
      </div>
      <div>
        <div class="frame">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
            <span class="url">audit-hq-demo.tinsu.ai/companies/…/items/…</span></div>
          <img loading="lazy" src="{{IMG:item}}" alt="Trang chi tiết mã hàng với cân đối kho">
        </div>
        <div class="cap">Trang mã hàng: cân đối kho, giao dịch BCCT và dòng đi vào thành phẩm.</div>
      </div>
    </div>
  </div>
</section>

<!-- ===================== TỔNG QUAN ===================== -->
<section id="overview">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Toàn cảnh</span>
      <h2>Bảng tổng quan xếp hạng theo rủi ro</h2>
      <p class="lead">Một màn hình để xem nhanh doanh nghiệp nào cần ưu tiên — sắp xếp theo điểm,
        lọc theo hạng, hiện số phát hiện theo mức.</p>
    </div>
    <div class="frame">
      <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
        <span class="url">audit-hq-demo.tinsu.ai/companies</span></div>
      <img loading="lazy" src="{{IMG:overview}}" alt="Bảng tổng quan doanh nghiệp theo điểm rủi ro">
    </div>
  </div>
</section>

<!-- ===================== PHÂN QUYỀN & BẢO MẬT ===================== -->
<section id="govern" class="alt">
  <div class="wrap">
    <div class="section-head">
      <span class="eyebrow">Sẵn sàng dùng nội bộ</span>
      <h2>Phân quyền theo doanh nghiệp &amp; nhật ký truy cập</h2>
      <p class="lead">Mô hình nội bộ: mỗi cán bộ được phân công một số doanh nghiệp; doanh nghiệp ngoài
        phạm vi đơn giản là "không tồn tại" với cán bộ đó. Ranh giới này áp dụng <b>cho cả Trợ lý AI</b>.</p>
    </div>
    <div class="cards" style="margin-bottom:34px">
      <div class="card"><div class="ic">🔐</div><h4>Cô lập dữ liệu thật</h4>
        <p>Hai vai trò admin / cán bộ. Cưỡng chế ở mọi lối vào phía máy chủ — ẩn nav không phải bảo mật thật.</p></div>
      <div class="card"><div class="ic">🤖</div><h4>AI cùng ranh giới quyền</h4>
        <p>Công cụ AI bị giới hạn theo đúng DN được phân công; truy vấn SQL chạy trên view đã lọc sẵn — không lách được.</p></div>
      <div class="card"><div class="ic">🧾</div><h4>Nhật ký truy cập</h4>
        <p>Ghi lại tải file, xuất báo cáo, xuất truy vấn, chạy kiểm tra — kèm rate-limit đăng nhập chống dò mật khẩu.</p></div>
    </div>
    <div class="split">
      <div>
        <div class="frame">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
            <span class="url">audit-hq-demo.tinsu.ai/admin/audit</span></div>
          <img loading="lazy" src="{{IMG:access_audit}}" alt="Nhật ký truy cập">
        </div>
        <div class="cap">Nhật ký truy cập — ai làm gì, trên DN nào, lúc nào.</div>
      </div>
      <div>
        <div class="frame">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
            <span class="url">audit-hq-demo.tinsu.ai/companies</span></div>
          <img loading="lazy" src="{{IMG:permissions}}" alt="Cán bộ chỉ thấy doanh nghiệp được phân công">
        </div>
        <div class="cap">Góc nhìn cán bộ — chỉ thấy doanh nghiệp trong phạm vi được giao.</div>
      </div>
    </div>
  </div>
</section>

<!-- ===================== TÀI LIỆU & NỀN TẢNG ===================== -->
<section id="docs">
  <div class="wrap">
    <div class="split rev">
      <div class="txt">
        <span class="tag green">Có căn cứ</span>
        <h3>Tài liệu pháp lý &amp; phương pháp luận đi kèm</h3>
        <p>Hệ thống tích hợp sẵn các văn bản nền tảng và bản giải thích cách tính điểm, để cán bộ và
          doanh nghiệp cùng hiểu mỗi phát hiện dựa trên căn cứ nào.</p>
        <ul>
          <li><b>Phương pháp tính điểm rủi ro</b> — công thức rate-based &amp; 5 hạng cảnh báo.</li>
          <li><b>TT 38/2015, TT 39/2018</b> — thủ tục hải quan, định nghĩa BCQT, mã loại hình, cân đối kho.</li>
          <li><b>TT 81/2019</b> — quản lý rủi ro nghiệp vụ hải quan (mức tuân thủ &amp; hạng rủi ro của TCHQ).</li>
        </ul>
        <p style="margin-top:18px;font-size:14px;color:var(--muted)">
          <b>Nền tảng kỹ thuật:</b> Python 3.12 · FastAPI · SQLAlchemy + Alembic · pandas/openpyxl ·
          hàng đợi công việc chạy nền · giao diện server-side gọn nhẹ.</p>
      </div>
      <div>
        <div class="frame">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
            <span class="url">audit-hq-demo.tinsu.ai/tai-lieu</span></div>
          <img loading="lazy" src="{{IMG:docs}}" alt="Trang tài liệu">
        </div>
        <div class="cap">Thư viện tài liệu pháp lý &amp; phương pháp luận tích hợp sẵn.</div>
      </div>
    </div>
  </div>
</section>

<!-- ===================== CTA ===================== -->
<section class="alt" style="text-align:center;padding:64px 0">
  <div class="wrap">
    <h2 style="font-size:30px">Trải nghiệm trực tiếp trên dữ liệu mẫu</h2>
    <p class="lead" style="margin:14px auto 28px;max-width:620px;color:var(--muted)">
      Toàn bộ tính năng ở trên đang chạy trên bản demo công khai với dữ liệu đã ẩn danh.</p>
    <a class="btn btn-primary" style="background:var(--navy);color:#fff" href="https://audit-hq-demo.tinsu.ai" target="_blank" rel="noopener">🚀 Mở Audit-HQ demo</a>
  </div>
</section>

<footer><div class="wrap">
  <div>
    <h4>Audit-HQ</h4>
    <div>Hệ thống Quản lý Rủi ro BCQT cho Hải quan.</div>
    <div style="margin-top:8px"><a href="https://audit-hq-demo.tinsu.ai" target="_blank" rel="noopener">audit-hq-demo.tinsu.ai</a></div>
  </div>
  <div>
    <h4>Sản phẩm của</h4>
    <div>Tinsu AI × Trọng Tín</div>
    <div style="margin-top:8px;color:#8a9bb5">Bản dùng cho thí điểm</div>
  </div>
</div>
<div class="wrap"><div class="disclaimer">
  Chỉ số rủi ro trên hệ thống là chỉ số <b>rủi ro dữ liệu BCQT</b> (chênh lệch nội bộ giữa M15/M15a/M16
  và đối chiếu BCCT), <b>không phải</b> đánh giá tuân thủ pháp luật theo Thông tư 81/2019/TT-BTC.
  Phân loại tuân thủ chính thức thuộc thẩm quyền Tổng cục Hải quan. Mọi quyết định cuối cùng thuộc thẩm
  quyền cán bộ. Toàn bộ số liệu minh hoạ đã được ẩn danh, không phản ánh doanh nghiệp có thật.
</div></div>
</footer>

<div id="lb"><img alt=""></div>
<script>
(function(){
  var lb=document.getElementById('lb'),lbimg=lb.querySelector('img');
  document.querySelectorAll('.frame img').forEach(function(im){
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
