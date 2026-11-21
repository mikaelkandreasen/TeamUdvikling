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
