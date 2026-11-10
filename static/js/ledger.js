/* 记账流水页：模态框新增/编辑、删除、分页（fetch，不整页刷新表格区） */
(function () {
  "use strict";

  var tableBody = document.getElementById("ledger-rows");
  if (!tableBody) return;

  var pageEl = document.getElementById("ledger-pageinfo");
  var prevBtn = document.getElementById("btn-prev-page");
  var nextBtn = document.getElementById("btn-next-page");
  var addBtn = document.getElementById("btn-add-record");
  var modalEl = document.getElementById("record-modal");
  var modalTitleEl = document.getElementById("record-modal-title");
  var recordForm = document.getElementById("record-form");
  var recordIdEl = document.getElementById("record-id");
  var recordDateEl = document.getElementById("record-date");
  var recordCatEl = document.getElementById("record-category");
  var recordAmountEl = document.getElementById("record-amount");
  var recordNoteEl = document.getElementById("record-note");
  var recordErrorEl = document.getElementById("record-error");

  var currentMonth = window.location.search.match(/[?&]month=(\d{4}-\d{1,2})/);
  var MONTH = currentMonth ? currentMonth[1] : null;

  var modal = modalEl ? new bootstrap.Modal(modalEl) : null;
  var paging = { next: null, prev: null };

  function getCookie(name) {
    var m = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[2]) : "";
  }

  function requestJSON(url, options) {
    options = options || {};
    var headers = options.headers || {};
    headers["X-CSRFToken"] = getCookie("csrftoken");
    if (options.json !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.json);
    }
    options.headers = headers;
    return fetch(url, options).then(function (resp) {
      if (!resp.ok) {
        return resp.json().catch(function () { return {}; }).then(function (data) {
          var msg = data.error || (data.errors && "表单校验失败，请检查金额/日期") || ("请求失败（" + resp.status + "）");
          throw new Error(msg);
        });
      }
      return resp.json();
    });
  }

  function apis(month) {
    return "/ledger/api/records/" + (month ? "?month=" + encodeURIComponent(month) : "");
  }

  /* -------------------------------------------------- 表格渲染 */

  function rowHtml(r) {
    var tr = document.createElement("tr");
    tr.dataset.id = r.id;
    tr.innerHTML =
      '<td class="text-nowrap">' + esc(r.record_date) + "</td>" +
      "<td>" + (r.type === "income" ? '<span class="badge bg-success">收入</span>' : '<span class="badge bg-danger">支出</span>') + "</td>" +
      "<td>" + esc(r.category || "-") + "</td>" +
      '<td class="text-truncate" style="max-width:260px">' + esc(r.note || "-") + "</td>" +
      '<td class="text-end fw-semibold ' + (r.type === "income" ? "text-success" : "text-danger") + '">' + esc(r.amount) + "</td>" +
      '<td class="text-nowrap">' +
      '<button class="btn btn-sm btn-outline-primary btn-edit">编辑</button> ' +
      '<button class="btn btn-sm btn-outline-danger btn-del">删除</button>' +
      "</td>";
    return tr;
  }

  function esc(text) {
    var div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
  }

  function loadRows(url) {
    requestJSON(url).then(function (data) {
      tableBody.innerHTML = "";
      (data.items || []).forEach(function (r) { tableBody.appendChild(rowHtml(r)); });
      if (!(data.items || []).length) {
        tableBody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">本月还没有流水</td></tr>';
      }
      paging = { prev: data.prev_page, next: data.next_page };
      pageEl.textContent = "已显示 " + (data.items || []).length + " 条";
      prevBtn.disabled = !data.has_prev;
      nextBtn.disabled = !data.has_next;
    }).catch(function (err) { alert(err.message); });
  }

  prevBtn.addEventListener("click", function () {
    if (!paging.prev) return;
    loadRows(apis(MONTH) + (MONTH ? "&" : "?") + "page=" + paging.prev);
  });

  nextBtn.addEventListener("click", function () {
    if (!paging.next) return;
    loadRows(apis(MONTH) + (MONTH ? "&" : "?") + "page=" + paging.next);
  });

  /* -------------------------------------------------- 模态框 */

  function openModal(record) {
    modalTitleEl.textContent = record ? "编辑流水" : "新增流水";
    recordIdEl.value = record ? record.id : "";
    recordDateEl.value = record
      ? record.record_date
      : new Date().toISOString().slice(0, 10);
    recordAmountEl.value = record ? record.amount : "";
    recordNoteEl.value = record ? (record.note || "") : "";
    if (record) {
      var catId = String(record.category_id);
      Array.prototype.forEach.call(recordCatEl.options, function (opt) {
        if (opt.value === catId) recordCatEl.value = catId;
      });
    } else {
      recordCatEl.value = recordCatEl.options.length ? recordCatEl.options[0].value : "";
    }
    recordErrorEl.classList.add("d-none");
    modal.show();
  }

  addBtn.addEventListener("click", function () { openModal(null); });

  /* 事件代理：编辑/删除按钮 */
  tableBody.addEventListener("click", function (event) {
    var target = event.target.closest("button");
    if (!target) return;
    var tr = target.closest("tr[data-id]");
    var id = tr ? tr.dataset.id : null;
    if (!id) return;

    if (target.classList.contains("btn-edit")) {
      requestJSON("/ledger/api/records/" + id + "/").then(function (data) {
        openModal(data.record);
      }).catch(function (err) { alert(err.message); });
    } else if (target.classList.contains("btn-del")) {
      if (!confirm("确定删除这笔流水？")) return;
      requestJSON("/ledger/api/records/" + id + "/", { method: "DELETE" }).then(function () {
        location.reload();
      }).catch(function (err) { alert(err.message); });
    }
  });

  recordForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var id = recordIdEl.value;
    var payload = {
      category: recordCatEl.value,
      amount: recordAmountEl.value,
      note: recordNoteEl.value.trim(),
      record_date: recordDateEl.value
    };
    var promise = id
      ? requestJSON("/ledger/api/records/" + id + "/", { method: "PUT", json: payload })
      : requestJSON("/ledger/api/records/", { method: "POST", json: payload });
    promise.then(function () {
      modal.hide();
      location.reload(); // 汇总卡片由服务端渲染
    }).catch(function (err) {
      recordErrorEl.textContent = err.message;
      recordErrorEl.classList.remove("d-none");
    });
  });

  /* 首次进入不停留在 JS 分页：初始行由服务端渲染；翻页按钮才走 API */
})();
