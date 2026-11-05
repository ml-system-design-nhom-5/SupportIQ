# Codebase & Test Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Giảm trùng lặp và phụ thuộc môi trường trong code/test SupportIQ, giữ nguyên hành vi, hợp đồng API, safety gates và khả năng tái hiện các lỗi đã sửa.

**Architecture:** Refactor từng phần trên cấu trúc hiện tại. Phân tách pure logic, runtime dependencies và test doubles; gom regression theo hành vi thay vì theo đợt review. Test mặc định chạy offline trên CPU với dữ liệu nhỏ tự chứa; model/GPU/live được chọn rõ ràng.

**Tech Stack:** Python .venv, pytest, FastAPI/httpx, SQLite, Pydantic; tái sử dụng dependencies hiện có. Không thêm framework orchestration, DI container, test runner hoặc monorepo tooling.

**Spec:** Phạm vi cleanup và tiêu chí nghiệm thu trong tài liệu này; giữ các hợp đồng ở [system evaluation design](../specs/2026-11-05-system-evaluation-design.md), [kế hoạch hoàn thiện](2026-11-05-supportiq-completion.md) và [biên bản 8 lỗi](../../review-eight-fixes.md).

Trạng thái: kế hoạch để review, chưa thực thi. Lượt khảo sát chỉ đọc code; không xóa cache, di chuyển file hoặc chạy benchmark trả phí.

## 1. Hiện trạng làm căn cứ

Khảo sát ngày05-11-2026:

- `pipeline/evaluation/`: 21 file Python, khoảng6.405 dòng; `system_execution.py`888 dòng, chứa mock encoder/client, factory, execution và oversight scenarios. `execute_system_case` khoảng280 dòng.
- `assess_system.py` chứa human annotation, ML provenance, product study, assessment publisher và CLI. Hai nơi có tên `summarize_http_results` với hợp đồng/phạm vi khác nhau (`system_performance.py`, `complete_system_report.py`). Không thể gom chỉ bằng tên.
- `tests/`: 44 file Python, khoảng9.540 dòng. Các file `test_system_review_probes.py`, `..._v2.py`, `test_review_eight_fixes.py` ghi lịch sử sửa lỗi, nhưng ca kiểm tra cùng một domain nằm rải rác.
- Fixture lớn: `make_eval_fixture` khoảng197 dòng; `make_comparison_fixture` khoảng129 dòng; benchmark/policy/release/annotation fixtures được lặp ở nhiều file.
- `pytest.ini` mới có pythonpath và cấu hình asyncio; chưa phân loại resource profile. `test_torch_cuda.py` assert CUDA ngay trong suite thông thường. Một số unit/integration test dùng BGE/model/KB local thật hoặc patch `Path.exists` toàn cục.
- Test API đã có `fake_llm` offline và `tests/annotation_fixtures.py`; cần giữ test doubles rõ ràng, không để helper làm dữ liệu sai trở thành hợp lệ.
- `.gitignore` bỏ qua `.pytest_cache/`, nhưng nhiều `.pytest-*`/`.review-system-probe-*` còn nổi ở root. Đây là cache ứng viên, không có nghĩa mọi thư mục chưa tracked đều là rác.
- Working tree đang có code/data/docs mới chưa commit. Mốc kiểm chứng gần nhất là382 tests pass, không phải một lần chạy mới trong lượt lập kế hoạch này.

## 2. Global Constraints

