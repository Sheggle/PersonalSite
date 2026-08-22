/* Two-player table: same board, same script, one player per side.
   The server only ever relays a step number — both clients rebuild the whole
   board from SNAPS, so there is no game state that can desynchronise. */
"use strict";

const params = new URLSearchParams(location.search);
let room = (params.get("room") || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 5);
let me = null;               // "jones" | "ruel"
let idx = 0;
let sides = {};              // which seats are taken
let peers = 0;
let ws = null;
let retry = 0;

const other = s => (s === "jones" ? "ruel" : "jones");
const NAME = { jones: "Craig Jones", ruel: "Olivier Ruel" };
const DECK = { jones: "England · Zoo", ruel: "France · Hand in Hand" };

/* Narrator steps (the framing at either end) may be advanced by either player.
   Every other step belongs to whoever acts in it. */
function actorOf(i) {
  if (i < 3 || i === STEPS.length - 1) return null;
  return STEPS[i].turn.includes("Ruel") ? "ruel" : "jones";
}

const SRC_TIP = {
  coverage: "Stated in the official Wizards of the Coast event coverage.",
  report: "Stated by Craig Jones in his own tournament report.",
  bridge: "Reconstructed connective tissue — the reading that fits every documented number."
};

/* ── board ─────────────────────────────────────────────────────── */
function paint() {
  const step = STEPS[idx], S = SNAPS[idx], prev = idx > 0 ? SNAPS[idx - 1] : null;
  const bottom = me || "jones", top = other(bottom);

  [["top", top], ["bot", bottom]].forEach(([slot, side]) => {
    const prevKeys = new Set(prev ? [...prev[side].perms, ...prev[side].lands].map(x => x.key) : []);
    fillRow($(slot + "Perms"), S[side].perms, prevKeys, false);
    fillRow($(slot + "Lands"), S[side].lands, prevKeys, true);

    const n = S[side].hand, grew = prev && n > prev[side].hand;
    // Your own hand is yours to see; the opponent's is a stack of backs either way,
    // because in this game every card that matters gets named as it is cast.
    $(slot + "Hand").innerHTML =
      Array.from({ length: n }, (_, k) => `<span class="back${grew && k === n - 1 ? " fresh" : ""}"></span>`).join("") +
      `<span class="handlbl">${n ? `<b>${n}</b> in hand` : "hand empty"}</span>`;

    $(slot + "Grave").textContent = S[side].grave;
    setLife($(slot + "Life"), S[side].life, prev ? prev[side].life : null);
    $(slot + "Name").textContent = NAME[side] + (side === me ? " — you" : "");
    $(slot + "Deck").textContent = DECK[side];
    $(slot + "Zone").classList.toggle("mine", side === me);
    $(slot + "Zone").classList.toggle("seated", !!sides[side]);
  });

  $("turnChip").innerHTML = `<b>${esc(S.turn)}</b>`;
  const sz = $("stackZone"); sz.innerHTML = "";
  S.cast.forEach(c => {
    const w = document.createElement("span");
    w.className = "spellchip";
    w.innerHTML = `<span class="sw">${c.p === "jones" ? "Jones" : "Ruel"} ${esc(c.word)}</span>` +
                  `<span class="sn" data-card="${esc(c.name)}">${esc(c.name)}</span>`;
    sz.appendChild(w);
  });
  if (S.reveal) {
    const w = document.createElement("span");
    w.className = "spellchip";
    w.innerHTML = `<span class="sw">Hand revealed</span><span class="sn" style="font-size:12px">` +
      S.reveal.cards.map(n => {
        const short = n.replace(/,.*$/, "");
        return n === S.reveal.taken
          ? `<span data-card="${esc(n)}" style="text-decoration:line-through;opacity:.55">${esc(short)}</span>`
          : `<span data-card="${esc(n)}">${esc(short)}</span>`;
      }).join(" · ") + `</span>`;
    sz.appendChild(w);
  }
  $("boardNote").textContent = step.hero ? "" : (S.note || "");

  const sw = $("slamwrap");
  sw.classList.toggle("on", !!step.hero);
  if (step.hero) {
    const d = CARDS[step.hero], fr = FRAME[d.frame || "A"];
    sw.innerHTML = `<div class="slam"><div class="bigcard" data-card="${esc(step.hero)}" ` +
      `style="--bg:var(${fr[0]});--fg:var(${fr[1]})">` +
      `<div class="costrow">${pips(d.cost)}</div><div class="bn">${esc(step.hero)}</div>` +
      `<div class="bt">${esc(d.type)}</div><div class="bx">${esc(d.text)}</div></div>` +
      `<div class="cap"><span class="k">${esc(step.heroKicker || "")}</span>` +
      `<span class="t">${step.heroTitle || ""}</span>` +
      `<span class="s">${step.heroSub || ""}</span></div></div>`;
  } else sw.innerHTML = "";

  const bare = !S.jones.perms.length && !S.ruel.perms.length && !S.jones.lands.length && !S.ruel.lands.length;
  $("board").classList.toggle("pre", bare);
  $("board").classList.toggle("climax", !!step.climax);

  /* ── analysis ── */
  const a = $("analysis");
  a.classList.toggle("climax", !!step.climax);
  const out = [`<div class="eyebrow"><span class="turn">${esc(step.turn)}</span>` +
    `<span class="src" data-src="${step.src}" title="${SRC_TIP[step.src]}">${step.src}</span></div>`,
    `<h2>${step.title}</h2>`];
  (step.p || []).forEach((t, n) => out.push(`<p${n === 0 ? ' class="lead"' : ""}>${prose(t)}</p>`));
  if (step.klaxon) out.push(`<div class="box klaxon"><span class="bl">${esc(step.klaxon.t)}</span><p>${prose(step.klaxon.h)}</p></div>`);
  if (step.quote) out.push(`<blockquote>&ldquo;${step.quote.text}&rdquo;<cite>${esc(step.quote.cite)}</cite></blockquote>`);
  (step.p2 || []).forEach(t => out.push(`<p>${prose(t)}</p>`));
  if (step.math) out.push(`<div class="math">${step.math.replace(/\n/g, "<br>")}</div>`);
  (step.boxes || []).forEach(b => out.push(
    `<div class="box ${b.k === "bridge" ? "puzzle" : b.k}"><span class="bl">${esc(b.t)}</span><p>${prose(b.h)}</p></div>`));
  a.innerHTML = out.join("");
  a.scrollTop = 0;

  paintTurnBanner();
  $("cNow").textContent = idx + 1;
  document.querySelectorAll(".tick").forEach((t, n) => {
    t.classList.toggle("now", n === idx);
    t.classList.toggle("done", n < idx);
  });
  $("prev").disabled = idx === 0;
}

