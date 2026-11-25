/* GLM 问答界面：会话管理 + 消息流 + SSE 流式输出 */
(function () {
  "use strict";

  var shell = document.getElementById("chat-shell");
  if (!shell) return;

  var convListEl = document.getElementById("conv-list");
  var newConvBtn = document.getElementById("new-conv");
  var navToggle = document.getElementById("chat-nav-toggle");
  var messagesEl = document.getElementById("chat-messages");
  var chatForm = document.getElementById("chat-form");
  var chatInput = document.getElementById("chat-input");
  var sendBtn = document.getElementById("chat-send");
  var modelSelect = document.getElementById("chat-model");
  var thinkingSelect = document.getElementById("chat-thinking");
  var shotBtn = document.getElementById("chat-shot");
  var fileInput = document.getElementById("chat-file");
  var previewEl = document.getElementById("chat-image-preview");
  var thumbEl = document.getElementById("chat-image-thumb");
  var previewStatus = document.getElementById("chat-image-status");
  var imageCancelBtn = document.getElementById("chat-image-cancel");
  var cropEl = document.getElementById("chat-crop");
  var cropStage = document.getElementById("chat-crop-stage");
  var cropImg = document.getElementById("chat-crop-img");
  var cropSel = document.getElementById("chat-crop-sel");
  var cropOkBtn = document.getElementById("chat-crop-ok");
  var cropAllBtn = document.getElementById("chat-crop-all");
  var cropCancelBtn = document.getElementById("chat-crop-cancel");

  var state = { currentId: null, streaming: false, pendingImage: null };

  /* 模型 / 思考深度：localStorage 记住上次选择（仅当仍在白名单内才恢复） */
  function restorePrefs() {
    try {
      var savedModel = localStorage.getItem("chat.model");
      var savedThinking = localStorage.getItem("chat.thinking");
      if (modelSelect && savedModel) {
        for (var i = 0; i < modelSelect.options.length; i++) {
          if (modelSelect.options[i].value === savedModel) {
            modelSelect.value = savedModel;
            break;
          }
        }
      }
      if (thinkingSelect && savedThinking) {
        for (var j = 0; j < thinkingSelect.options.length; j++) {
          if (thinkingSelect.options[j].value === savedThinking) {
            thinkingSelect.value = savedThinking;
            break;
          }
        }
      }
      if (modelSelect) modelSelect.addEventListener("change", function () {
        localStorage.setItem("chat.model", modelSelect.value);
      });
      if (thinkingSelect) thinkingSelect.addEventListener("change", function () {
        localStorage.setItem("chat.thinking", thinkingSelect.value);
      });
    } catch (e) { /* localStorage 不可用则忽略 */ }
  }

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
          throw new Error(data.error || ("请求失败（" + resp.status + "）"));
        });
      }
      return resp.json();
    });
  }

  /* -------------------------------------------------- 会话列表 */

  function escText(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div;
  }

  function convItem(c) {
    var el = document.createElement("div");
    el.className = "conv-item";
    el.dataset.id = c.id;
    el.appendChild(escText(c.title));

    var delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "conv-del";
    delBtn.innerHTML = "&times;";
    delBtn.title = "删除会话";
    delBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      if (!confirm("删除会话《" + c.title + "》？消息一并删除。")) return;
      requestJSON("/chat/api/conversations/" + c.id + "/delete/", { method: "DELETE" }).then(function () {
        if (String(state.currentId) === String(c.id)) {
          state.currentId = null;
          messagesEl.innerHTML = "";
        }
        el.remove();
      }).catch(function (err) { alert(err.message); });
    });
    el.appendChild(delBtn);

    el.addEventListener("click", function () { switchConversation(c.id); });
    return el;
  }

  function refreshConvList() {
    return requestJSON("/chat/api/conversations/").then(function (data) {
      convListEl.innerHTML = "";
      (data.items || []).forEach(function (c) { convListEl.appendChild(convItem(c)); });
      highlightConv(state.currentId);
      if (document.body.classList.contains("chat-nav")) document.body.classList.remove("chat-nav");
    });
  }

  function highlightConv(id) {
    Array.prototype.forEach.call(convListEl.children, function (el) {
      el.classList.toggle("active", String(el.dataset.id) === String(id));
    });
  }

  newConvBtn.addEventListener("click", function () {
    requestJSON("/chat/api/conversations/create/", { method: "POST" }).then(function (data) {
      return refreshConvList().then(function () {
        switchConversation(data.conversation.id);
      });
    }).catch(function (err) { alert(err.message); });
  });

  navToggle.addEventListener("click", function () {
    document.body.classList.toggle("chat-nav");
  });

  /* -------------------------------------------------- 消息渲染 */

  function openLightbox(src) {
    var ov = document.createElement("div");
    ov.className = "chat-lightbox";
    var img = document.createElement("img");
    img.src = src;
    ov.appendChild(img);
    ov.addEventListener("click", function () { document.body.removeChild(ov); });
    document.body.appendChild(ov);
  }

  function messageBubble(role, content, useMarkdown, image) {
    var div = document.createElement("div");
    div.className = "chat-msg " + role;
    if (image) {
      var img = document.createElement("img");
      img.src = image;
      img.className = "chat-msg-img";
      img.alt = "附图";
      img.addEventListener("click", function () { openLightbox(image); });
      div.appendChild(img);
    }
    if (content) {
      if (role === "assistant" && useMarkdown && window.marked) {
        var md = document.createElement("div");
        md.innerHTML = window.marked.parse(content);
        div.appendChild(md);
      } else {
        var text = document.createElement("div");
        text.textContent = content;
        div.appendChild(text);
      }
    }
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function switchConversation(id) {
    state.currentId = id;
    highlightConv(id);
    document.body.classList.remove("chat-nav");
    return requestJSON("/chat/api/conversations/" + id + "/messages/").then(function (data) {
      messagesEl.innerHTML = "";
      (data.items || []).forEach(function (m) {
        messageBubble(m.role, m.content, true, m.image);
      });
      if (!(data.items || []).length) {
        var tip = document.createElement("p");
        tip.className = "text-muted small m-auto";
        tip.textContent = "开始你的第一次提问吧～";
        messagesEl.appendChild(tip);
      }
    }).catch(function (err) { console.error(err); });
  }

  /* -------------------------------------------------- 截图 / 图片上传 */

  /* 前端 canvas 压缩：最长边 1568px、JPEG 质量 0.9。
     截图多为文字，压缩后通常 100~400KB，省流量也省 VPS 内存。 */
  function downscaleBlob(blob) {
    return new Promise(function (resolve) {
      var url = URL.createObjectURL(blob);
      var img = new Image();
      img.onload = function () {
        URL.revokeObjectURL(url);
        var MAX = 1568;
        var w = img.width, h = img.height;
        var scale = Math.min(1, MAX / Math.max(w, h));
        w = Math.max(1, Math.round(w * scale));
        h = Math.max(1, Math.round(h * scale));
        var canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        canvas.getContext("2d").drawImage(img, 0, 0, w, h);
        if (canvas.toBlob) {
          canvas.toBlob(function (out) { resolve(out || blob); }, "image/jpeg", 0.9);
        } else {
          resolve(blob);
        }
      };
      img.onerror = function () { URL.revokeObjectURL(url); resolve(blob); };
      img.src = url;
    });
  }

  function setPreview(url) {
    state.pendingImage = url;
    thumbEl.src = url;
    previewEl.hidden = false;
  }

  function clearPendingImage(cancelUpload) {
    var url = state.pendingImage;
    state.pendingImage = null;
    previewEl.hidden = true;
    thumbEl.removeAttribute("src");
    fileInput.value = "";
    if (url && cancelUpload) {
      requestJSON("/chat/api/image/delete/", { method: "DELETE", json: { url: url } })
        .catch(function () { /* 已发送/已不存在的图片忽略 */ });
    }
  }

  function uploadImageBlob(blob) {
    if (!blob) return;
    if (blob.type && blob.type.indexOf("image/") !== 0) {
      alert("只能发送图片文件");
      return;
    }
    if (blob.size > 10 * 1024 * 1024) {
      alert("图片超过 10MB，不能发送");
      return;
    }
    shotBtn.disabled = true;
    previewEl.hidden = false;
    thumbEl.removeAttribute("src");
    previewStatus.textContent = "图片上传中…";

    downscaleBlob(blob).then(function (small) {
      var fd = new FormData();
      fd.append("file", small, "screenshot.jpg");
      return fetch("/chat/api/image/upload/", {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
        body: fd
      }).then(function (resp) {
        return resp.json().then(function (data) {
          if (!resp.ok) throw new Error(data.error || "上传失败");
          return data;
        });
      });
    }).then(function (data) {
      /* 连续截图时，替换掉旧的待发图（避免服务器上留孤儿文件） */
      if (state.pendingImage && state.pendingImage !== data.url) clearPendingImage(true);
      setPreview(data.url);
      previewStatus.textContent = "截图已就绪，可继续输入文字，点\u201c发送\u201d一起发出去";
    }).catch(function (err) {
      previewEl.hidden = true;
      alert(err.message || "上传失败");
    }).finally(function () {
      shotBtn.disabled = false;
    });
  }

  /* 桌面：浏览器截屏（用户授权后抓一帧）；手机/不支持：退化为相册选图 */
  function captureScreen() {
    var gdm = navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia;
    if (!gdm) { fileInput.click(); return; }
    navigator.mediaDevices.getDisplayMedia({ video: true, audio: false }).then(function (stream) {
      var video = document.createElement("video");
      video.srcObject = stream;
      video.muted = true;
      return new Promise(function (resolve) {
        video.onloadedmetadata = function () { resolve(); };
      }).then(function () {
        video.play();
        return new Promise(function (resolve) { setTimeout(resolve, 300); });
      }).then(function () {
        var canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(video, 0, 0);
        stream.getTracks().forEach(function (t) { t.stop(); });
        return new Promise(function (resolve) {
          canvas.toBlob(resolve, "image/png");
        });
      }).then(function (blob) {
        if (blob) openCrop(blob);
      });
    }).catch(function (err) {
      /* 用户在浏览器弹窗点了取消 / 授权失败：不再骚扰，仅提示 */
      if (err && err.name === "NotAllowedError") return;
      fileInput.click();
    });
  }

  if (shotBtn) {
    shotBtn.addEventListener("click", function () {
      if (state.streaming) return;
      captureScreen();
    });
  }
  if (fileInput) {
    fileInput.addEventListener("change", function () {
      var f = fileInput.files && fileInput.files[0];
      if (f) openCrop(f);
    });
  }
  if (imageCancelBtn) {
    imageCancelBtn.addEventListener("click", function () { clearPendingImage(true); });
  }

  /* Ctrl+V 粘贴截图（与博客编辑器同款体验） */
  chatInput.addEventListener("paste", function (event) {
    var items = (event.clipboardData && event.clipboardData.items) || [];
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      if (item.kind === "file" && item.type.indexOf("image/") === 0) {
        event.preventDefault();
        var blob = item.getAsFile();
        if (blob) openCrop(blob);
        return;
      }
    }
  });

  /* -------------------------------------------------- 框选裁剪浮层 */

  var crop = { blob: null, url: null, dragging: false, sx: 0, sy: 0, rect: null };

  function openCrop(blob) {
    if (!blob) return;
    if (blob.type && blob.type.indexOf("image/") !== 0) {
      alert("只能发送图片文件");
      return;
    }
    if (blob.size > 10 * 1024 * 1024) {
      alert("图片超过 10MB，不能发送");
      return;
    }
    crop.blob = blob;
    crop.rect = null;
    crop.url = URL.createObjectURL(blob);
    cropImg.src = crop.url;
    cropSel.hidden = true;
    cropOkBtn.disabled = true;
    document.getElementById("chat-crop-hint").textContent =
      "按住拖出要发送的区域（拖错了重新拖即可）；不想裁剪就点\u201c全部\u201d";
    cropEl.hidden = false;
  }

  function closeCrop() {
    cropEl.hidden = true;
    if (crop.url) URL.revokeObjectURL(crop.url);
    cropImg.removeAttribute("src");
    crop.blob = null;
    crop.url = null;
    crop.rect = null;
    fileInput.value = "";
  }

  /* 在缩放后的舞台坐标系里取指针位置 */
  function stagePoint(event) {
    var r = cropStage.getBoundingClientRect();
    return {
      x: Math.min(Math.max(event.clientX - r.left, 0), r.width),
      y: Math.min(Math.max(event.clientY - r.top, 0), r.height),
    };
  }

  function drawSel() {
    if (!crop.rect) { cropSel.hidden = true; return; }
    cropSel.hidden = false;
    cropSel.style.left = crop.rect.x + "px";
    cropSel.style.top = crop.rect.y + "px";
    cropSel.style.width = crop.rect.w + "px";
    cropSel.style.height = crop.rect.h + "px";
  }

  if (cropStage) {
    cropStage.addEventListener("pointerdown", function (event) {
      if (cropEl.hidden) return;
      event.preventDefault();
      var p = stagePoint(event);
      crop.dragging = true;
      crop.sx = p.x;
      crop.sy = p.y;
      crop.rect = { x: p.x, y: p.y, w: 0, h: 0 };
      drawSel();
      cropOkBtn.disabled = true;
      cropStage.setPointerCapture(event.pointerId);
    });
    cropStage.addEventListener("pointermove", function (event) {
      if (!crop.dragging) return;
      var p = stagePoint(event);
      crop.rect = {
        x: Math.min(crop.sx, p.x),
        y: Math.min(crop.sy, p.y),
        w: Math.abs(p.x - crop.sx),
        h: Math.abs(p.y - crop.sy),
      };
      drawSel();
    });
    cropStage.addEventListener("pointerup", function () {
      if (!crop.dragging) return;
      crop.dragging = false;
      /* 拖得太小视为误触，清除选区 */
      if (!crop.rect || crop.rect.w < 12 || crop.rect.h < 12) {
        crop.rect = null;
        drawSel();
        cropOkBtn.disabled = true;
      } else {
        cropOkBtn.disabled = false;
      }
    });
  }

  if (cropOkBtn) {
    cropOkBtn.addEventListener("click", function () {
      if (!crop.blob || !crop.rect) return;
      var scale = cropImg.naturalWidth / cropImg.clientWidth;
      var sx = Math.round(crop.rect.x * scale);
      var sy = Math.round(crop.rect.y * scale);
      var sw = Math.max(1, Math.round(crop.rect.w * scale));
      var sh = Math.max(1, Math.round(crop.rect.h * scale));
      var canvas = document.createElement("canvas");
      canvas.width = sw;
      canvas.height = sh;
      canvas.getContext("2d").drawImage(cropImg, sx, sy, sw, sh, 0, 0, sw, sh);
      var srcType = crop.blob.type || "image/jpeg";
      var outType = srcType === "image/png" ? "image/png" : "image/jpeg";
      canvas.toBlob(function (out) {
        closeCrop();
        uploadImageBlob(out || crop.blob);
      }, outType, outType === "image/jpeg" ? 0.92 : undefined);
    });
  }
  if (cropAllBtn) {
    /* 不裁剪：整张图直接走上传 */
    cropAllBtn.addEventListener("click", function () {
      var blob = crop.blob;
      closeCrop();
      uploadImageBlob(blob);
    });
  }
  if (cropCancelBtn) {
    cropCancelBtn.addEventListener("click", closeCrop);
  }
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !cropEl.hidden) closeCrop();
  });

  /* -------------------------------------------------- SSE 发送 */

  function appendStreamDelta(el, text, buffered) {
    /* 流式阶段按纯文本增量展示，结束后再整段 Markdown 渲染 */
    el.textContent += text;
    buffered.push(text);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return buffered;
  }

  function sendStream(conversationId, content, imageUrl) {
    state.streaming = true;
    sendBtn.disabled = true;
    shotBtn.disabled = true;

    var userBubble = messageBubble("user", content, false, imageUrl);
    userBubble.classList.add("user");

    var assistantBubble = document.createElement("div");
    assistantBubble.className = "chat-msg assistant typing";
    assistantBubble.textContent = "";
    messagesEl.appendChild(assistantBubble);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    var thinkingEl = null;   /* <details class="chat-thinking"> 思考块 */
    var thinkingPre = null;
    var thinkingText = "";

    function appendThinking(text) {
      if (!thinkingEl) {
        thinkingEl = document.createElement("details");
        thinkingEl.className = "chat-thinking";
        thinkingEl.open = true;
        var sum = document.createElement("summary");
        sum.textContent = "思考中…";
        thinkingEl.appendChild(sum);
        thinkingPre = document.createElement("div");
        thinkingPre.className = "thinking-text";
        thinkingEl.appendChild(thinkingPre);
        messagesEl.insertBefore(thinkingEl, assistantBubble);
      }
      thinkingText += text;
      thinkingPre.textContent = thinkingText;
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function collapseThinking() {
      if (thinkingEl && thinkingEl.open) {
        thinkingEl.open = false;
        thinkingEl.querySelector("summary").textContent = "已深度思考 · 点击展开";
      }
    }

    var buffered = [];
    var firstDelta = true;

    fetch("/chat/api/conversations/" + conversationId + "/messages/stream/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken")
      },
      body: JSON.stringify({
        content: content,
        image: imageUrl || "",
        model: modelSelect ? modelSelect.value : "",
        thinking: thinkingSelect ? thinkingSelect.value : ""
      })
    }).then(function (resp) {
      if (!resp.ok) {
        return resp.json().catch(function () { return {}; }).then(function (data) {
          throw new Error(data.error || ("请求失败（" + resp.status + "）"));
        });
      }
      var reader = resp.body.getReader();
      var decoder = new TextDecoder("utf-8");
      var buffer = "";

      function pump() {
        return reader.read().then(function (result) {
          if (result.done) return null;
          buffer += decoder.decode(result.value, { stream: true });

          /* SSE 事件以空行分隔 */
          var idx;
          while ((idx = buffer.indexOf("\n\n")) !== -1) {
            var rawEvent = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            rawEvent.split("\n").forEach(function (line) {
              if (!line.startsWith("data:")) return;
              var payload = line.slice(5).trim();
              if (!payload) return;
              try {
                var data = JSON.parse(payload);
              } catch (e) {
                return;
              }
              if (data.thinking) {
                appendThinking(data.thinking);
              }
              if (data.delta) {
                if (firstDelta) {
                  assistantBubble.classList.remove("typing");
                  firstDelta = false;
                }
                collapseThinking();
                buffered = appendStreamDelta(assistantBubble, data.delta, buffered);
              }
              if (data.error) {
                collapseThinking();
                assistantBubble.textContent = "出错了：" + data.error;
              }
              if (data.done) {
                collapseThinking();
                /* 结束：整段 Markdown 渲染 */
                var full = buffered.join("");
                if (window.marked && full) {
                  assistantBubble.innerHTML = window.marked.parse(full);
                }
              }
            });
          }
          return pump();
        });
      }

      return pump();
    }).catch(function (err) {
      assistantBubble.textContent = "出错了：" + err.message;
    }).finally(function () {
      state.streaming = false;
      sendBtn.disabled = false;
      shotBtn.disabled = false;
      assistantBubble.classList.remove("typing");
      /* 首条消息会自动生成标题：刷新左侧列表 */
      refreshConvList();
    });
  }

  chatForm.addEventListener("submit", function (event) {
    event.preventDefault();
    if (state.streaming) return;
    var text = chatInput.value.trim();
    var imageUrl = state.pendingImage || "";
    if (!text && !imageUrl) return;   /* 纯图消息也允许：文字可留空 */
    if (!state.currentId) {
      /* 没有当前会话时先自动新建一个 */
      requestJSON("/chat/api/conversations/create/", { method: "POST" }).then(function (data) {
        return refreshConvList().then(function () {
          state.currentId = data.conversation.id;
          highlightConv(state.currentId);
          chatInput.value = "";
          clearPendingImage(false);   /* 已随消息发送，文件保留 */
          sendStream(state.currentId, text, imageUrl);
        });
      }).catch(function (err) { alert(err.message); });
      return;
    }
    chatInput.value = "";
    clearPendingImage(false);       /* 已随消息发送，文件保留 */
    sendStream(state.currentId, text, imageUrl);
  });

  chatInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      chatForm.requestSubmit ? chatForm.requestSubmit() : chatForm.dispatchEvent(new Event("submit"));
    }
  });

  /* -------------------------------------------------- 初始化 */

  function init() {
    restorePrefs();
    /* 用 fetch 重渲染列表，保证每项都带删除按钮 */
    refreshConvList();
    var first = convListEl.querySelector(".conv-item");
    if (first) switchConversation(first.dataset.id);
  }

  init();
})();