- Cleanup giữ hành vi: không đổi classifier, embedding, threshold, prompt, policy, KB, nội dung gold hoặc cách tính gate để làm test dễ pass.
- Không sửa `docs/CHỦ ĐỀ 1.md`; giữ API demo, ML service, CLI hiện có và schema artifact/version đã phát hành.
- Không xóa `.env`, `.venv`, `.git`, model weights, dữ liệu gốc, `ai-for-production.zip`, benchmark v1/v2/v3, release manifests, SQLite runtime, artifact hoặc biên bản phê duyệt của người dùng.
- Không sửa checksum của run cũ để “sửa” artifact. Nếu cần diễn giải mới, tạo assessment/report version mới.
- Không giảm coverage bằng skip/xóa assertion, không gắn marker để giấu test đang fail. Một scenario chỉ được bỏ bản test trùng khi đã có test thay thế tương đương.
- Không paid/network call trong default suite; không đọc API key thật. Loopback chỉ cho integration test được đánh dấu rõ.
- Unit/default suite phải chạy khi không có CUDA, cache Hugging Face, model thật, ML service, `.env` hoặc dữ liệu local bị gitignore.
- Test code dùng fake credentials và dữ liệu tổng hợp. Helper fixture không tự thêm approval, verdict, actor hoặc attestation cho trường hợp đang kiểm tra validation.
- Refactor thuần di chuyển dùng test hiện có; thêm test khi thiếu coverage, sửa bug theo RED→GREEN và ghi rõ tách khỏi cleanup. Không viết test chỉ để khẳng định tên file hoặc sao chép implementation.
- Không commit/push/merge hoặc dọn toàn bộ working tree tự động. Khi triển khai, dùng branch/workspace riêng và chỉ stage file thuộc từng task; bảo toàn mọi thay đổi đã có.

## 3. Phương án và lựa chọn

| Cách làm | Đánh đổi |
| --- | --- |
| Chỉ formatter và xóa cache | Ít rủi ro, nhưng không giải quyết unit test đòi GPU/model và module evaluation quá nhiều trách nhiệm |
| Cleanup tăng dần theo domain, có baseline và đối chiếu scenario | Khuyến nghị: thay đổi nhỏ, dễ rollback, giữ nguyên chức năng |
| Viết lại backend/evaluation hoặc chuyển toàn bộ cấu trúc repo | Phạm vi lớn, dễ mất guardrail/provenance; không cần cho yêu cầu này |

Thứ tự đề xuất: baseline → isolation/fixtures → gom tests → refactor evaluation → lifecycle/import cleanup → cache/docs. Việc xóa file là bước cuối sau khi chứng minh đã không còn caller hoặc đã có bản thay thế.

## 4. Review Focus

1. Native SQLite deadline và worker restart bị mất khi gom review tests: giữ probe late-write thật và kill/join đúng worker — Task4/5.
2. Fixture mặc định làm annotation/policy sai tự hợp lệ: invalid inputs phải được tạo và giữ nguyên; không normalize production input trong helper test — Task3.
3. Mock/live imports gây tải weights hoặc đọc credential khi collect/default test: chặn egress, lazy import và chọn marker đúng — Task2/5.
4. Gom hai hàm latency làm đổi percentile, denominator hoặc lẫn mock/live: characterization trước extraction, giữ rõ measurement_scope và branch mix — Task6.
5. Dọn cache chạm vào artifact/DB, junction/symlink hoặc file tracked: dry-run, resolve containment, tracked-path check và explicit allowlist — Task8.

## 5. File map và ranh giới thay đổi

| Files | Công việc |
| --- | --- |
| `pytest.ini`, `tests/conftest.py`, `tests/README.md` (new) | Profiles/markers, offline guard và lệnh chạy |
| `tests/fixtures/factories.py` (new), `tests/annotation_fixtures.py` | Fixture nhỏ, có nghĩa; chuyển helper sau khi sửa hết caller |
| `tests/unit/`, `tests/integration/`, `tests/evaluation/` | Gom theo domain; integration giữ process/HTTP/SQLite, evaluation giữ model thật |
| `pipeline/evaluation/mock_dependencies.py` (new) | Mock encoder/client chỉ cho profile simulated |
| `pipeline/evaluation/system_dependencies.py` (new) | SystemDependencies, factory và budgeted client wrapper |
| `pipeline/evaluation/system_execution.py` | Còn logic execute/normalize; public import tương thích trong đợt chuyển |
| `pipeline/evaluation/oversight_scenarios.py` (new) | Kịch bản demo oversight, audit facts |
| `pipeline/evaluation/latency_metrics.py` (new) | Pure percentile/branch aggregation, không gửi HTTP |
| `pipeline/evaluation/annotation_metrics.py`, `ml_provenance.py`, `product_metrics.py` (new) | Tách ba domain khỏi `assess_system.py` nếu mức giảm coupling có ích |
| `apps/demo/app.py`, `apps/ml_inference/app.py` | Lifespan thay on_event, resource ownership rõ |
| `.gitignore`, `scripts/clean_test_cache.ps1` (new) | Một nơi chứa temp, dry-run cleanup chỉ cache được phép |
| `docs/codebase-cleanup-log.md` (new) | Baseline, node-ID/scenario mapping, file move/delete inventory và kết quả |

