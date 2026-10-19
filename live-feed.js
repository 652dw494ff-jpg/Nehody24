(() => {
  const list = document.getElementById("list");
  const search = document.getElementById("search");
  const type = document.getElementById("type");
  const count = document.getElementById("count");
  const panel = list?.closest(".panel");
  const status = document.getElementById("trafficStatus");
  if (!list || !search || !type || !count) return;
  if (panel) {
    const heading = panel.querySelector("h2");
    if (heading) heading.textContent = "Aktuální dopravní události";
    const note = panel.querySelector(".small");
    if (note) note.textContent = "Data se automaticky načítají z veřejného XML zdroje Policie ČR. Pokud se strukturu dat nepodaří ověřit, seznam zůstane prázdný — žádné ukázkové nehody se nevydávají za skutečné.";
  }
  let events = [];
  const norm = value => String(value || "").toLocaleLowerCase("cs");
  function render() {
    const q = norm(search.value.trim()), t = type.value;
    const rows = events.filter(e => (!t || e.displayType === t) &&
      [e.displayType,e.title,e.location,e.description,e.start,e.end].join(" ").toLocaleLowerCase("cs").includes(q));
    count.textContent = String(rows.length);
    list.replaceChildren();
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = events.length ? "Žádná událost neodpovídá filtru." : "Žádné ověřené události se zatím nepodařilo načíst.";
      list.appendChild(empty);
      return;
    }
    rows.forEach(e => {
      const card = document.createElement("article");
      card.className = "incident";
      const symbol = document.createElement("div");
      symbol.className = "symbol";
      symbol.setAttribute("aria-hidden", "true");
      symbol.textContent = /nehod|sráž|havári/i.test(e.displayType + " " + e.title) ? "⚠" : /uzav/i.test(e.displayType + " " + e.title) ? "⛔" : "🚧";
      const body = document.createElement("div");
      const tag = document.createElement("span");
      tag.className = "tag info"; tag.textContent = e.displayType;
      const h3 = document.createElement("h3"); h3.textContent = e.title || e.displayType;
      body.append(tag,h3);
      if (e.location) { const p=document.createElement("p"); const b=document.createElement("strong"); b.textContent=e.location; p.appendChild(b); body.appendChild(p); }
      if (e.description) { const p=document.createElement("p"); p.textContent=e.description; body.appendChild(p); }
      if (e.start || e.end) { const p=document.createElement("p"); p.textContent=[e.start ? "Od: "+e.start : "",e.end ? "Do: "+e.end : ""].filter(Boolean).join(" · "); body.appendChild(p); }
      const state=document.createElement("div"); state.className="status"; state.textContent="Zdroj: Policie ČR";
      card.append(symbol,body,state); list.appendChild(card);
    });
  }
  function setStatus(text) { if (status) status.textContent = text; }
  async function load() {
    setStatus("Načítám poslední synchronizaci dopravních dat…");
    try {
      const response = await fetch("data/traffic.json?ts=" + Date.now(), {cache:"no-store"});
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      events = (Array.isArray(data.events) ? data.events : []).map((e,i) => {
        const type = String(e.type || "Dopravní událost");
        const title = String(e.title || type);
        return {...e, title, displayType:type, id:e.id || String(i)};
      });
      type.replaceChildren(new Option("Všechny typy", ""));
      [...new Set(events.map(e => e.displayType))].sort().forEach(t => type.add(new Option(t,t)));
      if (data.warning) setStatus(data.warning + " · Poslední pokus: " + new Date(data.fetchedAt).toLocaleString("cs-CZ"));
      else setStatus("Zdroj: Policie ČR · Načteno " + events.length + " položek · synchronizace " + new Date(data.fetchedAt).toLocaleString("cs-CZ"));
      render();
    } catch (error) {
      events = [];
      render();
      setStatus("Živý seznam teď není dostupný. Zkus oficiální mapu Policie ČR. (" + error.message + ")");
    }
  }
  search.addEventListener("input", render);
  type.addEventListener("change", render);
  const statusEl = document.createElement("p");
  statusEl.id = "trafficStatus"; statusEl.className = "small"; statusEl.setAttribute("role","status");
  if (panel) panel.insertBefore(statusEl, list);
  load();
  setInterval(load, 180000);
})();