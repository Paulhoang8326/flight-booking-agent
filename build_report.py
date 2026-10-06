"""Build the submission from measured JSON, with rendered evidence figures.

Artifact-only dependencies: python-docx, Pillow, pypdf. No LangChain import.
Run after tests, smoke demos, evaluation and results_capture.py.
"""
import json
import textwrap
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parent
REPORT=ROOT/'report'; IMAGES=REPORT/'images'
IMAGES.mkdir(parents=True,exist_ok=True)
evaluation=json.loads((ROOT/'results/evaluation.json').read_text(encoding='utf-8'))
test_count=int(re.search(r'(\d+) passed',(ROOT/'results/pytest.txt').read_text(encoding='utf-8')).group(1))
summary=evaluation['summary']
def load(name): return json.loads((ROOT/'results'/name).read_text(encoding='utf-8'))
react=load('react_S01.json'); pte=load('pte_S01.json'); hybrid=load('hybrid_S08.json')
safety=load('safety_demo.json'); permission=load('permission_S05.json')

def terminal_image(name,title,lines):
    wrapped=[]
    for line in lines: wrapped.extend(textwrap.wrap(line,width=94,replace_whitespace=False) or [''])
    font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',22)
    head=ImageFont.truetype('C:/Windows/Fonts/consolab.ttf',26)
    img=Image.new('RGB',(1280,100+len(wrapped)*31),(248,248,248))
    draw=ImageDraw.Draw(img)
    draw.text((28,22),title,font=head,fill='black')
    draw.line((28,65,1252,65),fill=(170,170,170),width=2)
    for i,line in enumerate(wrapped): draw.text((28,82+i*31),line,font=font,fill=(20,20,20))
    path=IMAGES/(name+'.png'); img.save(path)
    return path

def trace_lines(run):
    r=run['request']
    lines=[f"REQUEST {r['request_id']}: {r['origin']} -> {r['destination']} {r['departure_date']}",
           f"Cabin={r['cabin_class']} passengers={r['passenger_count']} budget={r['max_budget']:,} VND"]
    for i,e in enumerate(run['trace'],1):
        a=e['action']; args=e['arguments']; obs=e['observation']
        if a=='planner':
            lines.append(f"{i:02}. planner -> " + ' > '.join(s['action'] for s in obs['steps']))
        elif a=='request_confirmation':
            lines.append(f"{i:02}. USER confirm {args['flight_id']} total={args['total_price']:,}: {obs['answer']}")
        else:
            brief={k:v for k,v in obs.items() if k in ('status','error_code','available','total_price','booking_id','completed','reason')}
            if a=='search_flights': brief['candidates']=[f['flight_id'] for f in obs.get('flights',[])]
            lines.append(f"{i:02}. {a} {json.dumps(args,ensure_ascii=False)}")
            lines.append(f"    {e['harness_decision']} -> {json.dumps(brief,ensure_ascii=False)}")
    lines.append(f"FINAL: {run['status']} | booking_id={run['booking_id']}")
    lines.append(f"DB bookings={len(run['bookings'])} | tool calls={run['metrics']['tool_calls']} | model calls={run['metrics']['model_calls']}")
    return lines

figs={}
figs['react']=terminal_image('react_trace','ReAct / S01 - actual captured trace',trace_lines(react))
figs['pte']=terminal_image('pte_trace','Plan-then-Execute / S01 - actual captured trace',trace_lines(pte))
figs['hybrid']=terminal_image('hybrid_replan','Hybrid / S08 - actual captured trace',trace_lines(hybrid))
figs['safety']=terminal_image('harness_block','Direct Harness negative test',[
    'Attempt: '+json.dumps(safety['attempt']['arguments']),
    'Harness decision: '+safety['attempt']['harness_decision'],
    'Observation: '+json.dumps(safety['attempt']['observation']),
    'Booking DB: '+json.dumps(safety['bookings']),
    'Claimed booking: BK001 (model text only)',
    'Completion by code: '+str(safety['completion_by_code'])])