Không tách thêm mỗi helper thành một file. Giữ `run_evaluation`, `run_system_evaluation`, `run_comparison`, `assess_system`, `complete_system_report` là entrypoints ổn định; chỉ giảm trùng lặp phần thực sự có cùng hợp đồng.

## Task 1: Đóng baseline và danh mục phải bảo toàn

**Files:** Create `docs/codebase-cleanup-log.md`; đọc các manifest/config/CLI/tests hiện có. Không sửa logic.

**Interfaces:** Inventory ghi old node_id, domain, scenario, critical assertions, resource profile, target node_id và replacement reason. Đây là bảng đối chiếu hành vi, không là assertion số test phải bằng382 vĩnh viễn.

- [ ] Ghi branch/HEAD, diff/untracked inventory, phiên bản Python/dependencies, phần nào có model/cache và điều kiện chạy. Không đưa `.env` content hoặc credentials vào log.
- [ ] Chạy `python -m pytest --collect-only -q` bằng `.venv\Scripts\python.exe`; lưu node IDs và collection/import errors. Không tự đổi golden files.
- [ ] Chạy regression offline hiện tại với temp trong workspace, lưu pass/fail/warnings/durations; ghi riêng dependency/hardware failures, không đổi chúng thành pass.
- [ ] Lập danh mục safety/provenance invariants cần bảo toàn: cross-session/hash, actor/time/evidence, release checksum/CV folds, source ACL/version, near-duplicate leakage, timeout late write, idempotency/budget và metric denominator.
- [ ] Đánh dấu file có caller/CLI/import động trước khi coi là dead code. Lưu checksum manifest lịch sử để so sau cleanup.
- [ ] Checkpoint: mọi failure có nguyên nhân được ghi; không bắt đầu xóa/gom test khi chưa có mapping.

## Task 2: Profiles kiểm thử và temp directory ổn định

**Files:** Modify `pytest.ini`, `tests/conftest.py`, `tests/unit/test_torch_cuda.py`; create `tests/README.md`, config tests khi cần.

**Interfaces:** Markers `integration`, `real_model`, `cuda`, `live`; option `--run-live` mặc định false. Chỉ `live` được đọc credential và egress sau opt-in explicit. Default `-m "not real_model and not cuda and not live"`; lệnh CLI override marker cho profile chuyên biệt. `tmp_path` nằm dưới `tmp/pytest` qua một basetemp chuẩn cho mỗi run.

- [ ] RED: default run không gọi HF/download/remote HTTP và không cần `.env`; import/collect khi CUDA unavailable vẫn thành công. Test local HTTP server được marker integration dùng loopback thật.
- [ ] RED: live marker không opt-in bị skip với lý do rõ và không đọc key; `--run-live` thiếu key/config phải fail preflight, không chạy mock thay thế.
- [ ] Implement strict markers (`--strict-markers`), chọn testpaths và offline fixture guard. Guard cho integration chỉ allow loopback; mock HTTP transport vẫn hoạt động. Chặn network không được chặn SQLite/subprocess nội bộ.
- [ ] Chuyển CUDA smoke sang marker cuda; khi người vận hành chọn GPU profile thì kiểm tra CUDA thật, không coi unavailable là GPU pass. Real-model tests explicit và báo rõ thiếu asset; default không âm thầm chạy cache máy tác giả.
- [ ] Chuẩn hóa temp dưới `tmp/pytest/<run-id>` để không ghi đè run song song; override bằng `--basetemp` khi cần. Không thêm cleanup tự động xóa DB đang có worker sử dụng.
- [ ] GREEN: chạy default CPU/offline và integration loopback; kiểm tra không có remote socket/weights loading ngoài profile. Commit profile/config thay đổi riêng nếu thực hiện commit.

