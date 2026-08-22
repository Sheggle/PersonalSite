/* Board-state engine + card rendering, shared by both pages. */
"use strict";

/* ═══════════════════════════════════════════════════════════════
   ENGINE — the board is recomputed from step 0 every time, so the
   state can never drift out of sync with the narrative.
   ═══════════════════════════════════════════════════════════════ */
let KEY = 0;
function freshState(){
  KEY = 0;
  const side = () => ({life:20, hand:0, grave:0, lands:[], perms:[]});
  return {turn:"", note:"", cast:[], reveal:null, jones:side(), ruel:side()};
}
function clone(s){return JSON.parse(JSON.stringify(s));}

function helpers(S){
  const side = p => S[p];
  const find = (p,name,opt={}) => {
    const list = side(p).perms.filter(x => x.name===name && !x.dead);
    if(opt.haunted) return list.find(x=>x.haunted) || list[0];
    return list.find(x=>!x.haunted) || list[0];
  };
  return {
    draw(p){ side(p).hand++; },
    hand(p,d){ side(p).hand += d; },
    life(p,d){ side(p).life += d; },
    land(p,name,o={}){ side(p).lands.push({key:++KEY, name, tapped:!!o.tapped, land:true}); },
    bounceLand(p,name){
      const L = side(p).lands, i = L.map(x=>x.name).lastIndexOf(name);
      if(i>=0) L.splice(i,1);
      side(p).hand++;
    },
    add(p,name,o={}){
      side(p).perms.push({key:++KEY, name, tapped:!!o.tapped, sick:!!o.sick,
        art:!!o.art, pt:o.pt||null, atk:false, blk:false, haunted:false, equip:null, eqOn:null});
    },
    kill(p,name,o={}){
      const t = find(p,name,o);
      if(!t) return;
      t.dead = true; side(p).grave++;
      if(t.equip){ const c = side(p).perms.find(x=>x.key===t.equip); if(c) c.eqOn = null; }
      if(t.eqOn){ const e = side(p).perms.find(x=>x.key===t.eqOn);  if(e) e.equip = null; }
    },
    equip(p,eq,target){
      const E = find(p,eq), T = find(p,target);
      if(!E||!T) return;
      side(p).perms.forEach(x=>{ if(x.eqOn===E.key) x.eqOn=null; });
      E.equip = T.key; T.eqOn = E.key;
    },
    haunt(p,name){ const t = find(p,name); if(t) t.haunted = true; },
    blockWith(p,names){
      names.forEach(n=>{
        const t = side(p).perms.find(x=>x.name===n && !x.blk && !x.dead);
        if(t) t.blk = true;
      });
    },
    attackWith(p,names){
      names.forEach(n=>{
        const t = side(p).perms.find(x=>x.name===n && !x.atk && !x.dead);
        if(t){ t.atk = true; t.tapped = true; }
      });
    },
    cast(p,name,word){
      S.cast.push({p, name, word: word || "casts"});
      const d = CARDS[name] || {};
      // instants and sorceries go to the graveyard on resolution — except Seize the
      // Soul, which is exiled to haunt a creature instead.
      if(/^(Instant|Sorcery)/.test(d.type||"") && name !== "Seize the Soul") side(p).grave++;
    },
    reveal(cards,taken){ S.reveal = {cards, taken}; },
    note(t){ S.note = t; }
  };
}

const SNAPS = (()=>{
  let S = freshState(); const out = [];
  STEPS.forEach(step=>{
    ["jones","ruel"].forEach(p=>{
      S[p].perms = S[p].perms.filter(x=>!x.dead);
      S[p].perms.forEach(x=>{ x.tapped=false; x.sick=false; x.atk=false; x.blk=false; });
      S[p].lands.forEach(x=>{ x.tapped=false; });
    });
    S.cast = []; S.note = ""; S.reveal = null; S.turn = step.turn;
    step.do(helpers(S));
    out.push(clone(S));
  });
  return out;
})();

/* ═══════════════════════════════════════════════════════════════

   RENDER
   ═══════════════════════════════════════════════════════════════ */
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

