/* Cockpit — site : langue, copie du nom, portrait du personnage à soutenir (API publique d'EVE). */
(function () {
  try { localStorage.setItem("cockpit.site.lang", document.documentElement.lang); } catch (e) { /* */ }
  document.querySelectorAll("[data-setlang]").forEach(function (a) {
    a.addEventListener("click", function () { try { localStorage.setItem("cockpit.site.lang", a.dataset.setlang); } catch (e) { /* */ } });
  });
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      var txt = b.dataset.copy, label = b.textContent;
      (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).catch(function () {
        var t = document.createElement("textarea"); t.value = txt; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove();
      }).finally(function () { b.textContent = window.COPIED || "OK"; b.classList.add("ok"); setTimeout(function () { b.textContent = label; b.classList.remove("ok"); }, 1800); });
    });
  });
  // portrait et corporation du pilote (ESI public, sans connexion)
  var name = window.DONATE_CHARACTER;
  if (!name || !document.querySelector("[data-portrait]")) return;
  fetch("https://esi.evetech.net/universe/ids", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify([name]) })
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var c = (j.characters || [])[0]; if (!c) return;
      document.querySelectorAll("[data-portrait]").forEach(function (img) { img.src = "https://images.evetech.net/characters/" + c.id + "/portrait?size=256"; });
      return fetch("https://esi.evetech.net/characters/" + c.id + "/").then(function (r) { return r.json(); }).then(function (ch) {
        if (!ch.corporation_id) return;
        return fetch("https://esi.evetech.net/corporations/" + ch.corporation_id + "/").then(function (r) { return r.json(); }).then(function (co) {
          document.querySelectorAll("[data-pcorp]").forEach(function (el) { el.textContent = co.name ? co.name + (co.ticker ? " [" + co.ticker + "]" : "") : ""; });
        });
      });
    }).catch(function () { /* hors ligne : on garde l'image par défaut */ });
})();
