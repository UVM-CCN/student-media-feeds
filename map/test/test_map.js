/* Exercise map/index.html's script with a stubbed Leaflet + DOM. */
const fs = require("fs");
const path = require("path");

const ROOT = "/Users/bcooley/dev/student-media-feeds";
const html = fs.readFileSync(path.join(ROOT, "map/index.html"), "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const code = scripts[scripts.length - 1];

/* ---- minimal DOM ---- */
const els = {};
function mkEl(id) {
  return {
    id, textContent: "", innerHTML: "", className: "", type: "", dataset: {}, checked: false,
    children: [], attrs: {},
    setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { this.children.push(c); },
    addEventListener(ev, fn) { (this._h ||= {})[ev] = fn; },
    closest() { return null; }
  };
}
["map", "topics", "modes", "modeHint", "showPts", "nPubs", "nStories",
 "scaleLo", "scaleHi", "scaleUnit"].forEach(id => (els[id] = mkEl(id)));

// The mode toggle's buttons are static markup in the page, so seed them here.
["count", "share"].forEach(m => {
  const b = mkEl("mode-" + m);
  b.dataset.mode = m;
  els.modes.children.push(b);
});

global.document = {
  getElementById: id => els[id] || (els[id] = mkEl(id)),
  createElement: () => mkEl("new"),
  querySelector: sel => {
    const m = /data-mode="(\w+)"/.exec(sel);
    return m ? els.modes.children.find(b => b.dataset.mode === m[1]) : null;
  }
};

/* ---- minimal Leaflet ---- */
let heatData = null, markerCount = 0, popups = [];
const chain = obj => new Proxy(obj, { get: (t, k) => (k in t ? t[k] : () => chain(t)) });
global.L = {
  map: () => chain({ setView: () => chain({}), removeLayer: () => {} }),
  tileLayer: () => chain({ addTo: () => {} }),
  heatLayer: () => chain({
    setLatLngs: d => { heatData = d; },
    addTo() { return this; }
  }),
  layerGroup: () => chain({
    clearLayers: () => { markerCount = 0; },
    addTo() { return this; }
  }),
  circleMarker: () => chain({
    bindPopup(h) { popups.push(h); markerCount++; return this; },
    addTo() { return this; }
  })
};

global.window = {};
require(path.join(ROOT, "map/map_data.js"));

eval(code);

/* ---- assertions ---- */
let fail = 0;
function check(name, cond, detail) {
  if (!cond) { fail++; console.log("  FAIL " + name + (detail ? " — " + detail : "")); }
  else console.log("  ok   " + name + (detail ? " — " + detail : ""));
}

const topicsEl = els.topics;
console.log("topic buttons: " + topicsEl.children.length);
check("11 buttons (all + 10 topics)", topicsEl.children.length === 11);

function selectTopic(key) { topicsEl.children.find(b => b.dataset.key === key)._h.click(); }
function setMode(mode) {
  const btn = els.modes.children.find(b => b.dataset.mode === mode);
  els.modes._h.click.call(els.modes, { target: { closest: () => btn } });
}

const keys = ["__all__", ...window.MAP_DATA.topics.map(t => t.key)];

console.log("\n--- count mode ---");
setMode("count");
for (const k of keys) {
  selectTopic(k);
  const vals = heatData.map(r => r[2]);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const bad = vals.filter(v => !(v >= 0 && v <= 1)).length;
  check(k.padEnd(12), bad === 0 && Math.abs(mx - 1) < 1e-9 && mn >= 0.11,
        `n=${heatData.length} min=${mn.toFixed(3)} max=${mx.toFixed(3)} legend=[${els.scaleLo.textContent}..${els.scaleHi.textContent}]`);
}

console.log("\n--- share mode ---");
setMode("share");
for (const k of keys) {
  selectTopic(k);
  const vals = heatData.map(r => r[2]);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  check(k.padEnd(12), vals.every(v => v >= 0 && v <= 1) && Math.abs(mx - 1) < 1e-9,
        `n=${heatData.length} min=${mn.toFixed(3)} legend=[${els.scaleLo.textContent}..${els.scaleHi.textContent}] ${els.scaleUnit.textContent}`);
}

console.log("\n--- popups (markers on) ---");
setMode("count");
selectTopic("immigration");
els.showPts.checked = true;
els.showPts._h.change.call(els.showPts);
check("markers created", markerCount > 0, markerCount + " markers");
const sample = popups[0];
const barCount = (sample.match(/class="pop-bar[ "]/g) || []).length;
check("every category charted", barCount === 10, barCount + " bars in first popup");
check("selected topic highlighted", /pop-bar sel/.test(popups.join("")));
check("zero categories rendered", /pop-bar zero/.test(popups.join("")));
check("domain shown in popup", /pop-inst/.test(sample));

console.log("\nsample popup:\n" + sample.replace(/></g, ">\n<").split("\n").slice(0, 8).join("\n"));
process.exit(fail ? 1 : 0);