## Task 3: Fixture factories rõ nghĩa, giảm dữ liệu lặp

**Files:** Create `tests/fixtures/__init__.py`, `tests/fixtures/factories.py`; modify root/domain conftest và những test dùng fixture lớn.

**Interfaces đề xuất:**

- `make_system_case(**overrides) -> SystemCase` tạo một case nhỏ.
- `write_suite_fixture(root: Path, cases: list[dict], kb: list[dict]) -> dict[str, Path]` ghi snapshot/checksum thực trong tmp_path.
- `make_release_fixture(root: Path, *, n_folds: int = 10) -> dict[str, Path]` ghi CV descriptor/report/model placeholder bytes hợp đồng; không deserialize placeholder như model thật.
- `make_human_annotation(case_id: str, draft: str, claims: list[dict], *, reviewed_at: str, reviewer: str) -> dict` yêu cầu actor/time rõ; không quyết định claim verdict.
- `make_mock_runner(root: Path, *, prediction, retrieval_result, llm_result) -> PipelineRunner` có dependencies explicit và SQLite riêng.

- [ ] Đọc từng caller của `make_eval_fixture`, `make_comparison_fixture`, `mock_verified_inputs`, `reviewed_annotations`; chỉ trích phần giống nhau và cần cho test thực sự.
- [ ] Giữ nguyên negative cases bằng dữ liệu raw/override tường minh: thiếu actor/approval/checksum, invalid NaN, wrong version, no draft. Factory không tự “sửa” field mà test cố ý làm sai.
- [ ] Chuyển fixture một domain trước, chạy toàn bộ test domain đó; đối chiếu artifact values/assertions trước/sau. Không scope session cho SQLite hoặc runner mutable.
- [ ] Giảm fixture từ vài trăm dòng xuống dữ liệu tối thiểu cho cùng hành vi; release checksum test dùng bytes nhỏ, ML training test vẫn cần dữ liệu đủ class/fold để kiểm tra thật.
- [ ] Tách fake provider thành các response có tên: grounded success, refusal, bad citation, timeout, malformed JSON. Không dùng một draft return-policy cố định cho mọi nghiệp vụ và suy ra quality pass.
- [ ] GREEN unit/domain tests; xóa helper cũ chỉ sau khi không còn import. Tài liệu ghi fixture là dữ liệu tổng hợp, không phải approval hay benchmark sản phẩm.

## Task 4: Gom regression theo domain và bỏ bản trùng có chứng cứ

**Files:** Reorganize ba file review probes và completion tests; target dưới `tests/unit/evaluation/`, `tests/unit/intent/`, `tests/unit/retrieval/`, `tests/unit/llm/`, `tests/integration/`.

**Interfaces:** Public behavior/test assertions giữ nguyên; mapping old→new trong cleanup log. Test tên theo failure/behavior, issue ID cũ giữ trong docstring/comment khi hữu ích.

| Nguồn | Đích theo hành vi |
| --- | --- |
| review probes + completion reporting | `tests/unit/evaluation/test_ml_provenance.py`, `test_human_assessment.py`, `test_quality_gates.py` |
| timeout probes + completion deadline + system server | `tests/integration/test_worker_lifecycle.py`, `test_worker_native_deadline.py` |
| retrieval/completion knowledge tests | `tests/unit/retrieval/test_eligibility.py`, `test_relevance.py`, `test_publication.py` |
| pooling/citation/evidence probes | `tests/unit/llm/test_grounding.py`, `tests/unit/intent/test_http_client.py`, `tests/integration/test_evidence_persistence.py` |
| demo feedback/session probes | `tests/integration/test_demo_oversight.py` với nhiều action được parametrize |

