// Dashboard client. No build step: plain ES2020 talking to /api.
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));
// Only allow https image URLs from the API into src attributes.
const safeUrl = (u) => (typeof u === "string" && /^https:\/\//i.test(u) ? esc(u) : "");

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = data.detail || `Request failed (${res.status})`;
    if (Array.isArray(msg)) {
      msg = msg.map((e) => `${e.loc?.slice(-1)[0] ?? "field"}: ${e.msg}`).join("; ");
    }
    throw new Error(msg);
  }
  return data;
}

function toast(message, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type === "error" ? "error" : ""}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), type === "error" ? 6000 : 3000);
}

function timeAgo(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

const splitKeywords = (raw) => {
  const seen = new Set();
  return raw.split(",").map((k) => k.trim()).filter((k) => k && !seen.has(k.toLowerCase()) && seen.add(k.toLowerCase()));
};

/* ------------------------------------------------------------ campaigns */

function initCampaigns() {
  const list = $("#campaign-list");
  const dialog = $("#campaign-dialog");
  const form = $("#campaign-form");
  const f = form.elements;
  const preview = $("#post-preview");
  const recent = $("#recent-posts");
  const formError = $("#form-error");
  let campaigns = [];
  let lastPreviewId = null;

  const statusBadge = (s) => {
    if (s === "sent") return '<span class="badge on">sent</span>';
    if (s === "failed") return '<span class="badge fail">failed</span>';
    return `<span class="badge off">${esc(s)}</span>`;
  };

  function renderCampaign(c) {
    const thumb = safeUrl(c.post_thumbnail_url);
    return `
      <article class="campaign ${c.is_active ? "" : "inactive"}" data-id="${c.id}">
        <div class="thumb">${thumb ? `<img src="${thumb}" alt="" loading="lazy" style="width:100%;height:100%;object-fit:cover;border-radius:8px" onerror="this.remove()">` : "No preview"}</div>
        <div class="campaign-body">
          <div class="campaign-title">
            <h3>${esc(c.name || (c.post_caption || "").slice(0, 60) || "Untitled campaign")}</h3>
            <span class="badge ${c.is_active ? "on" : "off"}">${c.is_active ? "Active" : "Inactive"}</span>
          </div>
          <div class="post-id">Post ${esc(c.post_id)}${c.post_permalink ? ` · <a href="${safeUrl(c.post_permalink)}" target="_blank" rel="noopener">view</a>` : ""}</div>
          <div class="chips">${c.keywords.map((k) => `<span class="chip">${esc(k)}</span>`).join("")}</div>
          <p class="msg"><b>Reply</b><span>${esc(c.comment_reply)}</span></p>
          <p class="msg"><b>DM</b><span>${esc(c.dm_message)}</span></p>
        </div>
        <div class="campaign-actions">
          <label class="switch-field" title="Toggle active">
            <input type="checkbox" data-action="toggle" ${c.is_active ? "checked" : ""}>
            <span class="switch"></span>
          </label>
          <div class="row">
            <button class="btn ghost small" data-action="edit">Edit</button>
            <button class="btn danger small" data-action="delete">Delete</button>
          </div>
        </div>
      </article>`;
  }

  async function loadCampaigns() {
    try {
      campaigns = await api("/campaigns");
    } catch (e) {
      list.innerHTML = `<div class="empty">Couldn't load campaigns: ${esc(e.message)}</div>`;
      return;
    }
    list.innerHTML = campaigns.length
      ? campaigns.map(renderCampaign).join("")
      : `<div class="empty muted">No campaigns yet. Create one to start turning comments into DMs.</div>`;
  }

  async function loadActivity() {
    const body = $("#activity-body");
    try {
      const rows = await api("/activity?limit=25");
      body.innerHTML = rows.length ? rows.map((r) => `
        <tr title="${esc(r.error || "")}">
          <td>${esc(timeAgo(r.processed_at))}</td>
          <td>${r.commenter_username ? "@" + esc(r.commenter_username) : "—"}</td>
          <td class="comment">${esc(r.comment_text)}</td>
          <td><span class="chip">${esc(r.matched_keyword)}</span></td>
          <td>${statusBadge(r.reply_status)}</td>
          <td>${statusBadge(r.dm_status)}</td>
        </tr>`).join("") : `<tr><td colspan="6" class="muted">No matching comments yet.</td></tr>`;
    } catch (e) {
      body.innerHTML = `<tr><td colspan="6" class="muted">${esc(e.message)}</td></tr>`;
    }
  }

  async function checkSetup() {
    try {
      const cfg = await api("/config");
      $("#setup-warning").hidden = cfg.access_token_set && !!cfg.instagram_account_id;
    } catch { /* non-fatal */ }
  }

  function renderChips() {
    $("#keyword-chips").innerHTML = splitKeywords(f.keywords.value).map((k) => `<span class="chip">${esc(k)}</span>`).join("");
  }

  function updateCount() {
    $('[data-count="dm_message"]').textContent = f.dm_message.value.length;
  }

  async function loadPreview(force = false) {
    const id = f.post_id.value.trim();
    if (!id) { preview.hidden = true; lastPreviewId = null; return; }
    if (id === lastPreviewId && !force) return;
    lastPreviewId = id;
    preview.hidden = false;
    preview.className = "post-preview";
    preview.innerHTML = `<span class="muted">Loading post preview…</span>`;
    try {
      const p = await api(`/posts/${encodeURIComponent(id)}`);
      if (f.post_id.value.trim() !== id) return;
      const img = safeUrl(p.preview_url);
      preview.innerHTML = `
        ${img ? `<img src="${img}" alt="">` : ""}
        <div>
          <div class="post-id">${esc(p.media_type || "")} · ${esc(p.id)}</div>
          <p>${esc(p.caption || "(no caption)")}</p>
        </div>`;
    } catch (e) {
      if (f.post_id.value.trim() !== id) return;
      preview.className = "post-preview error";
      preview.textContent = `Couldn't load post: ${e.message}`;
    }
  }

  async function browsePosts() {
    if (!recent.hidden) { recent.hidden = true; return; }
    recent.hidden = false;
    recent.innerHTML = `<span class="muted">Loading recent posts…</span>`;
    try {
      const posts = await api("/posts/recent?limit=24");
      recent.innerHTML = posts.length ? posts.map((p) => `
        <button type="button" data-post="${esc(p.id)}" title="${esc((p.caption || "").slice(0, 120))}">
          ${safeUrl(p.preview_url) ? `<img src="${safeUrl(p.preview_url)}" alt="" loading="lazy">` : esc(p.id)}
        </button>`).join("") : `<span class="muted">No posts found.</span>`;
    } catch (e) {
      recent.innerHTML = `<span class="muted">${esc(e.message)}</span>`;
    }
  }

  function openDialog(c = null) {
    form.reset();
    formError.hidden = true;
    recent.hidden = true;
    preview.hidden = true;
    lastPreviewId = null;
    $("#dialog-title").textContent = c ? "Edit campaign" : "New campaign";
    f.id.value = c?.id ?? "";
    f.name.value = c?.name ?? "";
    f.post_id.value = c?.post_id ?? "";
    f.keywords.value = c ? c.keywords.join(", ") : "";
    f.comment_reply.value = c?.comment_reply ?? "";
    f.dm_message.value = c?.dm_message ?? "";
    f.is_active.checked = c ? c.is_active : true;
    renderChips();
    updateCount();
    dialog.showModal();
    if (c) loadPreview();
    else f.post_id.focus();
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    formError.hidden = true;
    const payload = {
      name: f.name.value.trim() || null,
      post_id: f.post_id.value.trim(),
      keywords: f.keywords.value,
      comment_reply: f.comment_reply.value.trim(),
      dm_message: f.dm_message.value.trim(),
      is_active: f.is_active.checked,
    };
    const missing = [];
    if (!payload.post_id) missing.push("Post ID");
    if (!splitKeywords(payload.keywords).length) missing.push("at least one keyword");
    if (!payload.comment_reply) missing.push("comment reply");
    if (!payload.dm_message) missing.push("DM message");
    if (missing.length) {
      formError.textContent = `Please add ${missing.join(", ")}.`;
      formError.hidden = false;
      return;
    }
    const btn = $("#save-campaign");
    btn.disabled = true;
    try {
      const id = f.id.value;
      await api(id ? `/campaigns/${id}` : "/campaigns", { method: id ? "PUT" : "POST", body: payload });
      dialog.close();
      toast(id ? "Campaign updated" : "Campaign created");
      loadCampaigns();
    } catch (e) {
      formError.textContent = e.message;
      formError.hidden = false;
    } finally {
      btn.disabled = false;
    }
  });

  list.addEventListener("click", async (ev) => {
    const action = ev.target.closest("[data-action]")?.dataset.action;
    const card = ev.target.closest(".campaign");
    if (!action || !card || action === "toggle") return;
    const c = campaigns.find((x) => String(x.id) === card.dataset.id);
    if (action === "edit") openDialog(c);
    if (action === "delete") {
      if (!confirm(`Delete this campaign? Comments on post ${c.post_id} will no longer trigger DMs.`)) return;
      try {
        await api(`/campaigns/${c.id}`, { method: "DELETE" });
        toast("Campaign deleted");
        loadCampaigns();
      } catch (e) { toast(e.message, "error"); }
    }
  });

  list.addEventListener("change", async (ev) => {
    if (ev.target.dataset.action !== "toggle") return;
    const id = ev.target.closest(".campaign").dataset.id;
    try {
      const c = await api(`/campaigns/${id}/toggle`, { method: "POST" });
      toast(c.is_active ? "Campaign activated" : "Campaign paused");
      loadCampaigns();
    } catch (e) {
      ev.target.checked = !ev.target.checked;
      toast(e.message, "error");
    }
  });

  recent.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-post]");
    if (!btn) return;
    f.post_id.value = btn.dataset.post;
    recent.hidden = true;
    loadPreview(true);
  });

  $("#new-campaign").addEventListener("click", () => openDialog());
  $("#browse-posts").addEventListener("click", browsePosts);
  $("#refresh-activity").addEventListener("click", loadActivity);
  $$("[data-close]", dialog).forEach((b) => b.addEventListener("click", () => dialog.close()));
  f.post_id.addEventListener("blur", () => loadPreview());
  f.keywords.addEventListener("input", renderChips);
  f.dm_message.addEventListener("input", updateCount);

  loadCampaigns();
  loadActivity();
  checkSetup();
}

