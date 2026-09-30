# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: `good_event: event == "response_sent" and latency_ms <= 3000`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` liên tục trong 5 phút
- Ảnh hưởng tới người dùng: Người dùng phải chờ lâu hơn trước khi nhận câu trả lời, trải nghiệm hội thoại bị gián đoạn, nguy cơ client timeout.
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard panel `Latency percentiles and TTFT` để xác nhận mức P95/P99 và mốc thời gian bắt đầu tăng đột biến.
  2. Lọc `data/logs.jsonl` trong khoảng thời gian đó, tìm các bản ghi `response_sent` có `latency_ms > 3000` và lấy `correlation_id`.
  3. Tra cứu `correlation_id` trên Langfuse, kiểm tra waterfall để xác định span gây chậm là `retrieval` hay `generation`.
- Mitigation tạm thời: Nếu span `retrieval` chậm do incident `rag_slow`, gọi `/incidents/rag_slow/disable`; nếu do prompt dài hoặc candidate regression, rollback label `production` về prompt version ổn định trước đó.
- Owner: `student-2A202602903`

## Alert 2

- Tên: `HighApiErrorRate`
- Severity: `critical`
- Duration: `3m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: Guardrail `error_rate_pct_max: 2` (tỷ lệ lỗi tối đa 2%)
- Điều kiện và thời gian duy trì: `error_rate_pct > 2%` liên tục trong 3 phút (tính theo tỷ lệ giữa `request_failed` và `request_received`)
- Ảnh hưởng tới người dùng: Người dùng nhận phản hồi mã lỗi HTTP 500, không nhận được câu trả lời từ hệ thống.
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard panel `Error rate and retrieval success`, kiểm tra tỷ lệ lỗi và phân bố `error_type` (ví dụ `RuntimeError`, `HTTPException`).
  2. Lọc `data/logs.jsonl` theo `event == "request_failed"`, kiểm tra `payload.detail` và lấy `correlation_id` của request lỗi gần nhất.
  3. Mở trace có cùng `correlation_id` trên Langfuse để kiểm tra span bị exception (ví dụ span `retrieval` lỗi timeout vector store).
- Mitigation tạm thời: Kiểm tra vector database và các dịch vụ phụ thuộc; nếu do incident `tool_fail`, gọi `/incidents/tool_fail/disable` để khôi phục; kích hoạt fallback knowledge retrieval nếu hạ tầng chính chưa sẵn sàng.
- Owner: `student-2A202602903`

## Alert 3

- Tên: `LowRetrievalSuccessRate`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: Guardrail `retrieval_success_rate_pct_min: 90` và `quality_score_avg_min: 0.75`
- Điều kiện và thời gian duy trì: `tool_success_rate_pct < 90%` trong 5 phút
- Ảnh hưởng tới người dùng: Hệ thống không truy xuất được tài liệu phù hợp, dẫn đến câu trả lời hallucination hoặc câu trả lời chung chung (fallback answer), làm giảm chất lượng phản hồi.
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard panel `Error rate and retrieval success` và panel `Quality proxy` để kiểm tra tỷ lệ thành công của retrieval và điểm chất lượng trung bình.
  2. Lọc `data/logs.jsonl` với điều kiện `tool_success == false` hoặc `quality_score < 0.75`, lấy `correlation_id`.
  3. Mở trace trên Langfuse theo `correlation_id`, kiểm tra span `retrieval` xem tài liệu trả về rỗng hay vector store trả về fallback.
- Mitigation tạm thời: Kiểm tra trạng thái vector store, re-index dữ liệu tri thức hoặc tạm thời chuyển luồng sang context tĩnh / fallback corpus đã được kiểm chứng.
- Owner: `student-2A202602903`