- [ ] Di chuyển từng nhóm, sửa import/mock target tới nơi sở hữu symbol thật. Không để monkeypatch compatibility facade trong khi implementation gọi module mới và test vô tình không intercept.
- [ ] Chỉ parametrize các input có cùng invariant và setup; giữ test riêng cho boundary/path khác nhau. Sleep timeout test và native SQLite late-write test không tương đương, không bỏ native test.
- [ ] Thay global `patch.object(Path, 'exists', return_value=True)` bằng manifest/artifact thật trong tmp_path; HTTP errors qua MockTransport, không dựa endpoint máy đang chạy.
- [ ] Với từng test định xóa, chỉ ra replacement có đủ assertions/numerator/side effects. Bỏ bản test lỗi thời đã kiểm tra nhầm process/fixture nhưng giữ probe đúng hành vi trong nhóm mới.
- [ ] Chạy collection và test domain sau mỗi move; không duplicate module basename gây import mismatch. Đối chiếu tất cả invariants Task1 còn có người sở hữu.
- [ ] Checkpoint: số test có thể giảm/tăng do parametrize; không đặt KPI “giảm số test” hoặc “giảm coverage”. Báo số scenario còn bao phủ và lý do bỏ từng bản trùng.

## Task 5: Tách dependencies, mock và oversight khỏi execution

**Files:** Create `mock_dependencies.py`, `system_dependencies.py`, `oversight_scenarios.py`; modify `system_execution.py`, server/runners/callers và test imports.

**Interfaces giữ nguyên:** `SystemDependencies`, `build_system_dependencies(inputs, profile, runtime_dir, start_server=True)`, `execute_system_case(case, deps, attempt_id, scope='e2e', in_worker=False)`, `run_component_probes`, `run_oversight_scenarios`.

- [ ] Trước extraction, có characterization cho profile mock không egress; live không dùng mock; server worker không khởi tạo server đệ quy; nonce/pinned inputs/ledger tồn tại qua restart.
- [ ] Chuyển `MockPolicyEncoder`, `MockIntentClient`, `MockLLMClient` và stopwords sang `mock_dependencies.py`. Module này chỉ được factory profile mock dùng, không import package `tests` từ runtime.
- [ ] Chuyển dependency dataclass/factory/budget wrapper sang `system_dependencies.py`; dùng lazy imports/TYPE_CHECKING để không có vòng lặp execution↔server↔performance.
- [ ] Chuyển oversight scenario implementation sang `oversight_scenarios.py`; execution còn điều phối case, fault injection và normalize result. Giữ `isolated_call.py` riêng; không thay process kill/join bằng thread vì muốn code ngắn hơn.
- [ ] Giữ re-export tối thiểu từ `system_execution.py` trong giai đoạn chuyển; cập nhật internal caller dùng owner mới. Không làm một tầng class hierarchy/framework mới.
- [ ] Chạy native deadline, HTTP worker, ledger, cross-session và evidence snapshot tests; kiểm tra mọi resource được close cả khi exception. Chạy mock CLI tạo đủ artifact/checksum mới.
- [ ] Checkpoint: CLI/schema/action/reason/idempotency không đổi. Nếu phát hiện bug, ghi task sửa riêng có RED→GREEN, không lẫn vào diff di chuyển.

## Task 6: Gom metrics/report logic và tách assessment domains

**Files:** Create `latency_metrics.py`, có thể tạo `annotation_metrics.py`, `ml_provenance.py`, `product_metrics.py`; modify performance/supplement/report/assess modules.

**Interfaces:** Hàm chuẩn đề xuất `summarize_latency(results: list[CaseResult], *, measurement_scope: str, expected_count: int, warmup_count: int) -> dict`; hai hàm cũ là adapter giữ output keys cũ. ML importer và annotation/product evaluator giữ signature công khai; `assess_run` vẫn publish immutable assessment.