/* ------------------------------------------------------------- settings */

function initSettings() {
  const form = $("#settings-form");
  const f = form.elements;
  const result = $("#connection-result");

  function render(cfg) {
    f.page_id.value = cfg.page_id || "";
    f.instagram_account_id.value = cfg.instagram_account_id || "";
    f.access_token.value = "";
    let status = cfg.access_token_set
      ? `Saved token: ${cfg.access_token_preview} (from ${cfg.access_token_source}). Leave blank to keep it.`
      : "No token saved yet.";
    if (cfg.token_expires_at) status += ` Expires ${new Date(cfg.token_expires_at).toLocaleDateString()}.`;
    $("#token-status").textContent = status;
    $("#refresh-token").hidden = !(cfg.token_refresh_available && cfg.access_token_set);
    $$("#checklist [data-check]").forEach((li) => {
      li.className = cfg[li.dataset.check] ? "ok" : "bad";
    });
  }

  async function load() {
    try { render(await api("/config")); } catch (e) { toast(e.message, "error"); }
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      render(await api("/config", {
        method: "PUT",
        body: {
          access_token: f.access_token.value.trim() || null,
          page_id: f.page_id.value,
          instagram_account_id: f.instagram_account_id.value,
        },
      }));
      toast("Settings saved");
    } catch (e) { toast(e.message, "error"); }
  });

  $("#test-connection").addEventListener("click", async (ev) => {
    ev.target.disabled = true;
    result.hidden = false;
    result.className = "connection-result";
    result.textContent = "Testing…";
    try {
      const { account } = await api("/config/test", { method: "POST" });
      result.className = "connection-result ok";
      result.innerHTML = `Connected as <b>@${esc(account.username)}</b>${account.followers_count != null ? ` · ${esc(account.followers_count)} followers` : ""}`;
    } catch (e) {
      result.className = "connection-result bad";
      result.textContent = e.message;
    } finally {
      ev.target.disabled = false;
    }
  });

  $("#refresh-token").addEventListener("click", async (ev) => {
    ev.target.disabled = true;
    try {
      render(await api("/config/refresh-token", { method: "POST" }));
      toast("Token refreshed");
    } catch (e) { toast(e.message, "error"); }
    finally { ev.target.disabled = false; }
  });

  $("#copy-webhook").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("#webhook-url").value);
      toast("Copied");
    } catch { $("#webhook-url").select(); }
  });

  load();
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "campaigns") initCampaigns();
  if (page === "settings") initSettings();
});