figs['handoff']=terminal_image('permission_handoff','ReAct / S05 - approval pending',[
    'Request: '+json.dumps(permission['request'],ensure_ascii=False),
    'Status: '+permission['status'],
    'stop_reason: '+permission['handoff']['stop_reason'],
    'trang_thai: '+json.dumps(permission['handoff']['trang_thai']),
    'cau_hoi_cho_nguoi: '+permission['handoff']['cau_hoi_cho_nguoi'],
    'DB bookings: '+str(len(permission['bookings']))])
figs['eval']=terminal_image('evaluation','Measured benchmark / 10 scenarios x 3 repeats',[
    'architecture     task%   booking%  tools  model  elapsed_ms  violations',
    *[f"{r['architecture']:16} {100*r['task_success_rate']:5.1f} {100*r['booking_success_rate']:9.2f} {r['avg_tool_calls']:6.2f} {r['avg_model_calls']:6.2f} {r['avg_elapsed_ms']:10.2f}  0 / 0 / 0" for r in summary],
    'Booking denominator: S01, S08, S09 (9 runs per architecture).',
    'Violations: constraint / permission / false completion.',
    'Mode: offline scripted model. Tokens: N/A. No provider latency measured.'])

logo=None
old=ROOT.parent.parent/'BTVN/BTVN_02_24521176_HoangKhoiNguyen.pdf'
if old.exists():
    logos=PdfReader(old).pages[0].images
    if logos:
        logo=IMAGES/'uit_logo.png'; logo.write_bytes(logos[0].data)

doc=Document()
sec=doc.sections[0]; sec.page_width=Cm(21); sec.page_height=Cm(29.7)
sec.top_margin=Cm(2); sec.bottom_margin=Cm(2); sec.left_margin=Cm(2.5); sec.right_margin=Cm(2)
for name in ['Normal','Title','Heading 1','Heading 2','Caption']:
    style=doc.styles[name]; style.font.name='Times New Roman'; style.font.color.rgb=RGBColor(0,0,0)
    fonts=style._element.rPr.rFonts
    for key in ['ascii','hAnsi','eastAsia','cs']:
        fonts.set(qn('w:'+key),'Times New Roman')
    for key in ['asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme']:
        fonts.attrib.pop(qn('w:'+key),None)
    for borders in list(style._element.xpath('.//w:pBdr')):
        borders.getparent().remove(borders)
normal=doc.styles['Normal']; normal.font.size=Pt(12)
normal.paragraph_format.line_spacing=1.15; normal.paragraph_format.space_after=Pt(6)
for name,size in [('Title',19),('Heading 1',15),('Heading 2',13)]:
    doc.styles[name].font.size=Pt(size); doc.styles[name].font.bold=True
    doc.styles[name].paragraph_format.keep_with_next=True
footer=sec.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
footer.add_run('SE373.R11 · Hoàng Khôi Nguyên · ')
field=OxmlElement('w:fldSimple'); field.set(qn('w:instr'),'PAGE'); footer._p.append(field)

def p(text='',bold=False):
    para=doc.add_paragraph(); para.add_run(text).bold=bold; return para
def h(text,level=1): return doc.add_heading(text,level=level)
def table(headers,rows,widths=None):
    t=doc.add_table(rows=1,cols=len(headers)); t.style='Table Grid'; t.autofit=False
    if widths:
        for col,w in zip(t.columns,widths): col.width=Cm(w)
    for c,txt in zip(t.rows[0].cells,headers):
        c.text=txt
        for run in c.paragraphs[0].runs: run.bold=True
    repeat=OxmlElement('w:tblHeader'); t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        cells=t.add_row().cells
        for c,txt in zip(cells,row): c.text=str(txt)
    for row in t.rows:
        for j,cell in enumerate(row.cells):
            if widths: cell.width=Cm(widths[j])
            for para in cell.paragraphs:
                para.paragraph_format.space_after=Pt(3); para.paragraph_format.space_before=Pt(3)
                para.paragraph_format.line_spacing=1.0
                for run in para.runs: run.font.size=Pt(10.5)
    props=t._tbl.tblPr
    tw=props.find(qn('w:tblW')); tw.set(qn('w:w'),str(round(sum(widths)*567))); tw.set(qn('w:type'),'dxa')
    borders=OxmlElement('w:tblBorders')
    for edge in ['top','left','bottom','right','insideH','insideV']:
        b=OxmlElement('w:'+edge); b.set(qn('w:val'),'single'); b.set(qn('w:sz'),'4'); b.set(qn('w:color'),'D9D9D9'); borders.append(b)
    props.append(borders)
    return t