- [ ] Characterize cả hai `summarize_http_results`: median/nearest-rank hay quantile hiện dùng, sample counts, branch theo llm_called, error/timeout, zero samples, mixed profile. Không ép chúng thành cùng nghĩa nếu kết quả khác.
- [ ] Trích các primitives thực sự chung (percentile, branch counters), gắn measurement_scope tường minh; compatibility adapters bảo toàn key/value. Không đổi estimator hoặc success criteria trong task cleanup.
- [ ] Tách pure annotation metrics, CV lineage verification và paired product metrics khỏi I/O publisher/CLI nếu giảm coupling. Tránh nhân đôi `EvaluationError`, hash/path validation ở từng module.
- [ ] Chuẩn hóa JSON/manifest I/O qua helper đang có sau khi so strictness; không thay fail-closed checksum bắt buộc bằng helper permissive. Không deserialize pickle từ benchmark input.
- [ ] GREEN characterization và negative tests: empty/duplicate/missing predictions, below-threshold rounding, AI-as-human, string false attestation, tampered report và wrong release.
- [ ] Kiểm tra report tạo mới khớp metric scope; import/CLI cũ hoạt động; dữ liệu lịch sử không sửa. Loại re-export thừa sau khi đã kiểm caller được hỗ trợ.

## Task 7: Lifecycle, typing/imports và dependency declarations

**Files:** Modify `apps/demo/app.py`, `apps/ml_inference/app.py`, các module đã refactor, `pipeline/requirements*.txt`, `apps/demo/requirements.txt`, README setup tương ứng.

**Interfaces:** FastAPI lifespan sở hữu startup/shutdown; client được inject do caller sở hữu, client factory tạo do app/deps sở hữu. Không đổi route/payload/status code.

- [ ] Characterize startup load model một lần, shutdown đóng client một lần, cleanup partial startup failure và TestClient lifespan hoạt động; API không khởi tạo model khi chỉ collect unit test.
- [ ] Chuyển `on_event` sang lifespan sau tests; giữ model readiness/label bijection/checksum. Không suppress warnings để làm suite “sạch”.
- [ ] Xóa import/biến/comment lỗi thời chỉ khi call graph và tests xác nhận. Chỉnh type hints tại boundary có ích; không chuyển toàn repo sang typing framework hoặc format mọi file ngoài phạm vi.
- [ ] Đối chiếu dependencies thực với requirements hiện có, đặc biệt cloudpickle/pytest/httpx/torch optional profile; chỉ gỡ dependency khi không còn caller/runtime/test dùng. Không nâng version hàng loạt trong cleanup.
- [ ] Giữ CPU backend/default test hoạt động, profile GPU chọn explicit. Smoke import/CLI trên setup được khai báo, ghi rõ dependency optional.
- [ ] GREEN targeted lifecycle tests, CLI `--help`, regression; diff không trộn thay đổi nghiệp vụ hoặc secrets.

## Task 8: Cache và thư mục dư — dry-run trước khi xóa

**Files:** Modify `.gitignore`; create `scripts/clean_test_cache.ps1`; update `tests/README.md`, cleanup inventory.

**Interfaces:** `clean_test_cache.ps1` mặc định chỉ in absolute-path/size/reason; `-Apply` mới xóa danh sách đã kiểm. Allowlist root `.pytest-*`, `.pytest_cache`, `.review-system-probe-*`, `__pycache__` ngoài env và temp mới dưới `tmp/pytest`. Không gộp SQLite/log/artifact vào cache chỉ vì không tracked.

- [ ] Kiểm tra dry-run: path resolve trong repo, không symlink/junction/reparse point, không tracked files, không `.git/.venv/data/artifacts/tmp` ngoài nhánh temp được phép; có process đang dùng test temp thì từ chối Apply.
- [ ] `.gitignore` chỉ bổ sung các pattern cache cụ thể; không ignore rộng tất cả dotfiles/test files để giấu thay đổi code chưa commit.
- [ ] Liệt kê thư mục rỗng/`.gitkeep` như ứng viên riêng. Chỉ bỏ sau khi kiểm tra runtime, packaging, README và lịch sử; `ml/releases` không phải rác vì chứa manifest.
- [ ] Khi thực thi cleanup, dùng native PowerShell `Remove-Item -LiteralPath` trên danh sách absolute đã xác minh, không ghép cmd qua shell khác; không xóa recursive đường dẫn chưa kiểm containment.
- [ ] Kiểm lại checksum artifact/model/approval và status working tree. Script bị policy chặn thì báo rõ, không thử shell/tool khác để vượt chặn.
- [ ] Cache dọn xong phải chạy được test lại; không lấy dung lượng giảm làm bằng chứng code tốt hơn.

