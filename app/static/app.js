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
