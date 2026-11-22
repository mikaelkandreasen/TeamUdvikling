// Minimal JS (CSP: kun scripts fra 'self'). Appen virker uden JS; dette er kun bekvemmelighed.
document.addEventListener("change", function (e) {
  var t = e.target;
  if (t.matches && t.matches("[data-autosubmit]") && t.form) { t.form.submit(); }
});
document.addEventListener("click", function (e) {
  if (e.target.matches && e.target.matches("[data-print]")) { window.print(); }
});
// Evaluering: husk hvilke spillertyper (rollepaneler) der er åbne, når man går til næste/forrige spiller.
(function () {
  function openRoles() {
    var out = [];
    document.querySelectorAll("details.role[data-role]").forEach(function (d) { if (d.open) { out.push(d.getAttribute("data-role")); } });
    return out.join(",");
  }
  document.addEventListener("submit", function (e) {
    var f = e.target, h = f && f.querySelector ? f.querySelector("[data-open-roles]") : null;
    if (h) { h.value = openRoles(); }
  }, true);
  document.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest("a[data-keep-open]") : null;
    if (a) { e.preventDefault(); window.location.href = a.getAttribute("href") + (a.getAttribute("href").indexOf("?") < 0 ? "?" : "&") + "open=" + encodeURIComponent(openRoles()); }
  });
})();

// Invitation: tjek live om brugernavnet er ledigt (serveren kontrollerer det igen ved oprettelse).
(function () {
  var inp = document.querySelector("[data-userchk]"), out = document.getElementById("uchk"), timer = null;
  if (!inp || !out || !window.fetch) { return; }
  inp.addEventListener("input", function () {
    clearTimeout(timer);
    var v = inp.value.trim();
    if (!v) { out.textContent = ""; return; }
    timer = setTimeout(function () {
      fetch(inp.getAttribute("data-userchk") + "?u=" + encodeURIComponent(v), { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (j) { if (inp.value.trim() === v) { out.textContent = j.msg || ""; out.style.color = j.ok ? "#1b7a3a" : "#b00020"; } })
        .catch(function () { out.textContent = ""; });
    }, 350);
  });
})();

// Fremmøde: «Alle» / «Ingen».
document.addEventListener("click", function (e) {
  var b = e.target.closest && e.target.closest("[data-checkall]");
  if (!b || !b.form) { return; }
  var on = b.getAttribute("data-checkall") === "1";
  b.form.querySelectorAll('input[type=checkbox][name=present]').forEach(function (c) { c.checked = on; });
});

// Delvise opdateringer uden sideskift (progressiv forbedring): <form data-swap="#id1,#id2"> sendes med fetch, og kun de angivne dele
// (+ beskeder) udskiftes med svarsiden. Uden JS, eller hvis noget går galt, virker formularen som en almindelig POST.
(function () {
  if (!window.fetch || !window.DOMParser) { return; }
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (!f || !f.matches || !f.matches("form[data-swap]") || e.defaultPrevented) { return; }
    if (e.submitter && e.submitter.hasAttribute("data-noswap")) { return; }       // knap der skal til en anden side (fx «Gem & næste»)
    var sels = f.getAttribute("data-swap").split(",").map(function (x) { return x.trim(); }).filter(Boolean);
    var body = new FormData(f);
    if (e.submitter && e.submitter.name) { body.append(e.submitter.name, e.submitter.value); }
    e.preventDefault();
    var busy = f.querySelectorAll("button"); busy.forEach(function (b) { b.disabled = true; });
    fetch(f.getAttribute("action") || window.location.href, { method: (f.method || "post").toUpperCase(), body: body, credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.text().then(function (t) { return { r: r, t: t }; }); })
      .then(function (x) {
        try {
        var doc = new DOMParser().parseFromString(x.t, "text/html");
        var pairs = sels.map(function (s) { return [document.querySelector(s), doc.querySelector(s)]; });
        var ok = x.r.status < 500 && pairs.every(function (p) { return p[0] && p[1]; }) && doc.querySelector("main");
        if (!ok) { window.location.href = x.r.url || window.location.href; return; }
        pairs.forEach(function (p) { p[0].replaceWith(document.importNode(p[1], true)); });
        document.querySelectorAll("main > .flash").forEach(function (n) { n.remove(); });
        var main = document.querySelector("main"), first = main.firstChild;
        doc.querySelectorAll("main > .flash").forEach(function (n) { main.insertBefore(document.importNode(n, true), first); });
        window.scrollTo({ top: Math.max(0, (main.getBoundingClientRect().top + window.pageYOffset) - 8) });
        } catch (err) { window.location.href = x.r.url || window.location.href; }      // formularen er allerede sendt: vis resultatsiden i stedet for at sende igen
      }, function () { busy.forEach(function (b) { b.disabled = false; }); f.removeAttribute("data-swap"); f.submit(); });   // netværksfejl før svar: almindelig POST
  });
})();