## Task 9: Kiểm chứng tổng thể và bàn giao

**Files:** Update cleanup log, `tests/README.md`, `pipeline/evaluation/README.md`; chỉ cập nhật báo cáo để liên kết bằng chứng mới, không đổi điểm benchmark.

- [ ] Chạy collection/default CPU/offline trên workspace không có model, `.env`, CUDA hoặc service; dùng fixture paths thay file local. Thử trong clean checkout sau khi các file cần thiết đã được đưa vào changeset, không dựa untracked file.
- [ ] Chạy integration loopback/process/SQLite, kiểm tra không còn worker giữ handle sau suite. Chạy real_model/cuda riêng nếu assets/hardware có; thiếu thì ghi not_run với lý do, không thêm vào số pass default.
- [ ] Chạy characterization artifact/manifest trước-sau, `git diff --check`, kiểm tra link README và secret scan không in key. Live paid benchmark không cần cho cleanup giữ hành vi; chỉ chạy khi explicit có yêu cầu/ngân sách mới.
- [ ] Đối chiếu scenario matrix: mọi guardrail trước đây vẫn có test đúng tầng; không giảm assertion meaningful, không bỏ missing/error cases khỏi denominator.
- [ ] Báo thời gian default/integration theo durations trên cùng máy và cache condition; đây là chỉ số cải thiện DX, không là latency sản phẩm. Không cam kết trước mức giảm phần trăm.
- [ ] Bàn giao file move/delete map, CLI/test commands, optional dependency profiles, warnings còn lại và điều chưa kiểm. Có checkpoint rollback cho từng nhóm; chưa push/merge khi chưa có chỉ dẫn.

## 6. Lệnh chạy đích

Lệnh sau là giao diện dự kiến sau Task2, chưa tuyên bố đã hoạt động ở code hiện tại:

```powershell
# Default: offline CPU, gồm integration loopback nhẹ, không model/GPU/live
.venv\Scripts\python.exe -m pytest --basetemp=tmp/pytest/default-run -q

# Pure unit tests để feedback nhanh
.venv\Scripts\python.exe -m pytest tests/unit --basetemp=tmp/pytest/unit-run -q

# Process/SQLite/HTTP thật trên loopback
.venv\Scripts\python.exe -m pytest -m "integration and not real_model and not live and not cuda" --basetemp=tmp/pytest/integration-run -q

# Model local / GPU: chọn rõ, không tự tải weights
.venv\Scripts\python.exe -m pytest -m "real_model and not live" --basetemp=tmp/pytest/model-run -q
.venv\Scripts\python.exe -m pytest -m cuda --basetemp=tmp/pytest/cuda-run -q

# Chỉ liệt kê cache; không xóa
.\scripts\clean_test_cache.ps1
```

Mỗi run đồng thời cần basetemp khác nhau. Không chạy lệnh live trong CI/default; README live chỉ dẫn opt-in riêng và budget preflight.

## 7. Tiêu chí hoàn thành và thứ tự

Thực hiện Task1→2→3→4→5→6→7→8→9. Có thể dừng sau một checkpoint với phần đã refactor vẫn hoạt động; không cần di chuyển toàn bộ test repo trong một commit.

Hoàn thành khi default suite offline/CPU tự chứa; test resource-heavy có profile rõ; các ca lỗi lịch sử còn được bảo vệ; evaluation có trách nhiệm dễ đọc; không làm đổi API/artifact/gate; cache dọn bằng allowlist kiểm chứng; manifest/approval cũ không thay đổi. Không đặt số dòng, số file hoặc số test giảm thành mục tiêu bắt buộc.