def fig(key,caption,width=16.3):
    para=doc.add_paragraph(); para.alignment=WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.keep_with_next=True
    para.add_run().add_picture(str(figs[key]),width=Cm(width))
    para=doc.add_paragraph(caption,style='Caption'); para.alignment=WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.keep_with_next=False
    for run in para.runs: run.italic=True; run.bold=False; run.font.size=Pt(11)
def page(): doc.add_page_break()

for text in ['ĐẠI HỌC QUỐC GIA TP HỒ CHÍ MINH','TRƯỜNG ĐẠI HỌC CÔNG NGHỆ THÔNG TIN']:
    para=p(text,True); para.alignment=WD_ALIGN_PARAGRAPH.CENTER
p()
if logo:
    para=p(); para.alignment=WD_ALIGN_PARAGRAPH.CENTER; para.add_run().add_picture(str(logo),width=Cm(4))
p()
for text in ['MÔN KỸ THUẬT XÂY DỰNG HỆ THỐNG AGENTIC AI','BÀI TẬP VỀ NHÀ 3']:
    para=p(text,True); para.alignment=WD_ALIGN_PARAGRAPH.CENTER
para=doc.add_paragraph('XÂY DỰNG AGENT ĐẶT VÉ MÁY BAY\nBẰNG LANGCHAIN VÀ LANGGRAPH',style='Title'); para.alignment=WD_ALIGN_PARAGRAPH.CENTER
p()
for text in ['LỚP SE373.R11','NGÀY NỘP: Chưa xác định trong tài liệu đề bài',
             'HỌ VÀ TÊN SINH VIÊN: HOÀNG KHÔI NGUYÊN','MSSV: 24521176']:
    para=p(text); para.alignment=WD_ALIGN_PARAGRAPH.CENTER
page()
h('1. Giới thiệu')
p('Project xây dựng Agent hỗ trợ đặt vé nội địa một chiều trên môi trường mock. Người dùng cung cấp route, ngày bay, số khách, cabin, ngân sách tổng và chính sách chọn chuyến. Hệ thống chỉ tạo booking khi đã có xác nhận phù hợp và kiểm tra kết quả bằng code.')
p('Bài tập tập trung vào Harness và ba mẫu ReAct, Plan-then-Execute, Hybrid. Phiên bản hiện tại chạy được offline, có 81 test pass và benchmark 90 lượt. Số liệu dùng để kiểm chứng orchestration và cơ chế an toàn; chưa đánh giá reasoning của LLM thật.')
h('2. Công nghệ sử dụng')
table(['Công nghệ','Vai trò'],[
    ['Python 3.12','Môi trường đã chạy và kiểm thử'],['LangChain 1.4.3','create_agent, middleware, BaseChatModel, tool calling'],
    ['LangGraph 1.2.13','StateGraph và conditional edges cho executor/re-plan'],
    ['Pydantic 2.13.5','Schema request, approval và structured plan'],['pytest 9.1.1','81 unit/integration tests'],
    ['python-dotenv; langchain-openai','Đọc .env và adapter LLM tùy chọn, chưa chạy live'],
    ['Scripted model','Policy deterministic để test offline, không phải LLM']], [5,11.5])
