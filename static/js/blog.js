/* 博客前台交互：中栏列表/过滤/加载更多 + 右栏详情 + 点赞 + 评论 + pushState */
(function () {
  "use strict";

  var shell = document.getElementById("blog-shell");
  if (!shell) return;

  var selectedInitial = shell.dataset.selectedPost || "";
  var mqMobile = window.matchMedia("(max-width: 767.98px)");

  var postListEl = document.getElementById("post-list");
  var loadMoreBtn = document.getElementById("load-more");
  var nowhereEl = document.getElementById("list-nowhere");
  var searchInput = document.getElementById("post-search");
  var catListEl = document.getElementById("cat-list");

  var detailBody = document.getElementById("detail-body");
  var detailEmpty = document.getElementById("detail-empty");
  var pdTitle = document.getElementById("pd-title");
  var pdCategory = document.getElementById("pd-category");
  var pdDate = document.getElementById("pd-date");
  var pdViews = document.getElementById("pd-views");
  var pdLikes = document.getElementById("pd-likes");
  var pdLikeBtn = document.getElementById("pd-like");
  var pdContent = document.getElementById("pd-content");
  var commentListEl = document.getElementById("comment-list");
  var commentForm = document.getElementById("comment-form");

  var state = { cat: "all", q: "", page: 1, hasMore: false, currentId: null };

  /* localStorage 点赞防重复 */
  var likedSet = (function () {
    try { return new Set(JSON.parse(localStorage.getItem("blog_liked_ids") || "[]")); } catch (e) { return new Set(); }
  })();

  function persistLiked() {
    try { localStorage.setItem("blog_liked_ids", JSON.stringify(Array.from(likedSet))); } catch (e) { /* 隐身模式等忽略 */ }
  }

  function debounce(fn, wait) {
    var t = null;
    return function () {
      var args = arguments, self = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(self, args); }, wait);
    };
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

  /* -------------------------------------------------- 中栏列表 */

  function postItem(item) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "post-item";
    btn.dataset.id = item.id;

    var titleEl = document.createElement("span");
    titleEl.className = "post-title";
    titleEl.textContent = item.title;
    btn.appendChild(titleEl);

    var meta = document.createElement("span");
    meta.className = "post-date";
    meta.textContent = item.date;
    if (item.category && state.cat === "all") {
      var catEl = document.createElement("span");
      catEl.className = "post-cat";
      catEl.textContent = item.category;
      meta.appendChild(catEl);
    }
    btn.appendChild(meta);

    btn.addEventListener("click", function () { openPost(item.id, true); });
    return btn;
  }

  function refreshHighlight() {
    Array.prototype.forEach.call(postListEl.children, function (el) {
      el.classList.toggle("active", String(el.dataset.id) === String(state.currentId));
    });
  }

  function loadPosts(reset) {
    if (reset) {
      state.page = 1;
      postListEl.innerHTML = "";
    }
    var params = new URLSearchParams({ category: state.cat, q: state.q, page: String(state.page) });
    return requestJSON("/blog/api/posts/?" + params.toString()).then(function (data) {
      (data.items || []).forEach(function (item) { postListEl.appendChild(postItem(item)); });
      state.hasMore = !!data.has_next;
      loadMoreBtn.classList.toggle("d-none", !state.hasMore);
      nowhereEl.classList.toggle("d-none", reset ? (data.items || []).length > 0 : true);
      refreshHighlight();
    }).catch(function (err) {
      console.error(err);
    });
  }

  catListEl.addEventListener("click", function (event) {
    var btn = event.target.closest(".cat-item");
    if (!btn) return;
    catListEl.querySelectorAll(".cat-item").forEach(function (el) { el.classList.remove("active"); });
    btn.classList.add("active");
    state.cat = btn.dataset.cat;
    loadPosts(true);
  });

  searchInput.addEventListener("input", debounce(function () {
    state.q = searchInput.value.trim();
    loadPosts(true);
  }, 300));

  loadMoreBtn.addEventListener("click", function () {
    state.page = state.page + 1;
    loadPosts(false);
  });

  /* -------------------------------------------------- 右栏详情 */

  function renderDetail(data) {
    detailEmpty.classList.add("d-none");
    detailBody.classList.remove("d-none");

    document.title = data.title + " · 我的小站";
    pdTitle.textContent = data.title;
    pdDate.textContent = data.published_at;
    pdViews.textContent = data.views;
    pdLikes.textContent = data.likes;

    if (data.category) {
      pdCategory.textContent = data.category;
      pdCategory.classList.remove("d-none");
    } else {
      pdCategory.classList.add("d-none");
    }

    var liked = likedSet.has(Number(data.id));
    pdLikeBtn.classList.toggle("btn-danger", liked);
    pdLikeBtn.disabled = false;

    try {
      pdContent.innerHTML = window.marked ? window.marked.parse(data.content_md || "") : "";
    } catch (e) {
      pdContent.textContent = data.content_md || "";
    }
  }

  function openPost(id, push) {
    if (mqMobile.matches) {
      /* 移动端：整页跳转“列表 → 详情” */
      location.href = "/blog/" + id + "/";
      return;
    }
    return requestJSON("/blog/api/posts/" + id + "/").then(function (data) {
      state.currentId = id;
      renderDetail(data);
      if (push) history.pushState({ postId: id }, "", "/blog/" + id + "/");
      refreshHighlight();
      loadComments(id);
      document.getElementById("post-detail").scrollTop = 0;
    }).catch(function (err) {
      console.error(err);
    });
  }

  /* 点赞 */
  pdLikeBtn.addEventListener("click", function () {
    var id = state.currentId;
    if (!id) return;
    if (likedSet.has(Number(id))) return; // 已赞过
    requestJSON("/blog/api/posts/" + id + "/like/", { method: "POST" }).then(function (data) {
      likedSet.add(Number(id));
      persistLiked();
      pdLikes.textContent = data.likes;
      pdLikeBtn.classList.add("btn-danger");
    }).catch(function (err) { alert(err.message); });
  });

  /* -------------------------------------------------- 评论 */

  function commentItem(c) {
    var div = document.createElement("div");
    div.className = "comment-item";
    var head = document.createElement("div");
    head.className = "d-flex justify-content-between";
    var nick = document.createElement("span");
    nick.className = "comment-nick";
    nick.textContent = c.nickname;
    var time = document.createElement("span");
    time.className = "comment-time";
    time.textContent = c.created_at;
    head.appendChild(nick); head.appendChild(time);
    var text = document.createElement("div");
    text.className = "comment-text";
    text.textContent = c.content;
    div.appendChild(head); div.appendChild(text);
    return div;
  }

  function loadComments(postId) {
    return requestJSON("/blog/api/posts/" + postId + "/comments/").then(function (data) {
      commentListEl.innerHTML = "";
      (data.items || []).forEach(function (c) { commentListEl.appendChild(commentItem(c)); });
      if (!(data.items || []).length) {
        var p = document.createElement("p");
        p.className = "text-muted small";
        p.textContent = "还没有评论，来抢沙发～";
        commentListEl.appendChild(p);
      }
    });
  }

  commentForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var id = state.currentId;
    if (!id) return;
    var nicknameEl = document.getElementById("comment-nickname");
    var contentEl = document.getElementById("comment-content");
    var payload = { nickname: nicknameEl.value.trim(), content: contentEl.value.trim() };
    if (!payload.nickname || !payload.content) {
      alert("请填写昵称和评论内容");
      return;
    }
    requestJSON("/blog/api/posts/" + id + "/comments/", { method: "POST", json: payload }).then(function (data) {
      if (commentListEl.querySelector(".text-muted")) commentListEl.innerHTML = "";
      commentListEl.appendChild(commentItem(data.comment));
      nicknameEl.value = "";
      contentEl.value = "";
    }).catch(function (err) { alert(err.message); });
  });

  /* -------------------------------------------------- 浏览器历史 */

  window.addEventListener("popstate", function () {
    var m = location.pathname.match(/^\/blog\/(\d+)\/?$/);
    if (m) {
      openPost(m[1], false);
    } else {
      document.title = "博客 · 我的小站";
      detailBody.classList.add("d-none");
      detailEmpty.classList.remove("d-none");
      state.currentId = null;
      refreshHighlight();
    }
  });

  /* -------------------------------------------------- 初始化 */

  function init() {
    loadPosts(true);
    if (selectedInitial) {
      if (mqMobile.matches) {
        document.body.classList.add("blog-detail");
      }
      openPost(selectedInitial, false);
    }
  }

  init();
})();