function myTurn() {
  const who = actorOf(idx + 1);            // whoever performs the NEXT step
  return !me || who === null || who === me;
}

function paintTurnBanner() {
  const el = $("turnBanner"), nxt = idx + 1;
  $("next").disabled = idx === STEPS.length - 1 || !myTurn();
  if (idx === STEPS.length - 1) { el.className = "turnbanner done"; el.textContent = "That's the game."; return; }
  const who = actorOf(nxt);
  if (!me) { el.className = "turnbanner"; el.textContent = "Watching — take a seat to play a side."; return; }
  if (who === null || who === me) {
    el.className = "turnbanner mine";
    el.innerHTML = `<b>Your move.</b> ${esc(STEPS[nxt].title)} <kbd>&rarr;</kbd>`;
  } else {
    el.className = "turnbanner theirs";
    el.textContent = sides[who]
      ? `Waiting for ${NAME[who]}…`
      : `${NAME[who]}'s move — nobody is sitting in that seat yet.`;
  }
}

/* ── networking ────────────────────────────────────────────────── */
function connect() {
  if (!room) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/api/mtg/ws/${room}`);

  ws.onopen = () => {
    retry = 0;
    setStatus("live");
    ws.send(JSON.stringify({ t: "hello", side: me }));
  };
  ws.onmessage = ev => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    if (m.t !== "state") return;
    sides = m.sides || {};
    peers = m.peers || 0;
    if (typeof m.step === "number" && m.step !== idx) idx = m.step;
    $("peers").textContent = peers === 1 ? "just you" : `${peers} here`;
    paint();
  };
  ws.onclose = () => {
    setStatus("offline");
    retry = Math.min(retry + 1, 6);
    setTimeout(connect, 500 * 2 ** retry);   // 1s, 2s, 4s … capped at ~32s
  };
  ws.onerror = () => ws.close();
}
function send(msg) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg)); }
function setStatus(s) {
  const el = $("status");
  el.className = "status " + s;
  el.textContent = { live: "connected", offline: "reconnecting…" }[s] || s;
}

function goto(n) {
  n = Math.max(0, Math.min(STEPS.length - 1, n));
  if (n === idx) return;
  if (n > idx && !myTurn()) return;
  idx = n; paint(); send({ t: "goto", step: idx });
}

/* ── lobby ─────────────────────────────────────────────────────── */
async function newTable() {
  const r = await fetch("/api/mtg/table", { method: "POST" });
  const { code } = await r.json();
  location.search = "?room=" + code;
}
function takeSeat(side) {
  me = side;
  try { localStorage.setItem("mtg-side-" + room, side); } catch (e) {}
  $("lobby").classList.remove("on");
  send({ t: "hello", side: me });
  paint();
}

function boot() {
  $("cAll").textContent = STEPS.length;
  const ticks = $("ticks");
  STEPS.forEach((s, i) => {
    const b = document.createElement("button");
    b.className = "tick"; b.type = "button"; b.title = `${i + 1}. ${s.title}`;
    b.setAttribute("aria-label", `Step ${i + 1}: ${s.title}`);
    b.innerHTML = "<i></i>";
    b.onclick = () => goto(i);
    ticks.appendChild(b);
  });
  $("prev").onclick = () => goto(idx - 1);
  $("next").onclick = () => goto(idx + 1);

  document.addEventListener("keydown", e => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (document.querySelector(".scrim.on")) { if (e.key === "Escape") closeSheets(); return; }
    const k = e.key;
    if (k === "ArrowRight" || k === "Right" || k === " ") { e.preventDefault(); goto(idx + 1); }
    else if (k === "ArrowLeft" || k === "Left") { e.preventDefault(); goto(idx - 1); }
    else if (k === "d" || k === "D") { e.preventDefault(); $("scrimDecks").classList.toggle("on"); }
  });
  document.querySelectorAll("[data-close]").forEach(b => b.onclick = closeSheets);
  document.querySelectorAll(".scrim").forEach(s =>
    s.addEventListener("click", e => { if (e.target === s) closeSheets(); }));

  renderDeck($("deckJones"), DECK_JONES);
  renderDeck($("deckRuel"), DECK_RUEL);

  if (!room) { $("lobby").classList.add("on"); $("lobbyNew").classList.add("on"); }
  else {
    $("roomCode").textContent = room;
    $("roomCode2").textContent = room;
    $("shareLink").value = location.origin + location.pathname + "?room=" + room;
    let saved = null;
    try { saved = localStorage.getItem("mtg-side-" + room); } catch (e) {}
    if (saved === "jones" || saved === "ruel") me = saved; else $("lobby").classList.add("on");
    connect();
  }
  paint();
}
function closeSheets() { document.querySelectorAll(".scrim").forEach(s => s.classList.remove("on")); }

function renderDeck(el, deck) {
  el.innerHTML = deck.map(([g, cards]) =>
    `<div class="grp">${esc(g)}</div>` + cards.map(([n, name]) => {
      const known = CARDS[name] ? ` data-card="${esc(name)}"` : "";
      return `<div><span class="n">${n}</span><span${known}` +
             `${known ? ' style="border-bottom:1px dotted var(--rule);cursor:help"' : ""}>${esc(name)}</span></div>`;
    }).join("")).join("");
}

document.addEventListener("DOMContentLoaded", boot);