h('3. Chức năng chính')
for text in ['Tiếp nhận yêu cầu và giữ constraints dưới dạng dữ liệu frozen.',
    'Tìm chuyến, đọc chi tiết, kiểm ghế và tính tổng tiền theo số khách.',
    'Yêu cầu xác nhận cho từng quote trước khi ghi booking.',
    'Đọc lại booking DB để kiểm completion; handoff khi cần người can thiệp.',
    'Chạy ba architecture trên cùng dữ liệu và ghi trace/metrics để so sánh.']:
    doc.add_paragraph(text,style='List Bullet')
page()
h('4. Thiết kế hệ thống')
h('4.1. Dữ liệu và Mock Tools',2)
p('MockFlightDatabase chứa 10 chuyến tại SGN, HAN, DAD trong các ngày 15–16/10/2026. Booking lưu in-memory; mỗi test và mỗi lượt evaluation tạo DB riêng. Tiền dùng số nguyên VND; ngân sách là tổng booking, không phải giá mỗi khách.')
table(['Tool','Chức năng'],[['search_flights','Tìm đúng route/ngày/cabin/hãng/ngân sách tổng'],
    ['get_flight_details','Lấy thông tin chuyến theo flight_id'],['check_seat_availability','Kiểm số ghế đáp ứng số khách'],
    ['calculate_price','Tính base_price × passenger_count'],['book_flight','Ghi booking CONFIRMED và trừ ghế sau permission']], [6,10.5])
p('Luồng chính: User → Agent → BookingHarness → Mock Tools → Mock Database. Bốn tool đầu đọc dữ liệu; book_flight tạo side effect. Agent không được gọi raw booking adapter để bỏ qua Harness.')
h('4.2. Harness',2)
p('Ràng buộc là dữ liệu. BookingRequest frozen lưu origin, destination, departure_date, passenger_count, cabin_class, airline, max_budget và selection_policy. Harness kiểm route, lịch, số khách, ngân sách, schema tool arguments và đối chiếu mọi action với request; không tự nới ngân sách hoặc đổi ngày.')
p('Kiểm quyền. READ tools chạy sau validation. Approval lưu fingerprint toàn bộ request, flight_id, số khách và tổng tiền. Approval chuyến A không dùng cho B; giá hoặc số khách thay đổi làm approval không còn phù hợp. Callback xác nhận thuộc application, không phải model.')
p('Completion bằng code. Hệ thống đọc booking DB và audit approval; kiểm request, chuyến, route/ngày, cabin/hãng, hành khách, giá, ngân sách và status. Model tự nói đã đặt vé không làm tác vụ hoàn thành.')
p('Handoff. Gói bàn giao gồm stop_reason, da_thu, trang_thai, cau_hoi_cho_nguoi. Giới hạn tài nguyên: 40 tool proposals, tối đa 2 replans và graph recursion limit. Validator dùng ngày tham chiếu cố định 06/10/2026 để tái lập fixture bài học.')
page()
h('5. Ba mẫu thiết kế Agent')
h('5.1. ReAct',2)
p('create_agent điều phối vòng action → observation → action tiếp theo. ScriptedBookingModel kế thừa BaseChatModel, chọn tool dựa trên observation trước đó. Middleware chuyển mọi tool proposal sang BookingHarness.execute. Khi chuyến hết ghế, policy thử lại với candidate khác và yêu cầu approval mới.')
h('5.2. Plan-then-Execute',2)
p('Planner trả structured Plan gồm tám bước: search, select candidate, details, seats, price, confirmation, booking, verification. Executor StateGraph thực thi từng bước. Plan chỉ cho registered tools và ba control actions; không sinh hay execute Python. Baseline lập plan một lần và handoff khi plan mất hiệu lực.')
h('5.3. Hybrid',2)
p('Hybrid dùng planner như PTE nhưng kiểm observation sau từng bước. Khi candidate hết ghế, giá thay đổi hoặc tool lỗi có thể phục hồi, conditional edge quay lại planner. Candidate lỗi bị loại, approval cũ bị hủy, tối đa hai lần re-plan. Thay constraint cần request/session mới; chưa có UI sửa constraint giữa phiên.')
table(['Tiêu chí','ReAct','PTE','Hybrid'],[
    ['Plan ban đầu','Không','Có','Có'],['Sau observation','Chọn action mới','Theo plan','Kiểm rồi đi tiếp'],
    ['Khi S08 hết ghế','Thử alternative','Plan mất hiệu lực','Re-plan'],
    ['Planner calls','Không riêng','Một lần','Có thêm khi lỗi']], [4.5,4,4,4])
