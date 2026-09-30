# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Văn Giáp
- **MSSV:** 2A202602903
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/Giappp/K4-L3-DAY13-NguyenVanGiap-2A202602903-Monitoring-LLMOps.git
- **Commit SHA cuối:** 61a34f827748393ced851ea7c9b412dd53dced23
- **Challenge ID:** day13-k4-l3b-monitoring-llmops-v1
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-2A202602903`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.txt` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png`, `evidence/8a.png`, `evidence/8b.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10a.png`, `evidence/10b.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | Đạt điểm tuyệt đối, 0 missing schema, 0 missing context enrichment, 0 PII leak |
| `validate_dashboard.py` | 6/6 panel | 6/6 panel | Đạt chuẩn 100% hợp lệ hợp đồng cho cả 6 panels |
| `pytest` | 22 passed | 26 passed | Bổ sung đầy đủ unit tests cho CCCD, Credit card, Context enrichment và Child observations |
| Số traces hợp lệ | 0 | > 30 | Đầy đủ root, retrieval và generation observations trên Langfuse project cá nhân |
| Số PII leak | 0 | 0 | Tất cả email, SĐT VN, CCCD, thẻ tín dụng đều được scrub thành công |
| Latency P95 / TTFT P95 | ~1500ms / 50ms | ~160ms / 50ms | Độ trễ bình thường rất nhanh, TTFT 50ms đáp ứng tốt tương tác thời gian thực |
| Retrieval success rate | 100% | 100% | Hoạt động ổn định, ghi nhận chính xác trạng thái tool_success trong structured logs |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:**
  - Trong `app/middleware.py`, middleware `CorrelationIdMiddleware` trước tiên xóa ngữ cảnh cũ bằng `clear_contextvars()` để chống rò rỉ giữa các request.
  - Sau đó kiểm tra header `x-request-id` từ request gửi lên; nếu không có hoặc chuỗi rỗng sẽ sinh mới theo định dạng `req-<8-hex>` (`f"req-{uuid.uuid4().hex[:8]}"`).
  - Gắn correlation ID vào structlog contextvars qua `bind_contextvars(correlation_id=correlation_id)` và lưu vào `request.state.correlation_id`.
  - Trả correlation ID và thời gian xử lý qua response headers: `x-request-id` và `x-response-time-ms`. Đồng thời truyền ID vào `LabAgent.run` và đính kèm vào metadata của Langfuse trace.
- **Các metadata được ghi vào structured log:**
  - Nhóm hệ thống: `ts` (ISO 8601 UTC), `level`, `service="api"`, `event` (`request_received`, `response_sent`, `request_failed`).
  - Nhóm ngữ cảnh request: `correlation_id`, `user_id_hash` (băm sha256 12 ký tự), `session_id`, `feature`, `model`, `env`.
  - Nhóm chỉ số vận hành (trong `response_sent`): `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`.
  - Payload an toàn: `message_preview`, `answer_preview` (hoặc `detail` khi có lỗi) đã được scrub sạch PII.
- **Cách bảo đảm PII được scrub trước khi ghi:**
  - Định nghĩa regex trong `app/pii.py` cho `email`, `phone_vn`, `cccd`, `credit_card`.
  - Đăng ký processor `scrub_event` trong `app/logging_config.py` chạy trước `JsonlFileProcessor` và `JSONRenderer`. Processor này quét đệ quy mọi giá trị chuỗi trong `event_dict` (ngoại trừ các trường hệ thống không chứa PII như `ts`, `level`, `correlation_id`, `user_id_hash`) để thay thế bằng `[REDACTED_<TYPE>]` trước khi ghi file `data/logs.jsonl` hoặc hiển thị ra màn hình.
- **Cách kiểm chứng kết quả:**
  - Chạy `python scripts/validate_logs.py` đạt 100/100, xác nhận 0 bản ghi vi phạm schema và 0 PII leak.
  - Bộ kiểm thử tự động `tests/test_pii.py`, `tests/test_chat_observability.py`, `tests/test_validate_logs.py` đều pass 100%.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:**
  - Cấu hình biến môi trường `LANGFUSE_PUBLIC_KEY` và `LANGFUSE_SECRET_KEY` từ chính project cá nhân `day13-k4-l3b-2A202602903` trên Langfuse Cloud. URL truy cập trace trực tiếp mang project ID `cmuni951r0hkvad0ci2s8sjq1`.
- **Cấu trúc root/retrieval/generation observations:**
  - Cấu trúc cây trace hình thành theo đúng quan hệ cha - con:
    ```text
    day13-agent-request (Root trace)
    └── lab-agent-run (Observation loại Agent)
        ├── retrieval (Child observation loại Retriever, ghi nhận input preview và doc_count)
        └── generation (Child observation loại Generation, ghi nhận model claude-sonnet-4-5, prompt template, token usage và cost)
    ```
