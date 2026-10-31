// Collapsible IPAM tree: lazy child loading, expand/collapse all, remembered state, keyboard navigation.
(() => {
  "use strict";

  const store = {
    get(key, fallback) {
      try {
        const v = localStorage.getItem(key);
        return v === null ? fallback : JSON.parse(v);
      } catch {
        return fallback;
      }
    },
    set(key, value) {
      try {
        localStorage.setItem(key, JSON.stringify(value));
      } catch {
        /* storage unavailable: the tree still works, it just forgets its state */
      }
    },
  };

  const FREE_KEY = "ipam-tree:free";
  const FREE_COOKIE = "ipam_tree_free"; // conf.FREE_COOKIE: lets the server render the first rows to match
  const MAX_SAVED_KEYS = 200; // keeps the restore URL short; ancestors come first in DOM order

  function rememberFree(on) {
    store.set(FREE_KEY, on);
    const secure = location.protocol === "https:" ? "; secure" : "";
    document.cookie = `${FREE_COOKIE}=${on ? 1 : 0}; path=/; max-age=31536000; samesite=lax${secure}`;
  }

  function init(table) {
    const tbody = table.tBodies[0];
    const ds = table.dataset;
    const filtered = ds.filtered === "1";
    const onPage = ds.rootKey === "__root__" && ds.storageKey === "ipam-tree:page";
    // Detail tabs (Prefix/Aggregate/VRF) name their object, e.g. "prefix:12"; their state is stored per object.
    const tab = ds.tab || "";
    const stateKey = ds.storageKey;
    // Saved state: {all: true} after "Expand all", otherwise {keys: [...]} (a bare array is the old format).
    const hasSaved = store.get(stateKey, null) !== null;
    const saved = store.get(stateKey, {});
    const savedAll = (onPage || tab) && !Array.isArray(saved) && saved.all === true;
    const expanded = new Set(Array.isArray(saved) ? saved : saved.keys || []);
    let allExpanded = false;
    let interacted = false;
    const level = (row) => Number(row.dataset.level);
    const rows = () => Array.from(tbody.querySelectorAll("tr.ipt-row"));
    const isOpen = (row) => row.getAttribute("aria-expanded") === "true";

    function url(base, params) {
      const u = new URL(base, location.origin);
      Object.entries(params).forEach(([k, v]) => u.searchParams.set(k, v));
      u.searchParams.set("free", ds.free);
      return u;
    }

    // The whole tree, as after "Expand all": the page's, or a detail tab's rooted at its object.
    const allUrl = () => (tab ? url(ds.expandUrl, { tab, all: 1 }) : url(ds.subtreeUrl, { key: "__root__" }));

    async function fetchRows(u) {
      const resp = await fetch(u, {
        headers: { "X-Requested-With": "XMLHttpRequest", "X-Tree-Page": location.pathname + location.search },
        credentials: "same-origin",
      });
      // Fragment endpoints never redirect: a redirect means the session expired and fetch() followed it to the
      // login page. Reload so the browser lands on the login form (with next= this page), not rows of login HTML.
      if (resp.redirected) {
        location.reload();
        return { ok: false, status: 0, html: "", truncated: false };
      }
      return {
        ok: resp.ok,
        status: resp.status,
        html: await resp.text(),
        truncated: resp.headers.get("X-Tree-Truncated") === "1",
      };
    }

    // A 404 fragment carries the server's error row (e.g. the node was deleted since the page loaded). Only that row
    // is kept: any other error body (NetBox's 403 or 404 page) is a full HTML page, not rows.
    function errorRows(res) {
      if (res.status !== 404) return [];
      const t = document.createElement("template");
      t.innerHTML = res.html;
      return Array.from(t.content.querySelectorAll("tr.ipt-error"));
    }

    // A detail tab's whole tree failed to load (its object was deleted or hidden since the page loaded): show the
    // server's top-level error row in its place. Anything else (403, login redirect) leaves the table as it is.
    function tabFailed(res) {
      console.warn("[ipam-tree]", new Error(`HTTP ${res.status} loading ${tab}`));
      const errors = errorRows(res);
      if (!errors.length) return;
      tbody.replaceChildren(...errors);
      banner(false);
      allExpanded = false;
    }

    function descendants(row) {
      const out = [];
      for (let r = row.nextElementSibling; r && level(r) > level(row); r = r.nextElementSibling) out.push(r);
      return out;
    }

    function save() {
      if (filtered || !(onPage || tab)) return;
      if (allExpanded) {
        store.set(stateKey, { all: true });
        return;
      }
      const inOrder = rows()
        .map((r) => r.dataset.key)
        .filter((k) => expanded.has(k));
      store.set(stateKey, { keys: inOrder.slice(0, MAX_SAVED_KEYS) });
    }

    // Show the descendants of `row` that should be visible given each ancestor's expanded state.
    function refreshVisibility(row) {
      let hideBelow = isOpen(row) ? null : level(row);
      for (const r of descendants(row)) {
        if (hideBelow !== null && level(r) > hideBelow) {
          r.classList.add("ipt-hidden");
          continue;
        }
        hideBelow = null;
        r.classList.remove("ipt-hidden");
        if (r.hasAttribute("aria-expanded") && !isOpen(r)) hideBelow = level(r);
      }
    }

    function banner(show) {
      const card = table.closest(".card");
      let el = card.previousElementSibling;
      if (!el || !el.classList.contains("ipt-banner")) {
        el = document.createElement("div");
        el.className = "alert alert-warning ipt-banner d-none";
        el.textContent = ds.truncatedMessage;
        card.before(el);
      }
      el.classList.toggle("d-none", !show);
    }

    function rememberLoaded(fromRows) {
      fromRows.forEach((r) => {
        if (isOpen(r)) expanded.add(r.dataset.key);
      });
    }

    async function load(row, endpoint) {
      row.classList.add("ipt-loading");
      row.classList.remove("ipt-failed");
      try {
        const res = await fetchRows(url(endpoint, { key: row.dataset.key, level: row.dataset.level }));
        if (!res.ok) {
          const errors = errorRows(res);
          if (errors.length) {
            descendants(row).forEach((r) => r.remove());
            row.after(...errors);
            delete row.dataset.loaded; // reopening retries instead of showing the error row
            // Open (but not remembered) so the error row follows the row: collapsing hides it, ancestor toggles keep it.
            if (row.hasAttribute("aria-expanded")) row.setAttribute("aria-expanded", "true");
          }
          throw new Error(`HTTP ${res.status} loading ${row.dataset.key}`);
        }
        descendants(row).forEach((r) => r.remove());
        row.insertAdjacentHTML("afterend", res.html);
        row.dataset.loaded = "1";
        banner(res.truncated);
        return true;
      } catch (err) {
        console.warn("[ipam-tree]", err);
        row.classList.add("ipt-failed");
        return false;
      } finally {
        row.classList.remove("ipt-loading");
      }
    }

    async function setExpanded(row, open) {
      allExpanded = false;
      if (open && !row.dataset.loaded && !(await load(row, ds.childrenUrl))) return;
      if (open && descendants(row).length === 0) {
        // Nothing visible underneath (e.g. children hidden by permissions): drop the toggle.
        row.removeAttribute("aria-expanded");
        row.querySelector(".ipt-toggle")?.replaceWith(Object.assign(document.createElement("span"), { className: "ipt-spacer" }));
        return;
      }
      row.setAttribute("aria-expanded", String(open));
      if (open) expanded.add(row.dataset.key);
      else expanded.delete(row.dataset.key);
      refreshVisibility(row);
      save();
    }

    async function expandSubtree(row) {
      if (!row.hasAttribute("aria-expanded") || !(await load(row, ds.subtreeUrl))) return;
      row.setAttribute("aria-expanded", "true");
      expanded.add(row.dataset.key);
      rememberLoaded(descendants(row));
      refreshVisibility(row);
      save();
    }

    async function expandAll() {
      if (filtered) {
        // Keep the filtered result: reopen everything already loaded instead of fetching the whole tree.
        rows().forEach((r) => {
          if (r.dataset.loaded) r.setAttribute("aria-expanded", "true");
          r.classList.remove("ipt-hidden");
        });
        // Error rows come back with the node they sit under, which stays open (and unloaded) like after load().
        tbody.querySelectorAll("tr.ipt-error").forEach((r) => {
          r.classList.remove("ipt-hidden");
          tbody.querySelector(`tr[data-key="${CSS.escape(r.dataset.parent)}"]`)?.setAttribute("aria-expanded", "true");
        });
        return;
      }
      if (!onPage && !tab) {
        // Any other table: expand each top-level row of this table in turn.
        const top = Math.min(...rows().map(level));
        for (const row of rows().filter((r) => level(r) === top)) await expandSubtree(row);
        return;
      }
      table.classList.add("ipt-busy");
      try {
        // A detail tab's whole tree is rooted at its object; both share one expand_all_limit budget.
        const res = await fetchRows(allUrl());
        if (!res.ok) {
          if (tab) tabFailed(res);
          return;
        }
        tbody.innerHTML = res.html;
        banner(res.truncated);
        rememberLoaded(rows());
        allExpanded = true;
        save();
      } finally {
        table.classList.remove("ipt-busy");
      }
    }

    function collapseAll() {
      const all = rows();
      if (!all.length) return;
      const top = Math.min(...all.map(level));
      all.forEach((r) => {
        if (r.hasAttribute("aria-expanded")) r.setAttribute("aria-expanded", "false");
        r.classList.toggle("ipt-hidden", level(r) > top);
      });
      // Error rows sit under a node that failed to load: they go with their parent.
      tbody.querySelectorAll("tr.ipt-error").forEach((r) => r.classList.toggle("ipt-hidden", level(r) > top));
      expanded.clear();
      allExpanded = false;
      save();
    }

    async function restore(serverFree) {
      if (filtered) return;
      const keys = () => Array.from(expanded).slice(0, MAX_SAVED_KEYS).join(",");
      let res;
      if (onPage) {
        if (!savedAll && expanded.size === 0) return;
        res = await fetchRows(savedAll ? allUrl() : url(ds.expandUrl, { keys: keys() }));
      } else if (tab) {
        // The server opened the tab's object: re-render rooted at it for a saved state (an empty one too, after
        // "Collapse all"), or when it rendered free space differently from the remembered preference.
        if (!hasSaved && ds.free === serverFree) return;
        res = await fetchRows(savedAll ? allUrl() : url(ds.expandUrl, { tab, keys: keys() }));
      } else {
        return;
      }
      // Never overwrite what the user did while the restore was loading.
      if (interacted) return;
      if (!res.ok) {
        if (tab) tabFailed(res);
        return;
      }
      if (!res.html.trim()) return;
      tbody.innerHTML = res.html;
      tbody.querySelector("tr.ipt-row")?.setAttribute("tabindex", "0");
      banner(res.truncated);
      allExpanded = savedAll;
      if (savedAll) rememberLoaded(rows());
    }

    table.addEventListener("click", (e) => {
      const btn = e.target.closest(".ipt-toggle");
      if (btn) interacted = true;
      if (!btn) return;
      const row = btn.closest("tr");
      if (e.altKey) expandSubtree(row);
      else setExpanded(row, !isOpen(row));
    });

    table.addEventListener("keydown", (e) => {
      const row = e.target.closest("tr.ipt-row");
      if (!row) return;
      interacted = true;
      const visible = rows().filter((r) => !r.classList.contains("ipt-hidden"));
      const i = visible.indexOf(row);
      const focus = (r) => {
        if (!r) return;
        row.tabIndex = -1;
        r.tabIndex = 0;
        r.focus();
      };
      switch (e.key) {
        case "ArrowDown":
          focus(visible[i + 1]);
          break;
        case "ArrowUp":
          focus(visible[i - 1]);
          break;
        case "ArrowRight":
          if (row.hasAttribute("aria-expanded") && !isOpen(row)) setExpanded(row, true);
          else focus(visible[i + 1]);
          break;
        case "ArrowLeft":
          if (isOpen(row)) setExpanded(row, false);
          else if (row.dataset.parent) focus(tbody.querySelector(`tr[data-key="${CSS.escape(row.dataset.parent)}"]`));
          break;
        case "*":
          expandSubtree(row);
          break;
        case "Enter": {
          const a = row.querySelector("td.ipt-name a");
          if (a) a.click();
          break;
        }
        default:
          return;
      }
      e.preventDefault();
    });

    const mark = (fn) => () => {
      interacted = true;
      fn();
    };
    document.querySelectorAll('[data-ipt-action="expand-all"]').forEach((b) => b.addEventListener("click", mark(expandAll)));
    document.querySelectorAll('[data-ipt-action="collapse-all"]').forEach((b) => b.addEventListener("click", mark(collapseAll)));
    document.querySelectorAll('[data-ipt-action="toggle-free"]').forEach((sw) => {
      sw.addEventListener("change", () => {
        rememberFree(sw.checked);
        ds.free = sw.checked ? "1" : "0";
        // Reload so already-expanded nodes are re-rendered with or without free space.
        const u = new URL(location.href);
        u.searchParams.set("free", ds.free);
        location.assign(u);
      });
    });

    // A remembered free-space preference applies when the URL does not say otherwise. The server reads it from the
    // cookie; rewriting the cookie here also covers preferences saved before the cookie existed.
    const serverFree = ds.free;
    if (!new URL(location.href).searchParams.has("free")) {
      const savedFree = store.get(FREE_KEY, null);
      if (savedFree !== null) {
        rememberFree(savedFree);
        ds.free = savedFree ? "1" : "0";
        const sw = document.getElementById("ipt-free");
        if (sw) sw.checked = savedFree;
      }
    }
    // Nothing saved for this tab yet: what the server opened is the state to keep.
    if (tab && !hasSaved) rememberLoaded(rows());
    const first = tbody.querySelector("tr.ipt-row");
    if (first) first.tabIndex = 0;
    restore(serverFree);
  }

  document.addEventListener("DOMContentLoaded", () => document.querySelectorAll("table.ipt-tree").forEach(init));
})();