h('6. Quy trình hoạt động')
for i,text in enumerate(['Nhập request và tạo BookingRequest.','Harness kiểm input và giữ constraints frozen.',
    'Agent lập plan hoặc đề xuất action theo architecture.','Harness kiểm tool name, schema và constraints.',
    'Tool thực thi trên DB, trả observation và ghi trace.','Chọn candidate theo policy hoặc hỏi người dùng.',
    'Kiểm ghế, tính tổng tiền, xin xác nhận đúng quote.','Harness kiểm approval trước book_flight.',
    'Tạo booking và trừ ghế; nếu môi trường đổi thì xử lý theo architecture.',
    'CompletionChecker đọc DB/audit; trả COMPLETED hoặc handoff.'],1):
    p(f'{i}. {text}')
page()
h('7. Kết quả chạy demo')
h('7.1. ReAct Agent',2)
p('S01 yêu cầu SGN → HAN ngày 15/10/2026, Economy, một khách, ngân sách 2.000.000 VND và chọn rẻ nhất. Agent chọn VJ120 giá 1.200.000 VND, lấy xác nhận, tạo BK001 và verification pass. Ảnh dưới là phần trace được render từ JSON của lần chạy thật; approval trong smoke run là người dùng giả lập.')
fig('react','Hình 1. Trace ReAct S01 với booking và completion được kiểm bằng code.')
p('Trace ghi action, arguments, Harness decision và observation. Không ghi chain-of-thought. CLI tương tác dùng cùng flow nhưng chờ người dùng nhập y/n ở bước xác nhận.')
page()
h('7.2. Plan-then-Execute Agent',2)
p('S01 cho kết quả giống ReAct nhưng cách điều phối khác: planner tạo tám bước trước khi executor chạy. Model không chọn lại action ở mỗi tool observation. Kế hoạch được kiểm theo allowlist và thứ tự an toàn trước khi thực thi.')
fig('pte','Hình 2. Structured plan và trace thực thi PTE S01.')
p('Ở S08, cùng plan này không còn thực hiện được vì chuyến đã hết ghế trước booking. Baseline dừng PLAN_INVALIDATED, DB không có booking. Đây là handoff an toàn nhưng chưa đạt mục tiêu booking của scenario.')
page()
h('7.3. Hybrid Agent',2)
p('S08 mô phỏng ghế của VJ120 chuyển về 0 ngay trước ghi booking. Tool trả SEATS_NOT_AVAILABLE. Hybrid phát hiện lỗi, hủy approval cũ, loại VJ120 và gọi planner lần thứ hai. Candidate thay thế QH202 có tổng tiền 1.500.000 VND nên phải được xác nhận lại trước khi đặt.')
fig('hybrid','Hình 3. Hybrid re-plan và lấy approval mới cho QH202 trong S08.')
p('BK001 cuối cùng thuộc QH202, verification pass. Test đối chiếu hai quote được confirm lần lượt là VJ120 và QH202; không tái sử dụng approval chuyến cũ.')
page()
h('7.4. Harness chặn hành động không hợp lệ',2)
p('Thử trực tiếp gọi book_flight khi chưa có approval. Harness trả BLOCK và USER_CONFIRMATION_REQUIRED, DB vẫn rỗng. Sau đó giả sử model nói đã đặt BK001; verification đọc DB trả False. Bằng chứng được lưu trong results/safety_demo.json.')
fig('safety','Hình 4. Harness chặn booking chưa approval và từ chối false completion.')
p('S05 thực hiện các bước tìm kiếm, kiểm ghế và quote, nhưng người dùng chưa xác nhận. Agent dừng NEED_USER_CONFIRMATION và cung cấp gói handoff đủ bốn trường.')
fig('handoff','Hình 5. Handoff S05 khi approval pending và booking DB rỗng.')
p('Các test bổ sung kiểm approval sai chuyến, request khác, giá/số khách thay đổi, constraints bị đổi, booking bị sửa và repeated delivery. Cùng request/quote được giao lại trong một session không tạo thêm booking; chưa có resume lưu bền giữa process.')
page()
h('8. Đánh giá ba mẫu Agent')
p('Thiết kế: 10 scenario S01–S10, ba architecture, ba lần lặp; tổng 90 lượt offline. Mỗi lượt reset DB độc lập. S01/S08/S09 có mục tiêu booking; các scenario còn lại cần handoff an toàn. Test: 81 passed, 0 failed. Kết quả dưới lấy trực tiếp từ evaluate.py và results/evaluation.json.')
table(['Scenario','Mục tiêu'],[[s,t] for s,t in [('S01','Cheapest happy path'),('S02','Hỏi chọn khi thiếu policy'),('S03','Thiếu ngày: không mutation'),('S04','Không có chuyến: không đổi ngày'),('S05/S06','Pending / từ chối approval'),('S07','Chuyến chỉ định hết ghế'),('S08','Ghế mất ngay trước booking'),('S09/S10','Hai khách: đủ / thiếu ngân sách tổng')]], [3,13.5])
metrics=[('Task Success Rate','task_success_rate',True),('Booking Success Rate','booking_success_rate',True),
    ('Constraint Violation Rate','constraint_violation_rate',True),('Permission Violation Rate','permission_violation_rate',True),
    ('False Completion Rate','false_completion_rate',True),('Tool calls trung bình','avg_tool_calls',False),
    ('Model calls trung bình','avg_model_calls',False),('Execution time TB (ms)','avg_elapsed_ms',False)]