- **Cách nối trace với log:**
  - Trace metadata chứa trường `correlation_id` có giá trị trùng khớp hoàn toàn với `correlation_id` trong structured log `data/logs.jsonl`.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** Version 1, gắn nhãn `baseline` và `production`
- **Version/label candidate:** Version 2, gắn nhãn `candidate`
- **Trace ID của mỗi version:**
  - Version 1 (`production` / `baseline`): `6ac48b2c5eca818e4a056eeb2e726649`
  - Version 2 (`candidate`): `04de4b0c8c0f98300189e4ae818604a8`
- **Cách promote và rollback `production`:**
  - Trên Langfuse UI: Menu Prompts -> `day13-chat` -> chọn version muốn gán nhãn -> cập nhật label `production`.
  - Ứng dụng tự động tải phiên bản prompt tương ứng theo nhãn `production` từ Langfuse mà không cần thay đổi source code hay restart service.
  - Rollback: Khi phát hiện Version 2 gặp sự cố, gán lại nhãn `production` về Version 1.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:**
  - Cấu hình chuẩn 6 panels trong `config/dashboard.yaml`:
    1. `Latency percentiles and TTFT`: Phân vị P50, P95, P99 của latency và P95 của TTFT (ngưỡng P95 <= 3000ms).
    2. `Request traffic`: Lưu lượng request theo từng phút (`count by 1m`, rate >= 1 rpm).
    3. `Error rate and retrieval success`: Tỷ lệ lỗi API (<= 2%) và tỷ lệ thành công của retrieval tool (>= 90%).
    4. `Cost over time`: Chi phí tích lũy theo USD (tổng chi phí <= $2.5).
    5. `Input and output tokens`: Tổng token vào và ra (tổng <= 50,000 tokens).
    6. `Quality proxy`: Điểm chất lượng trung bình theo heuristic (>= 0.75).
- **SLO và lý do chọn:**
  - Primary SLO: 99.5% request trong chu kỳ 28 ngày thành công và có `latency_ms <= 3000ms`.
  - Lý do: Người dùng chấp nhận độ trễ vài giây để LLM suy nghĩ và sinh câu trả lời, nhưng nếu độ trễ vượt quá 3000ms thì trải nghiệm người dùng suy giảm rõ rệt. Mục tiêu 99.5% vừa bảo đảm cam kết chất lượng dịch vụ cao, vừa để lại headroom cho các truy vấn phức tạp hoặc tail latency.
- **Cách tính error budget:**
  - Với SLO 99.5%, ngân sách lỗi (Error Budget) là `100% - 99.5% = 0.5%`.
  - Ví dụ trong chu kỳ 28 ngày hệ thống nhận được 10,000 requests, số lượng request được phép bị lỗi (HTTP 500) hoặc có độ trễ vượt quá 3000ms là tối đa: `10,000 * 0.5% = 50 requests`.
- **Ba alert và runbook tương ứng:**
  1. `HighLatencyP95` (Warning): `p95(latency_ms) > 3000ms` duy trì trong 5m. Runbook: xem panel Latency, lấy `correlation_id` có latency cao từ log, tra cứu trace trên Langfuse để xác định span chậm (`retrieval` hay `generation`), nếu do `rag_slow` thì tắt incident, nếu do prompt thì rollback prompt.
  2. `HighApiErrorRate` (Critical): `error_rate_pct > 2%` duy trì trong 3m. Runbook: xem panel Errors, lọc log `request_failed` tìm nguyên nhân ngoại lệ (vd: vector store timeout), kiểm tra span lỗi trên trace, khôi phục dịch vụ phụ thuộc hoặc tắt incident `tool_fail`.
  3. `LowRetrievalSuccessRate` (Warning): `tool_success_rate_pct < 90%` duy trì trong 5m. Runbook: xem panel Errors và Quality, lọc log `tool_success == false`, mở trace kiểm tra input/output retrieval, re-index cơ sở tri thức hoặc chuyển sang static fallback context.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Khoảng thời gian điều tra:** `2026-09-30 12:33:00` đến `12:35:00` (UTC 05:33 - 05:35)
- **Triệu chứng từ metrics:**
  - Latency P95 tăng vọt bất thường lên mức **~13,281ms** trong lúc chạy test đồng thời (concurrency 5), vượt xa ngưỡng bình thường (~160ms) và ngưỡng cảnh báo của challenge `latency_threshold_ms: 2000`.
- **Log line và correlation ID liên quan:**
  - `correlation_id`: `req-06bbc9a7` (cùng các request bị ảnh hưởng `req-43e02076`, `req-934cee2a`, `req-efd41d85`, `req-9db12ca5`).
  - Log line đại diện:
    ```json
    {"service": "api", "latency_ms": 2652, "ttft_ms": 50, "tokens_in": 47, "tokens_out": 170, "cost_usd": 0.002691, "quality_score": 0.8, "tool_name": "retrieval", "tool_success": true, "payload": {"answer_preview": "Starter answer. You should improve this output logic and add better quality chec..."}, "event": "response_sent", "correlation_id": "req-06bbc9a7", "session_id": "k4-l3b-challenge-s03", "env": "dev", "model": "claude-sonnet-4-5", "user_id_hash": "189d0a182d4e", "feature": "monitoring", "level": "info", "ts": "2026-09-30T05:34:11.849470Z"}
    ```
