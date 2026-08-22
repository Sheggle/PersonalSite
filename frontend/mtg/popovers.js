/* Card and glossary popovers, shared by both pages. */
"use strict";

const cardpop = $("cardpop"), gpop = $("gpop");
function place(el, x, y){
  const r = el.getBoundingClientRect();
  let left = x + 16, top = y + 14;
  if(left + r.width > innerWidth - 12) left = x - r.width - 16;
  if(top + r.height > innerHeight - 12) top = Math.max(12, y - r.height - 14);
  el.style.left = left + "px"; el.style.top = top + "px";
}
function showCard(name, x, y){
  const d = CARDS[name]; if(!d) return;
  cardpop.innerHTML = `<h4>${esc(name)}</h4>` +
    `<div class="meta">${d.cost ? esc(d.cost.replace(/[{}]/g,"")) + " · " : ""}${esc(d.type)}${d.pt ? " · " + d.pt : ""}</div>` +
    (d.text ? `<div class="rules">${esc(d.text)}</div>` : "") +
    (d.plain ? `<div class="plain">${esc(d.plain)}</div>` : "");
  cardpop.classList.add("on"); place(cardpop, x, y);
}
function showGloss(k, x, y){
  const g = GLOSS[k]; if(!g) return;
  gpop.innerHTML = `<h4>${esc(g[0])}</h4><p>${esc(g[1])}</p>`;
  gpop.classList.add("on"); place(gpop, x, y);
}
document.addEventListener("mouseover", e=>{
  const c = e.target.closest("[data-card]");
  if(c){ showCard(c.dataset.card, e.clientX, e.clientY); } else { cardpop.classList.remove("on"); }
  const g = e.target.closest(".g");
  if(g){ showGloss(g.dataset.g, e.clientX, e.clientY); } else { gpop.classList.remove("on"); }
});
document.addEventListener("focusin", e=>{
  const g = e.target.closest(".g");
  if(g){ const r = g.getBoundingClientRect(); showGloss(g.dataset.g, r.left, r.bottom); }
});
document.addEventListener("click", e=>{
  const g = e.target.closest(".g");
  if(g){ e.preventDefault(); showGloss(g.dataset.g, e.clientX, e.clientY); }
});