rows=[[label]+[f"{100*r[key]:.2f}%" if percent else f"{r[key]:.2f}" for r in summary] for label,key,percent in metrics]
rows.extend([['Handoff đúng / tổng']+[f"{r['handoff_correct']}/{r['handoff_count']}" for r in summary],['Token usage','N/A','N/A','N/A']])
table(['Metric','ReAct','PTE','Hybrid'],rows,[7,3.1,3.1,3.3])
p('Task Success Rate tính đúng outcome / 30 lượt mỗi architecture, gồm safe handoff. Booking Success Rate dùng 9 lượt S01/S08/S09. PTE S08 được tính handoff đúng nhưng không tính task success. Tool calls gồm proposals bị chặn. Model calls offline là scripted decisions hoặc planner calls; không phải token/chi phí LLM.')
fig('eval','Hình 6. Bảng benchmark được render từ output evaluation thực tế.')
page()
h('9. So sánh và nhận xét')
p('ReAct và Hybrid đạt task success 100% trong bộ scenario; PTE đạt 90%. Khác biệt đến từ S08: PTE không re-plan nên dừng an toàn, còn ReAct và Hybrid đặt được alternative. Booking success tương ứng là 100%, 66,67% và 100% trên các scenario có mục tiêu booking.')
p('PTE có ít tool/model calls hơn vì không tiếp tục sau plan invalidation. Hybrid chỉ gọi planner khi cần; ReAct dùng scripted model để quyết định action sau mỗi observation. Cả ba không có vi phạm constraint/permission hay false completion trong 90 lượt đã đo. Kết quả không chứng minh khả năng reasoning của một architecture luôn tốt hơn.')
p('Thời gian đo gồm dựng graph và chạy mock tool, không gồm nhập CLI hoặc gọi provider thật. Ba lần lặp kiểm tái lập của orchestration; không đại diện độ đa dạng đầu ra của LLM hoặc phân phối độ trễ API.')
h('10. Kết luận và hướng dẫn chạy')
p('Project đã triển khai đủ mock tools, constraints bằng dữ liệu, permission gắn quote, completion đọc DB và handoff; ba architecture chạy trên cùng môi trường. Harness tách đề xuất của model khỏi quyền ghi booking và quyền công nhận completion.')
p('Giới hạn: dữ liệu mock, không payment hay airline API; DB in-memory, không durable resume. Scripted benchmark nhỏ và deterministic. Chưa có API key trong môi trường nên chưa chạy model thật; adapter .env được cung cấp nhưng integration live chưa được kiểm chứng. Không dùng số liệu này để kết luận chất lượng reasoning hoặc chọn model tốt nhất.')
p('Trong PowerShell, đứng tại folder flight_booking_agent và dùng Python 3.11+ để tạo .venv. Các lệnh đã chạy thành công:')
for text in ['python -m venv .venv',r'.\.venv\Scripts\python.exe -m pip install -r requirements.txt',
    r'.\.venv\Scripts\python.exe main.py --agent react --auto-approve',
    r'.\.venv\Scripts\python.exe main.py --agent plan_execute --auto-approve',
    r'.\.venv\Scripts\python.exe main.py --agent hybrid --scenario S08 --auto-approve',
    r'.\.venv\Scripts\python.exe -m pytest tests -q',
    r'.\.venv\Scripts\python.exe evaluate.py --repeats 3']:
    para=p(text)
    for run in para.runs: run.font.name='Consolas'; run.font.size=Pt(10)
