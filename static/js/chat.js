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

  var state = { currentId: null, streaming: false };

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

  function messageBubble(role, content, useMarkdown) {
    var div = document.createElement("div");
    div.className = "chat-msg " + role;
    if (role === "assistant" && useMarkdown && window.marked && content) {
      div.innerHTML = window.marked.parse(content);
    } else {
      div.textContent = content;
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
        messageBubble(m.role, m.content, true);
      });
      if (!(data.items || []).length) {
        var tip = document.createElement("p");
        tip.className = "text-muted small m-auto";
        tip.textContent = "开始你的第一次提问吧～";
        messagesEl.appendChild(tip);
      }
    }).catch(function (err) { console.error(err); });
  }

  /* -------------------------------------------------- SSE 发送 */

  function appendStreamDelta(el, text, buffered) {
    /* 流式阶段按纯文本增量展示，结束后再整段 Markdown 渲染 */
    el.textContent += text;
    buffered.push(text);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return buffered;
  }

  function sendStream(conversationId, content) {
    state.streaming = true;
    sendBtn.disabled = true;

    var userBubble = messageBubble("user", content, false);
    userBubble.classList.add("user");

    var assistantBubble = document.createElement("div");
    assistantBubble.className = "chat-msg assistant typing";
    assistantBubble.textContent = "";
    messagesEl.appendChild(assistantBubble);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    var buffered = [];
    var firstDelta = true;

    fetch("/chat/api/conversations/" + conversationId + "/messages/stream/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken")
      },
      body: JSON.stringify({ content: content })
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
              if (data.delta) {
                if (firstDelta) {
                  assistantBubble.classList.remove("typing");
                  firstDelta = false;
                }
                buffered = appendStreamDelta(assistantBubble, data.delta, buffered);
              }
              if (data.error) {
                assistantBubble.textContent = "出错了：" + data.error;
              }
              if (data.done) {
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
      assistantBubble.classList.remove("typing");
      /* 首条消息会自动生成标题：刷新左侧列表 */
      refreshConvList();
    });
  }

  chatForm.addEventListener("submit", function (event) {
    event.preventDefault();
    if (state.streaming) return;
    var text = chatInput.value.trim();
    if (!text) return;
    if (!state.currentId) {
      /* 没有当前会话时先自动新建一个 */
      requestJSON("/chat/api/conversations/create/", { method: "POST" }).then(function (data) {
        return refreshConvList().then(function () {
          state.currentId = data.conversation.id;
          highlightConv(state.currentId);
          chatInput.value = "";
          sendStream(state.currentId, text);
        });
      }).catch(function (err) { alert(err.message); });
      return;
    }
    chatInput.value = "";
    sendStream(state.currentId, text);
  });

  chatInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      chatForm.requestSubmit ? chatForm.requestSubmit() : chatForm.dispatchEvent(new Event("submit"));
    }
  });

  /* -------------------------------------------------- 初始化 */

  function init() {
    /* 用 fetch 重渲染列表，保证每项都带删除按钮 */
    refreshConvList();
    var first = convListEl.querySelector(".conv-item");
    if (first) switchConversation(first.dataset.id);
  }

  init();
})();
