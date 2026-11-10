/* 文章编辑器：粘贴图片自动上传并插入 Markdown；右侧 marked.js 实时预览 */
(function () {
  "use strict";

  var textarea = document.getElementById("md-input");
  var previewEl = document.getElementById("md-preview");
  if (!textarea) return;

  function getCookie(name) {
    var m = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[2]) : "";
  }

  function renderPreview() {
    if (!previewEl) return;
    if (!window.marked) return;
    try {
      previewEl.innerHTML = window.marked.parse(textarea.value || "");
    } catch (e) {
      previewEl.textContent = textarea.value;
    }
  }

  /* 在光标处插入文本（替换选区） */
  function insertAtCursor(text) {
    var start = textarea.selectionStart || 0;
    var end = textarea.selectionEnd || 0;
    textarea.setRangeText(text, start, end, "end");
    var caret = start + text.length;
    textarea.focus();
    textarea.setSelectionRange(caret, caret);
    renderPreview();
  }

  function statusEl() {
    var el = document.getElementById("upload-status");
    if (!el) {
      el = document.createElement("div");
      el.id = "upload-status";
      textarea.insertAdjacentElement("afterend", el);
    }
    return el;
  }

  function setStatus(text, isError) {
    var el = statusEl();
    el.className = "form-text " + (isError ? "text-danger" : "text-success");
    el.textContent = text;
  }

  function uploadBlob(blob) {
    // 剪贴板的 File 对象一般叫 image.png；拖拽文件有真实文件名
    var name = blob.name || ("clipboard-" + Date.now() + ".png");
    var fd = new FormData();
    fd.append("file", blob, name);

    setStatus("图片上传中…", false);
    return fetch("/blog/api/upload/", {
      method: "POST",
      headers: { "X-CSRFToken": getCookie("csrftoken") },
      body: fd
    }).then(function (resp) {
      return resp.json().then(function (data) {
        if (!resp.ok) throw new Error(data.error || "上传失败");
        return data;
      });
    }).then(function (data) {
      insertAtCursor("![](" + data.url + ")\n");
      setStatus("图片已插入 ✔", false);
    }).catch(function (err) {
      setStatus(err.message, true);
    });
  }

  /* 粘贴：clipboardData.items 里找 image */
  textarea.addEventListener("paste", function (event) {
    var items = (event.clipboardData && event.clipboardData.items) || [];
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      if (item.kind === "file" && item.type.indexOf("image/") === 0) {
        event.preventDefault();
        var blob = item.getAsFile();
        if (blob && blob.size <= 10 * 1024 * 1024) {
          uploadBlob(blob);
        } else {
          setStatus("图片超过 10MB，不能上传", true);
        }
        return; // 命中图片后不再让普通粘贴继续
      }
    }
  });

  /* 拖拽图片到编辑器也支持 */
  textarea.addEventListener("dragover", function (event) { event.preventDefault(); });
  textarea.addEventListener("drop", function (event) {
    var files = (event.dataTransfer && event.dataTransfer.files) || [];
    for (var i = 0; i < files.length; i++) {
      if (files[i].type.indexOf("image/") === 0) {
        event.preventDefault();
        uploadBlob(files[i]);
        return;
      }
    }
  });

  textarea.addEventListener("input", renderPreview);

  if (window.marked) {
    window.marked.setOptions({ gfm: true, breaks: false });
  }

  renderPreview();
})();