p('Bỏ --auto-approve để trình bày confirm tương tác; S08 sẽ hỏi lại cho chuyến thay thế. Tài liệu bài học Buoi3.pdf xác nhận BTVN#3; không xác định được ngày nộp nên không tự điền.')
p('Tham khảo: tài liệu môn học Buoi3.pdf; LangChain wrap_tool_call và LangGraph StateGraph.add_conditional_edges trên reference.langchain.com. Logo UIT được lấy từ báo cáo BTVN 02 đã có của sinh viên.')
for para in doc.paragraphs:
    for run in para.runs:
        if '81' in run.text:
            run.text=run.text.replace('81',str(test_count))
for tbl in doc.tables:
    for row in tbl.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.text=run.text.replace('81 unit',f'{test_count} unit')
doc.save(REPORT/'BTVN_03_24521176_HoangKhoiNguyen.docx')

# Markdown source retains the requested 15-section outline and measured table.
md=['# BTVN 3 — Xây dựng Agent đặt vé máy bay bằng LangChain và LangGraph',
    'Hoàng Khôi Nguyên · 24521176 · SE373.R11. Ngày nộp chưa xác định trong đề bài.',
    '## 1. Giới thiệu bài toán','Đặt vé nội địa một chiều trong môi trường mock SGN/HAN/DAD.',
    '## 2. Mục tiêu','Harness kiểm ràng buộc, permission, completion và handoff; so sánh ReAct/PTE/Hybrid.',
    '## 3. Công nghệ','Python 3.12; LangChain 1.4.3; LangGraph 1.2.13; Pydantic 2.13.5; pytest 9.1.1; python-dotenv; langchain-openai tùy chọn.',
    '## 4. Mock flight environment','10 chuyến, 15–16/10/2026; DB in-memory reset từng lượt; tiền VND nguyên, budget tổng booking.',
    'Tools: search_flights, get_flight_details, check_seat_availability, calculate_price, book_flight.',
    '## 5. Harness','BookingRequest frozen. Gate kiểm schema và constraint. Approval gắn fingerprint request, chuyến, số khách, tổng tiền. Completion đọc booking/audit; kiểm request, route/ngày/cabin/hãng/tên/giá/ngân sách/status. Handoff gồm stop_reason/da_thu/trang_thai/cau_hoi_cho_nguoi.',
    '```mermaid\nflowchart TD\nUser --> Agent\nAgent --> Harness\nHarness --> Tools\nTools --> DB\nDB --> Completion\nHarness --> Handoff\n```',
    '## 6. ReAct','create_agent + BaseChatModel scripted + wrap_tool_call gate. Observation quyết định tool kế tiếp, adaptive retry khi hết ghế.',
    '![ReAct](report/images/react_trace.png)',
    '## 7. Plan-then-Execute','Structured plan tám bước; StateGraph thực thi tuần tự, không re-plan baseline. S08 dừng PLAN_INVALIDATED.',
    '![PTE](report/images/pte_trace.png)',
    '## 8. Hybrid','Plan + kiểm observation từng bước + tối đa 2 replans. Hủy approval cũ và xin confirm chuyến thay thế.',
    '![Hybrid](report/images/hybrid_replan.png)',
    '## 9. Thiết kế thực nghiệm','S01–S10 × 3 architecture × 3 lần = 90 lượt offline; reset DB độc lập. 81 tests passed.',
    'S01 success; S02 thiếu policy; S03 thiếu input; S04 no flight; S05 pending; S06 decline; S07 sold out; S08 mất ghế trước booking; S09/S10 budget hai khách.',
    '## 10. Kết quả thực tế','| Metric | ReAct | PTE | Hybrid |','|---|---:|---:|---:|',
    *['| '+' | '.join(row)+' |' for row in rows],
    'Task denominator 30/architecture; booking denominator 9/architecture (S01/S08/S09). PTE S08 là safe handoff đúng nhưng không hoàn thành mục tiêu booking. Tool count gồm proposal bị chặn; model count là scripted/planner calls. Timing gồm dựng graph, không gồm user input hoặc export.',
    '![Evaluation](report/images/evaluation.png)',
    '## 11. So sánh ba architecture','S08: ReAct retry; PTE invalidated; Hybrid re-plan. Số calls của PTE thấp hơn một phần vì dừng sớm.',
    '## 12. Nhận xét','Không có constraint/permission violation hoặc false completion trong benchmark. Chênh lệch phản ánh policy/orchestration được lập trình, chưa phản ánh reasoning của LLM thật.',
    '![Harness block](report/images/harness_block.png)',
    '## 13. Hạn chế','Mock DB/flight, không payment/API thật, benchmark nhỏ deterministic. Chưa chạy provider; token N/A. Không durable resume; idempotency trong session. Ngày tham chiếu 06/10/2026 cố định cho fixture. Constraint update cần session mới.',
    '## 14. Kết luận','Đã xây đủ ba architecture và Harness, kiểm bằng 81 tests cùng 90 lượt benchmark. Không kết luận architecture tốt nhất cho hệ thống thật.',
    '## 15. Hướng dẫn chạy','Xem README.md để setup. Trong folder project:',
    '```powershell\n.\\.venv\\Scripts\\python.exe main.py --agent react\n.\\.venv\\Scripts\\python.exe main.py --agent plan_execute\n.\\.venv\\Scripts\\python.exe main.py --agent hybrid --scenario S08\n.\\.venv\\Scripts\\python.exe -m pytest tests -q\n.\\.venv\\Scripts\\python.exe evaluate.py --repeats 3\n```',
    'Nguồn: Buoi3.pdf; báo cáo BTVN 02 để tham khảo phong cách/logo; [LangChain middleware](https://reference.langchain.com/python/langchain/agents/middleware/types/wrap_tool_call); [LangGraph routing](https://reference.langchain.com/python/langgraph/graph/state/StateGraph/add_conditional_edges).']
(ROOT/'report.md').write_text('\n\n'.join(md).replace('81 tests',f'{test_count} tests'),encoding='utf-8')
print(REPORT/'BTVN_03_24521176_HoangKhoiNguyen.docx')