function pips(cost){
  if(!cost) return "";
  const m = cost.match(/\{[^}]+\}/g) || [];
  return m.map(t=>{
    const v = t.slice(1,-1);
    if(/^\d+$/.test(v)) return `<span class="pip C">${v}</span>`;
    if(/^[WUBRG]$/.test(v)) return `<span class="pip ${v}">${v}</span>`;
    if(v.includes("/")) return `<span class="pip C">${v.replace(/\//g,"")}</span>`;
    return `<span class="pip C">${esc(v)}</span>`;
  }).join("");
}
const FRAME = {W:["--c-w","--c-w-ink"],U:["--c-u","--c-u-ink"],B:["--c-b","--c-b-ink"],
  R:["--c-r","--c-r-ink"],G:["--c-g","--c-g-ink"],M:["--c-m","--c-m-ink"],
  A:["--c-a","--c-a-ink"],L:["--c-l","--c-l-ink"]};

function cardEl(perm, isLand){
  const d = CARDS[perm.name] || {};
  const fr = FRAME[d.frame || "A"];
  const slot = document.createElement("div");
  slot.className = "slot" + (isLand ? " land" : "");
  if(perm.dead) slot.classList.add("doomed");
  const c = document.createElement("div");
  c.className = "card" + (isLand ? " land" : "") + (perm.tapped ? " tapped" : "") +
                (d.frame === "W" ? " wframe" : "");
  c.style.setProperty("--bg", `var(${fr[0]})`);
  c.style.setProperty("--fg", `var(${fr[1]})`);
  const pt = perm.pt || d.pt || "";
  const sub = (d.type||"").split("—")[1];
  const typeLine = d.token ? "Token"
    : sub ? sub.trim().split(/\s+/).pop()          // "Human Samurai" -> "Samurai"
    : (d.type||"").trim();
  c.innerHTML =
    (d.cost ? `<div class="costrow">${pips(d.cost)}</div>` : "") +
    `<div class="cname">${esc(perm.name.replace(/,.*$/,""))}</div>` +
    (isLand ? `<div class="taps">${(d.taps||"").split("").map(x=>`<span class="pip ${x}">${x}</span>`).join("")}</div>`
            : `<div class="ctype">${esc(typeLine)}</div>`) +
    (pt ? `<div class="ptbox">${esc(pt)}</div>` : "");
  const badges = [];
  if(perm.atk) badges.push(`<span class="bdg atk">ATTACKING</span>`);
  if(perm.blk) badges.push(`<span class="bdg blk">BLOCKING</span>`);
  if(perm.eqOn) badges.push(`<span class="bdg jitte">JITTE</span>`);
  if(perm.haunted) badges.push(`<span class="bdg haunt">HAUNTED</span>`);
  if(perm.sick) badges.push(`<span class="bdg sick">CAN'T ATTACK YET</span>`);
  if(badges.length) c.insertAdjacentHTML("afterbegin",
    `<div class="badge-row">${badges.slice(0,2).join("")}</div>`);
  slot.appendChild(c);
  c.dataset.card = perm.name;
  return slot;
}

function fillRow(el, list, prevKeys, isLand){
  el.innerHTML = "";
  if(!list.length){
    el.classList.add("empty");
    el.innerHTML = `<span class="row-empty-note">${isLand ? "no lands" : "no creatures"}</span>`;
    return;
  }
  el.classList.remove("empty");
  list.forEach(p=>{
    const s = cardEl(p, isLand);
    if(!prevKeys.has(p.key)) s.firstChild.classList.add("fresh");
    el.appendChild(s);
  });
}

function setLife(el, val, prev){
  el.querySelector(".n").textContent = val;
  el.classList.toggle("low", val <= 5);
  const old = el.querySelector(".delta");
  if(old) old.remove();
  if(prev !== null && prev !== val){
    const d = document.createElement("span");
    const diff = val - prev;
    d.className = "delta " + (diff < 0 ? "down" : "up");
    d.textContent = (diff > 0 ? "+" : "") + diff;
    el.appendChild(d);
  }
}

function prose(html){
  return String(html)
    .replace(/<b>([^<]+)<\/b>/g, (m,t)=>{
      const k = Object.keys(CARDS).find(x => x===t || x.replace(/,.*$/,"")===t);
      return k ? `<b class="cn" data-card="${k}">${t}</b>` : m;
    })
    .replace(/\[\[([a-z]+)\|([^\]]+)\]\]/g, (m,k,l)=>`<b class="g" data-g="${k}" tabindex="0">${l}</b>`)
    .replace(/\[\[([a-z]+)\]\]/g, (m,k)=>`<b class="g" data-g="${k}" tabindex="0">${(GLOSS[k]||["?"])[0].toLowerCase()}</b>`);
}
