// Minimal JS (CSP: kun scripts fra 'self'). Appen virker uden JS; dette er kun bekvemmelighed.
document.addEventListener("change", function (e) {
  var t = e.target;
  if (t.matches && t.matches("[data-autosubmit]") && t.form) { t.form.submit(); }
});
document.addEventListener("click", function (e) {
  if (e.target.matches && e.target.matches("[data-print]")) { window.print(); }
});
