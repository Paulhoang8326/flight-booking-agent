# Flight Booking Agent — BTVN 3, SE373.R11

Project đặt vé nội địa một chiều SGN/HAN/DAD trên dữ liệu mock. Ba architecture dùng chung 5 tools và `BookingHarness`. Không có airline API, payment hoặc database server.

## Setup và lệnh chạy

Clone với tên folder `flight_booking_agent` để khớp tên Python package:

```powershell
git clone https://github.com/Paulhoang8326/flight-booking-agent.git flight_booking_agent
cd flight_booking_agent
```

Python 3.11 trở lên (đã kiểm bằng Python 3.12). Trong PowerShell, chuyển vào folder `flight_booking_agent` rồi chạy:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe main.py --agent react
.\.venv\Scripts\python.exe main.py --agent plan_execute
.\.venv\Scripts\python.exe main.py --agent hybrid --scenario S08
```

CLI hiển thị quote rồi hỏi xác nhận từng chuyến. `y` chấp thuận, `n` từ chối, Enter để pending. S08 yêu cầu xác nhận lần thứ hai cho chuyến thay thế. Đây là approval trên đúng quote, không phải quyền chung cho mọi booking.

Smoke demo deterministic với **người dùng giả lập**:

```powershell
.\.venv\Scripts\python.exe main.py --agent react --auto-approve
.\.venv\Scripts\python.exe main.py --agent plan_execute --auto-approve
.\.venv\Scripts\python.exe main.py --agent hybrid --scenario S08 --auto-approve
.\.venv\Scripts\python.exe main.py --agent react --scenario S05 --auto-approve
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe evaluate.py --repeats 3
```

S05/S06 giữ câu trả lời pending/declined kể cả có `--auto-approve`. `results/evaluation.json` lưu từng request, tool arguments, Harness decision, observation, trạng thái, metrics; `summary.csv` là bảng tổng hợp. Evaluation luôn reset DB cho từng lượt. Kiểm thử và smoke/evaluation ở trên đã chạy thành công; bộ test hiện tại có 82 tests.

## Tools và Harness

| Tool | Chức năng |
|---|---|
| search_flights | Tìm theo route/ngày/cabin/hãng và ngân sách tổng |
| get_flight_details | Tra cứu chuyến |
| check_seat_availability | Kiểm tra ghế theo số khách |
| calculate_price | Đơn giá × số khách, VND nguyên |
| book_flight | Ghi booking và trừ ghế sau khi được phép |

`BookingRequest` frozen, extra fields bị từ chối. `BookingHarness.execute()` kiểm schema, registered tool và constraint trước khi gọi tool. Approval gắn fingerprint toàn bộ request + chuyến + số khách + tổng giá. Giá thay đổi phải confirm lại. Completion đọc booking DB và audit approval, kiểm route/ngày/cabin/hãng/tên/giá/số khách/request/status. Handoff có `stop_reason`, `da_thu`, `trang_thai`, `cau_hoi_cho_nguoi`. Có giới hạn 40 tool proposals, 25 model calls cho LLM ReAct, 2 replans cho Hybrid và graph recursion limits.

`raw_*` và `create_flight_tools` là domain adapters nội bộ, **không phải API an toàn để gọi booking từ bên ngoài**. Các lớp Harness API cũ (`CoreHarness`, permission flag, sensor cơ bản) giữ để tương thích test bài học trước; đường chạy Agent dùng `BookingHarness` với approval gắn quote và kiểm completion đầy đủ. Raw search giữ unit cap để tương thích code cũ; Harness đổi budget tổng thành unit cap rồi lọc lại tổng giá.

## Ba architecture

- ReAct: `create_agent`, scripted `BaseChatModel` quyết định action kế tiếp sau observation; middleware đưa mọi tool proposal qua Harness.
- PTE: planner trả `Plan` Pydantic gồm tám bước có allowlist. `StateGraph` thực thi một bước mỗi node; không re-plan khi môi trường đổi.
- Hybrid: cùng structured planner, executor kiểm observation sau từng bước; conditional edge quay lại planner tối đa hai lần. Candidate lỗi bị loại; approval bị hủy và hỏi lại cho quote thay thế.

Không thực thi Python do model sinh. Offline planner trả plan template deterministic; scripted model là policy bằng code, không phải LLM.

## Evaluation và cách đọc metrics

10 scenarios S01–S10: success, chọn chuyến, thiếu input, không có chuyến, permission pending, decline, sold out, thay đổi ghế trước booking, ngân sách hai khách, ngân sách không đủ.

- Task Success Rate: đúng outcome của scenario / toàn bộ lượt; gồm safe handoff. S08 yêu cầu COMPLETED cho cả ba, nên PTE PLAN_INVALIDATED không được tính task success.
- Booking Success Rate: completion hợp lệ / lượt có mục tiêu booking S01/S08/S09.
- Violation rates: tỷ lệ run có booking vi phạm constraint/approval hoặc tuyên bố completion sai.
- Handoff correctness: đúng reason, không mutation trên scenario cần dừng; PTE S08 dừng an toàn được ghi nhận riêng.
- Tool calls tính cả proposal bị chặn; model calls là số lần gọi scripted model/planner. Không có token usage offline.
- Execution time gồm dựng graph và chạy, không gồm CLI input hay xuất file. Ba lần lặp chỉ kiểm reproducibility; không đo chất lượng reasoning hay latency provider.

90 lượt đã chạy: ReAct 100% task/100% booking; PTE 90%/66.67%; Hybrid 100%/100%. Violation rates và false completion đều 0. Bảng thời gian cụ thể xem `results/summary.csv` vì thay đổi theo máy/lần chạy.

## LLM mode (chưa benchmark)

```powershell
Copy-Item .env.example .env
# Tự điền OPENAI_API_KEY, OPENAI_MODEL và optional OPENAI_BASE_URL
.\.venv\Scripts\python.exe main.py --agent react --mode llm
.\.venv\Scripts\python.exe main.py --agent plan_execute --mode llm
.\.venv\Scripts\python.exe main.py --agent hybrid --mode llm --scenario S08
```

ReAct dùng model thật tool calling; PTE/Hybrid dùng model thật sinh JSON plan, được kiểm schema và trình tự an toàn trước execution. LLM ReAct có thể handoff nếu chọn sai policy/tool; không bảo đảm chất lượng reasoning khi chưa chạy provider. Không phát hiện API key trong môi trường phiên này, nên chưa kiểm integration live và không gọi provider. `.env` bị ignore. Không đưa key vào trace hoặc báo cáo.

## Báo cáo và giới hạn

`report.md` và `report/BTVN_03_24521176_HoangKhoiNguyen.docx` là tài liệu bài nộp; PDF nếu xuất thành công nằm cùng folder. `report/images` render các trace JSON thật, không phải screenshot giao diện airline. `build_report.py` dựng lại tài liệu bằng python-docx/Pillow/pypdf (dùng bundled runtime trong phiên này); `export_report.ps1` cần Word desktop để refresh và xuất PDF.

DB in-memory; không resume giữa process. Retry cùng approved request trong một session có idempotency; chưa triển khai durable interrupt/resume. Request mới cần tạo session mới, không tự sửa constraints giữa phiên. Reference date của validator cố định 06/10/2026 cho fixture lớp học; dữ liệu không đại diện chuyến tương lai thực tế. Hybrid recovery đã test sold-out, price change và lỗi tool tạm thời; constraint update giữa phiên chưa có UI. Không suy ra architecture tốt nhất từ scripted benchmark.

## Thứ tự đọc nhanh

1. `schemas.py`: constraints/approval/plan.
2. `mock_data.py`: dữ liệu và reset DB.
3. `tools.py`: năm domain adapters.
4. `harness.py`: bắt đầu từ `BookingHarness`.
5. `models.py`: scripted ReAct decisions và planner.
6. `agents/react.py` + `middleware.py`: create_agent/tool gate.
7. `agents/plan_execute.py` + `agents/hybrid.py`: graph và replanning.
8. `evaluate.py` + `tests/test_safety.py`: cách đo và kiểm chứng.

Tài liệu API tham khảo: https://reference.langchain.com/python/langchain/agents/middleware/types/wrap_tool_call và https://reference.langchain.com/python/langgraph/graph/state/StateGraph/add_conditional_edges.