- **Trace ID và span gây ảnh hưởng:**
  - Trace ID: `c277b69179e85a6e66bbf786d59bc38f`
  - Span gây ảnh hưởng: Span **`retrieval`** có latency kéo dài **2.501s** (chiếm 94.3% trong tổng số 2.652s của toàn bộ request, trong khi span `generation` chỉ mất ~0.15s).
- **Root cause:**
  - Sự cố bắt nguồn từ incident `rag_slow` khiến thành phần truy xuất tài liệu (vector store / retrieval) bị nghẽn độ trễ 2.5s trên mỗi truy vấn thuộc tính năng `monitoring`.
- **Fix action:**
  - Gọi API `/incidents/rag_slow/disable` để tắt trạng thái nghẽn của retrieval, khôi phục độ trễ về dưới 5ms. Trên môi trường production thực tế: mở rộng quy mô (scale-up/out) cụm vector database, tối ưu index HNSW/IVF và bổ sung cache kết quả truy xuất cho các câu hỏi phổ biến.
- **Preventive measure:**
  - Bổ sung timeout và circuit breaker cho lời gọi retrieval (ví dụ giới hạn 1.5s): nếu quá thời gian sẽ tự động chuyển sang fallback context tĩnh thay vì chặn luồng request. Đồng thời duy trì alert `HighLatencyP95` để phát hiện và cảnh báo sớm qua Slack.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
  - Thiết kế cơ chế PII Scrubbing dạng đệ quy nhiều lớp: vừa scrub ở tầng tiền xử lý chuỗi (`summarize_text`) trước khi đưa vào metadata của trace, vừa scrub ở tầng processor của structlog (`scrub_event`) trước khi xuất file `data/logs.jsonl`. Quyết định này bảo đảm nguyên tắc "defense-in-depth" (phòng thủ đa tầng), triệt tiêu hoàn toàn nguy cơ rò rỉ dữ liệu nhạy cảm của người dùng ra cả log file cục bộ lẫn nền tảng giám sát SaaS đám mây.
- **Một lỗi/blocker đã gặp:**
  - Ban đầu khi chưa cài đặt child observations cho Langfuse, waterfall trace chỉ có một span duy nhất `lab-agent-run`. Khi latency tăng đột biến trong challenge, không thể biết độ trễ nằm ở bước gọi LLM hay bước retrieval tài liệu tri thức.
- **Cách tìm nguyên nhân và xử lý:**
  - Tham khảo tài liệu Langfuse Python SDK v4 và hướng dẫn trong `docs/GUIDE.md`, sử dụng context manager `start_as_current_observation` để phân tách rõ ràng 2 child observation `retrieval` (retriever) và `generation` (generation). Sau khi thêm, waterfall trace hiển thị rõ ràng span `retrieval` chiếm 2.5s.
- **Cách hiểu luồng Metrics → Logs → Traces:**
  - **Metrics** là lớp phát hiện triệu chứng diện rộng và mốc thời gian xảy ra bất thường (ví dụ: P95 latency nhảy vọt lên 13s lúc 12:34).
  - **Logs** cung cấp ngữ cảnh chi tiết và mã `correlation_id` của các request cụ thể bị ảnh hưởng trong khoảng thời gian đó.
  - **Traces** mổ xẻ request mang `correlation_id` đó thành cây quan sát phân tán để chỉ ra chính xác span nào (retrieval vs generation) là nguyên nhân gây chậm hoặc lỗi.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
  - Prompt trong hệ thống LLM có vai trò tương đương như code hoặc config logic nghiệp vụ: một thay đổi nhỏ về câu từ có thể làm thay đổi hoàn toàn độ dài token, chi phí và độ trễ. Quản lý prompt theo version và nhãn (`production`, `candidate`) cho phép đội ngũ kỹ thuật thử nghiệm an toàn và rollback ngay lập tức khi phát hiện regression mà không cần sửa code hay triển khai lại toàn bộ hệ thống.
- **Điều quan trọng nhất đã học:**
  - Tư duy vận hành hệ thống AI/LLMOps bài bản: không suy đoán nguyên nhân theo cảm tính mà luôn đi theo chuỗi bằng chứng xác thực từ Metrics đến Logs và Traces, đồng thời luôn đặt yếu tố an toàn dữ liệu (PII Redaction) lên hàng đầu.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**
  - Hàm đánh giá chất lượng `_heuristic_quality` hiện tại dựa trên các quy tắc heuristic đơn giản (độ dài, đối chiếu từ khóa). Trong tương lai có thể nâng cấp lên phương pháp LLM-as-a-judge hoặc mô hình phân loại đánh giá độc lập.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [x] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
