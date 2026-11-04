/**
 * SupportIQ Copilot Demo - Pure JavaScript Client
 * Security: Strictly uses textContent to prevent XSS. No external frameworks.
 */

(function () {
  'use strict';

  // --- State ---
  let appProfiles = [];
  let currentSubmissionId = null;
  let currentRunId = null;
  let currentDraftHash = null;
  let isRetrying = false;

  // --- DOM Elements ---
  const healthDot = document.getElementById('health-dot');
  const healthText = document.getElementById('health-text');
  const intakeForm = document.getElementById('intake-form');
  const exampleSelect = document.getElementById('example-select');
  const profileSelect = document.getElementById('profile-select');
  const personalLookupToggle = document.getElementById('personal-lookup-toggle');
  const orderGroup = document.getElementById('order-group');
  const orderSelect = document.getElementById('order-select');
  const orderCustomInput = document.getElementById('order-custom-input');
  const queryInput = document.getElementById('query-input');
  const charCount = document.getElementById('char-count');
  const btnSubmit = document.getElementById('btn-submit');
  const btnClear = document.getElementById('btn-clear');
  const formMessage = document.getElementById('form-message');
  const historyList = document.getElementById('history-list');

  // Result state blocks
  const stateEmpty = document.getElementById('state-empty');
  const stateLoading = document.getElementById('state-loading');
  const stateResult = document.getElementById('state-result');

  // Result fields
  const cardAction = document.getElementById('card-action');
  const badgeAction = document.getElementById('badge-action');
  const badgeQueue = document.getElementById('badge-queue');
  const valTeam = document.getElementById('val-team');
  const valReasonVi = document.getElementById('val-reason-vi');
  const rowMissingSlots = document.getElementById('row-missing-slots');
  const valMissingSlots = document.getElementById('val-missing-slots');

  const valIntent = document.getElementById('val-intent');
  const valConfidence = document.getElementById('val-confidence');
  const valMargin = document.getElementById('val-margin');
  const valVersions = document.getElementById('val-versions');

  const valSourceCount = document.getElementById('val-source-count');
  const sourcesList = document.getElementById('sources-list');

  const cardDraft = document.getElementById('card-draft');
  const badgeDraftKind = document.getElementById('badge-draft-kind');
  const draftHashDisplay = document.getElementById('draft-hash-display');
  const draftEditor = document.getElementById('draft-editor');
  const btnApprove = document.getElementById('btn-approve');
  const btnSaveEdit = document.getElementById('btn-save-edit');
  const btnReject = document.getElementById('btn-reject');
  const btnEscalate = document.getElementById('btn-escalate');
  const feedbackMessage = document.getElementById('feedback-message');

  const valRunId = document.getElementById('val-run-id');
  const valDecisionId = document.getElementById('val-decision-id');
  const valRawReasons = document.getElementById('val-raw-reasons');
  const valMustApprove = document.getElementById('val-must-approve');

  // --- Dictionaries & Mappings ---
  const ACTION_MAP = {
    'retrieve_draft': { label: 'Đề xuất bản nháp', cls: 'badge-action-retrieve_draft' },
    'clarify': { label: 'Cần bổ sung thông tin', cls: 'badge-action-clarify' },
    'escalate': { label: 'Chuyển nhân viên hỗ trợ', cls: 'badge-action-escalate' },
    'manual_fallback': { label: 'Xử lý thủ công', cls: 'badge-action-manual_fallback' },
  };

  const REASON_VI_MAP = {
    'high_confidence_supported': 'Đầy đủ căn cứ chính sách hợp lệ và độ tin cậy đạt yêu cầu.',
    'missing_order_id': 'Thiếu mã đơn hàng để tra cứu thông tin cá nhân của khách.',
    'commerce_order_not_found': 'Không tìm thấy mã đơn hàng trong hệ thống lưu trữ.',
    'commerce_unauthorized_customer': 'Khách hàng không có quyền truy cập vào đơn hàng này.',
    'insufficient_evidence': 'Chưa có tài liệu chính sách phê duyệt phù hợp hoặc tài liệu đã hết hiệu lực.',
    'low_confidence': 'Độ tin cậy của mô hình dưới ngưỡng an toàn quy định.',
    'ambiguous_intent': 'Khoảng cách giữa các ý định quá gần nhau, chưa đủ dứt khoát.',
    'unsupported_intent': 'Ý định của câu hỏi chưa được hỗ trợ xử lý tự động.',
    'sensitive_action': 'Yêu cầu thực hiện thao tác nhạy cảm, bắt buộc nhân viên tiếp quản.',
    'explicit_human_request': 'Khách hàng yêu cầu gặp trực tiếp nhân viên tư vấn.',
    'clarify_limit_exceeded': 'Đã vượt quá số lần làm rõ cho phép, chuyển nhân viên hỗ trợ.',
    'staff_escalated_feedback': 'Nhân viên hỗ trợ chủ động chuyển cấp thủ công qua phản hồi.',
  };

  const EXAMPLES = {
    'ex-return': {
      text: 'What is your standard return policy and window?',
      profileId: 'demo-customer',
      personal: false,
      orderId: '',
    },
    'ex-track-valid': {
      text: 'Where is my package and what is the current delivery status?',
      profileId: 'demo-customer',
      personal: true,
      orderId: 'ORD-1001',
    },
    'ex-track-invalid': {
      text: 'I want to track order ORD-1002 and see the shipping details.',
      profileId: 'demo-customer',
      personal: true,
      orderId: 'ORD-1002',
    },
    'ex-missing-order': {
      text: 'Can you check why my order is delayed? I need tracking updates.',
      profileId: 'demo-customer',
      personal: true,
      orderId: '',
    },
    'ex-unsupported': {
      text: 'How much are the shipping customs fees to Tokyo Japan?',
      profileId: 'demo-customer',
      personal: false,
      orderId: '',
    },
  };

  // --- Helper Functions ---
  function generateUUID() {
    if (crypto && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function showMessage(el, text, type) {
    el.textContent = text;
    el.className = 'alert-box alert-' + type;
    el.style.display = 'block';
  }

  function hideMessage(el) {
    el.style.display = 'none';
    el.textContent = '';
  }

  function mapReasonsToVietnamese(reasons) {
    if (!reasons || reasons.length === 0) {
      return 'Không có mã lý do đặc biệt.';
    }
    const mapped = reasons.map(r => REASON_VI_MAP[r] || r);
    return mapped.join(' | ');
  }

  // --- Initialization ---
  async function checkHealth() {
    try {
      const res = await fetch('/api/demo/health');
      if (res.ok) {
        const data = await res.json();
        healthDot.className = 'status-dot status-dot-ready';
        healthText.textContent = `Hệ thống sẵn sàng (Model: ${data.model_version || 'v2'})`;
      } else {
        healthDot.className = 'status-dot status-dot-error';
        healthText.textContent = 'Dịch vụ gặp lỗi phản hồi';
      }
    } catch (e) {
      healthDot.className = 'status-dot status-dot-error';
      healthText.textContent = 'Mất kết nối máy chủ';
    }
  }

  async function loadProfiles() {
    try {
      const res = await fetch('/api/demo/profiles');
      if (!res.ok) throw new Error('Không thể tải danh sách hồ sơ');
      appProfiles = await res.json();

      profileSelect.replaceChildren();
      appProfiles.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${p.name} [${p.id}]`;
        profileSelect.appendChild(opt);
      });

      updateOrderOptions();
    } catch (err) {
      showMessage(formMessage, 'Lỗi tải hồ sơ khách hàng: ' + err.message, 'danger');
    }
  }

  function updateOrderOptions() {
    const selectedId = profileSelect.value;
    const profile = appProfiles.find(p => p.id === selectedId);

    orderSelect.replaceChildren();
    const defaultOpt = document.createElement('option');
    defaultOpt.value = '';
    defaultOpt.textContent = '-- Chọn đơn thuộc hồ sơ hoặc tự nhập --';
    orderSelect.appendChild(defaultOpt);

    if (profile && profile.allowed_orders) {
      profile.allowed_orders.forEach(ord => {
        const opt = document.createElement('option');
        opt.value = ord;
        opt.textContent = `${ord} (Đã xác thực)`;
        orderSelect.appendChild(opt);
      });
    }
  }

  async function loadHistory() {
    try {
      const res = await fetch('/api/demo/history');
      if (!res.ok) return;
      const history = await res.json();

      historyList.replaceChildren();
      if (history.length === 0) {
        const hint = document.createElement('div');
        hint.className = 'empty-hint';
        hint.textContent = 'Chưa có lịch sử trong phiên này.';
        historyList.appendChild(hint);
        return;
      }

      history.forEach(item => {
        const div = document.createElement('div');
        div.className = 'history-item';

        const leftSpan = document.createElement('span');
        const actionTag = item.result ? item.result.action : 'unknown';
        const intentTag = item.result ? item.result.predicted_intent : '';
        leftSpan.textContent = `[${actionTag}] ${intentTag}`;

        const rightSpan = document.createElement('span');
        rightSpan.style.color = '#94a3b8';
        rightSpan.style.fontSize = '0.75rem';
        rightSpan.textContent = item.run_id.substring(0, 8) + '...';

        div.appendChild(leftSpan);
        div.appendChild(rightSpan);

        div.addEventListener('click', () => {
          if (item.result) {
            renderResult(item.result);
          }
        });

        historyList.appendChild(div);
      });
    } catch (e) {
      console.warn('Could not refresh history', e);
    }
  }

  // --- Form Events ---
  exampleSelect.addEventListener('change', function () {
    const key = exampleSelect.value;
    if (!key || !EXAMPLES[key]) return;
    const ex = EXAMPLES[key];
    queryInput.value = ex.text;
    charCount.textContent = ex.text.length;
    profileSelect.value = ex.profileId;
    updateOrderOptions();
    personalLookupToggle.checked = ex.personal;
    orderGroup.style.display = ex.personal ? 'block' : 'none';
    orderSelect.value = ex.orderId || '';
    orderCustomInput.value = '';
    isRetrying = false;
    currentSubmissionId = null;
    hideMessage(formMessage);
  });

  profileSelect.addEventListener('change', updateOrderOptions);

  personalLookupToggle.addEventListener('change', function () {
    orderGroup.style.display = personalLookupToggle.checked ? 'block' : 'none';
  });

  queryInput.addEventListener('input', function () {
    charCount.textContent = queryInput.value.length;
    // Typing new query resets retry state
    if (isRetrying) {
      isRetrying = false;
      currentSubmissionId = null;
    }
  });

  btnClear.addEventListener('click', function () {
    queryInput.value = '';
    charCount.textContent = '0';
    exampleSelect.value = '';
    orderCustomInput.value = '';
    orderSelect.value = '';
    personalLookupToggle.checked = false;
    orderGroup.style.display = 'none';
    isRetrying = false;
    currentSubmissionId = null;
    hideMessage(formMessage);
    showEmptyState();
  });

  intakeForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    hideMessage(formMessage);

    const text = queryInput.value.trim();
    if (!text) {
      showMessage(formMessage, 'Vui lòng nhập nội dung câu hỏi của khách hàng.', 'warning');
      queryInput.focus();
      return;
    }

    const profileId = profileSelect.value;
    if (!profileId) {
      showMessage(formMessage, 'Vui lòng chọn hồ sơ khách hàng.', 'warning');
      profileSelect.focus();
      return;
    }

    const isPersonal = personalLookupToggle.checked;
    let orderId = null;
    if (isPersonal) {
      orderId = orderCustomInput.value.trim() || orderSelect.value.trim() || null;
    }

    // Keep submissionId if retrying after network error, else generate new
    if (!isRetrying || !currentSubmissionId) {
      currentSubmissionId = generateUUID();
    }

    const payload = {
      submission_id: currentSubmissionId,
      profile_id: profileId,
      text: text,
      is_personal_lookup: isPersonal,
      order_id: orderId,
    };

    setLoadingState(true);

    try {
      const res = await fetch('/api/demo/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        isRetrying = true; // allow retrying with same submissionId
        if (res.status === 409) {
          throw new Error('Xung đột mã yêu cầu (409): Submission ID đã được dùng với nội dung khác.');
        } else if (res.status === 422) {
          throw new Error('Dữ liệu không hợp lệ (422): Trường yêu cầu không đúng định dạng.');
        } else {
          throw new Error(errorData.detail || `Lỗi máy chủ (${res.status})`);
        }
      }

      const result = await res.json();
      isRetrying = false; // success, can reset retry flag
      renderResult(result);
      loadHistory();
    } catch (err) {
      setLoadingState(false);
      showMessage(formMessage, err.message, 'danger');
    }
  });

  // --- Result Rendering ---
  function showEmptyState() {
    stateEmpty.style.display = 'block';
    stateLoading.style.display = 'none';
    stateResult.style.display = 'none';
  }

  function setLoadingState(loading) {
    btnSubmit.disabled = loading;
    if (loading) {
      stateEmpty.style.display = 'none';
      stateLoading.style.display = 'block';
      stateResult.style.display = 'none';
    } else {
      stateLoading.style.display = 'none';
    }
  }

  function renderResult(data) {
    setLoadingState(false);
    stateEmpty.style.display = 'none';
    stateLoading.style.display = 'none';
    stateResult.style.display = 'flex';

    currentRunId = data.run_id;
    currentDraftHash = data.draft_hash;
    hideMessage(feedbackMessage);

    // 1. Action Card
    const actionInfo = ACTION_MAP[data.action] || { label: data.action, cls: 'badge-neutral' };
    badgeAction.textContent = actionInfo.label;
    badgeAction.className = 'badge ' + actionInfo.cls;
    badgeQueue.textContent = `Hàng đợi: ${data.target_queue || 'standard'}`;
    valTeam.textContent = data.requested_team || 'general_support';
    valReasonVi.textContent = mapReasonsToVietnamese(data.reason_codes);

    if (data.missing_slots && data.missing_slots.length > 0) {
      rowMissingSlots.style.display = 'flex';
      valMissingSlots.textContent = data.missing_slots.join(', ');
    } else {
      rowMissingSlots.style.display = 'none';
    }

    // 2. Intent & Metrics
    valIntent.textContent = data.predicted_intent || '--';
    if (data.confidence !== null && data.confidence !== undefined) {
      valConfidence.textContent = Number(data.confidence).toFixed(2);
    } else {
      valConfidence.textContent = 'Chưa có';
    }
    if (data.margin !== null && data.margin !== undefined) {
      valMargin.textContent = Number(data.margin).toFixed(2);
    } else {
      valMargin.textContent = 'Chưa có';
    }
    valVersions.textContent = `Mô hình: ${data.model_version || 'unknown'} | CS: ${data.policy_version || 'v2'}`;

    // 3. Evidence Sources
    sourcesList.replaceChildren();
    const sources = data.sources || [];
    valSourceCount.textContent = `${sources.length} nguồn`;

    if (sources.length === 0) {
      const hint = document.createElement('div');
      hint.className = 'empty-hint';
      hint.textContent = 'Chưa có nguồn tài liệu trích dẫn phù hợp.';
      sourcesList.appendChild(hint);
    } else {
      sources.forEach(src => {
        const item = document.createElement('div');
        item.className = 'source-item';

        const header = document.createElement('div');
        header.className = 'source-item-header';

        const titleSpan = document.createElement('span');
        titleSpan.className = 'source-title';
        titleSpan.textContent = src.title || src.doc_id;

        const metaSpan = document.createElement('span');
        metaSpan.className = 'source-meta';
        const vText = src.version ? `v${src.version}` : 'Chưa có';
        const scoreText = src.score ? ` (Khớp: ${src.score})` : '';
        metaSpan.textContent = `${src.doc_id} · ${vText}${scoreText}`;

        header.appendChild(titleSpan);
        header.appendChild(metaSpan);

        const snippetDiv = document.createElement('div');
        snippetDiv.className = 'source-snippet';
        snippetDiv.textContent = src.snippet || 'Không có đoạn trích.';

        item.appendChild(header);
        item.appendChild(snippetDiv);
        sourcesList.appendChild(item);
      });
    }

    // 4. Draft Card
    if (data.draft_body) {
      cardDraft.style.display = 'block';
      draftEditor.value = data.draft_body;
      badgeDraftKind.textContent = data.draft_kind === 'template' ? 'Mẫu minh họa (Template)' : 'Sinh bởi LLM';
      draftHashDisplay.textContent = `Hash: ${data.draft_hash ? data.draft_hash.substring(0, 12) + '...' : '--'}`;
      btnApprove.disabled = false;
      btnSaveEdit.disabled = false;
    } else {
      cardDraft.style.display = 'block';
      draftEditor.value = 'Không có bản nháp cho hành động này.';
      badgeDraftKind.textContent = 'Không áp dụng';
      draftHashDisplay.textContent = 'Hash: --';
      btnApprove.disabled = true;
      btnSaveEdit.disabled = true;
    }

    // 5. Tech Details
    valRunId.textContent = data.run_id;
    valDecisionId.textContent = data.decision_id || '--';
    valRawReasons.textContent = JSON.stringify(data.reason_codes || []);
    valMustApprove.textContent = String(data.must_human_approve);
  }

  // --- Feedback Actions ---
  async function sendFeedback(action, editedText = null) {
    if (!currentRunId) return;
    hideMessage(feedbackMessage);

    const payload = {
      action: action,
      draft_hash: currentDraftHash || '',
      edited_text: editedText,
    };

    try {
      const res = await fetch(`/api/demo/runs/${currentRunId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Lỗi phản hồi (${res.status})`);
      }

      const fbData = await res.json();
      if (action === 'edit' && fbData.current_draft_hash) {
        currentDraftHash = fbData.current_draft_hash;
        draftHashDisplay.textContent = `Hash: ${currentDraftHash.substring(0, 12)}...`;
        showMessage(feedbackMessage, 'Đã lưu chỉnh sửa bản nháp thành công! (Cần duyệt lại phiên bản mới)', 'success');
      } else if (action === 'approve') {
        showMessage(feedbackMessage, 'Đã ghi nhận duyệt bản nháp thành công.', 'success');
      } else if (action === 'reject') {
        showMessage(feedbackMessage, 'Đã ghi nhận từ chối bản nháp.', 'warning');
      } else if (action === 'escalate') {
        showMessage(feedbackMessage, 'Đã ghi nhận chuyển cấp xử lý cho nhân viên hỗ trợ.', 'danger');
      }
    } catch (err) {
      showMessage(feedbackMessage, 'Lỗi ghi nhận phản hồi: ' + err.message, 'danger');
    }
  }

  btnApprove.addEventListener('click', () => sendFeedback('approve'));
  btnSaveEdit.addEventListener('click', () => {
    const text = draftEditor.value.trim();
    if (!text) {
      showMessage(feedbackMessage, 'Bản nháp không được để trống.', 'warning');
      return;
    }
    sendFeedback('edit', text);
  });
  btnReject.addEventListener('click', () => sendFeedback('reject'));
  btnEscalate.addEventListener('click', () => sendFeedback('escalate'));

  // --- Boot ---
  checkHealth();
  loadProfiles();
  loadHistory();
})();
