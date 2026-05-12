// ==UserScript==
// @name         ripraven catch-up
// @namespace    https://sheggle.com/ripraven
// @version      0.1.0
// @description  Browser-side downloader for ripraven (sheggle.com). Runs on any ravenscans.org page and feeds the local library while Cloudflare blocks the server.
// @match        https://ravenscans.org/*
// @run-at       document-idle
// @grant        GM_xmlhttpRequest
// @connect      sheggle.com
// @connect      ravenscans.org
// @connect      cdn1.ravenscans.org
// @connect      cdn2.ravenscans.org
// @connect      cdn3.ravenscans.org
// @connect      cdn4.ravenscans.org
// @updateURL    https://sheggle.com/api/ripraven/static/ripraven.user.js
// @downloadURL  https://sheggle.com/api/ripraven/static/ripraven.user.js
// ==/UserScript==

(function () {
    'use strict';

    // Only run in the top frame — same-origin iframes injected by the page
    // would otherwise duplicate the loop.
    if (window.top !== window.self) return;

    const SHEGGLE = 'https://sheggle.com';
    const QUEUE_POLL_IDLE_MS = 60_000;
    const QUEUE_POLL_ERROR_MS = 10_000;
    const PER_IMAGE_DELAY_MS = 200;

    // ---- GM_xmlhttpRequest helpers ------------------------------------------

    function gmRequest(opts) {
        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                ...opts,
                onload: r => {
                    if (r.status >= 200 && r.status < 300) resolve(r);
                    else reject(new Error(`HTTP ${r.status} ${opts.url}`));
                },
                onerror: e => reject(new Error(`network error ${opts.url}: ${e && e.error}`)),
                ontimeout: () => reject(new Error(`timeout ${opts.url}`)),
            });
        });
    }

    async function getJson(url) {
        const r = await gmRequest({ method: 'GET', url, responseType: 'json', headers: { Accept: 'application/json' } });
        return r.response;
    }

    async function postJson(url, body) {
        const r = await gmRequest({
            method: 'POST',
            url,
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            data: JSON.stringify(body),
            responseType: 'json',
        });
        return r.response;
    }

    async function getText(url) {
        const r = await gmRequest({ method: 'GET', url, responseType: 'text' });
        return r.responseText;
    }

    async function getBlob(url) {
        const r = await gmRequest({ method: 'GET', url, responseType: 'blob', timeout: 60_000 });
        return r.response;
    }

    async function postForm(url, formData) {
        const r = await gmRequest({
            method: 'POST',
            url,
            data: formData,
            responseType: 'json',
            timeout: 300_000,
        });
        return r.response;
    }

    // ---- overlay UI ---------------------------------------------------------

    const overlay = (() => {
        const el = document.createElement('div');
        el.id = 'ripraven-overlay';
        el.style.cssText = `
            position: fixed; right: 12px; bottom: 12px; z-index: 2147483647;
            background: rgba(13, 17, 23, 0.92); color: #e6edf3;
            font: 12px/1.4 system-ui, sans-serif;
            padding: 8px 12px; border-radius: 8px;
            border: 1px solid #30363d;
            max-width: 320px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
            pointer-events: auto;
        `;
        el.innerHTML = `
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                <span style="font-weight:600;color:#79c0ff;">🦅 ripraven</span>
                <span id="ripraven-status" style="opacity:.7;">starting…</span>
            </div>
            <div id="ripraven-detail" style="opacity:.7;font-size:11px;"></div>
        `;
        document.body.appendChild(el);
        return el;
    })();

    function setStatus(status, detail) {
        const s = document.getElementById('ripraven-status');
        const d = document.getElementById('ripraven-detail');
        if (s) s.textContent = status;
        if (d) d.textContent = detail || '';
    }

    // ---- work handlers ------------------------------------------------------

    function sortByTrailingNumber(urls) {
        const numOf = u => {
            const m = u.match(/\/(\d+)\.[a-z]+$/i);
            return m ? parseInt(m[1], 10) : 999999;
        };
        return [...urls].sort((a, b) => numOf(a) - numOf(b));
    }

    function extName(url) {
        const m = url.match(/\.([a-z]+)(?:\?|$)/i);
        return m ? m[1].toLowerCase() : 'jpg';
    }

    function basename(url) {
        const m = url.match(/\/([^/]+)$/);
        return m ? m[1].split('?')[0] : null;
    }

    async function handleChapterList(item) {
        setStatus(`scraping chapter list`, item.series_slug);
        const html = await getText(item.series_url);

        // ravenscans links chapters like /series-name-chapter-10/ or /...-chapter-1-1/
        const re = /href="(https?:\/\/ravenscans\.org\/[^"]*?-chapter-(\d+(?:-\d+)?)[^"]*?)"/g;
        const seen = new Set();
        const chapters = [];
        let m;
        while ((m = re.exec(html)) !== null) {
            const num = m[2].replace('-', '.');
            if (seen.has(num)) continue;
            seen.add(num);
            chapters.push({ number: num, url: m[1] });
        }
        if (!chapters.length) throw new Error('no chapter links on series page');

        await postJson(`${SHEGGLE}/api/ripraven/series/${item.series_slug}/chapter-list`, {
            series_name: item.series_name,
            series_url: item.series_url,
            chapters,
        });
        setStatus(`uploaded ${chapters.length} chapters`, item.series_slug);
    }

    async function handleChapter(item) {
        setStatus(`fetching ch ${item.chapter_num}`, item.series_slug);
        const html = await getText(item.chapter_url);

        const imgRe = /https:\/\/cdn\d+\.ravenscans\.org\/[^"'\s)>]+\.(?:jpg|jpeg|png|webp)/gi;
        const urls = sortByTrailingNumber(Array.from(new Set(html.match(imgRe) || [])));
        if (!urls.length) throw new Error(`no image urls in chapter ${item.chapter_num}`);

        const form = new FormData();
        if (item.claim_token) form.append('claim_token', item.claim_token);

        for (let i = 0; i < urls.length; i++) {
            setStatus(`fetching ch ${item.chapter_num}`, `${i + 1}/${urls.length} ${item.series_slug}`);
            const blob = await getBlob(urls[i]);
            const fname = basename(urls[i]) || `${String(i).padStart(3, '0')}.${extName(urls[i])}`;
            form.append('pages', blob, fname);
            if (PER_IMAGE_DELAY_MS) await sleep(PER_IMAGE_DELAY_MS);
        }

        setStatus(`uploading ch ${item.chapter_num}`, `${urls.length} pages → ${item.series_slug}`);
        await postForm(
            `${SHEGGLE}/api/ripraven/series/${item.series_slug}/chapters/${item.chapter_num}/pages`,
            form,
        );
    }

    function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

    // ---- main loop ----------------------------------------------------------

    async function tick() {
        let queue;
        try {
            queue = await getJson(`${SHEGGLE}/api/ripraven/queue?limit=1`);
        } catch (err) {
            console.error('[ripraven] queue fetch failed', err);
            setStatus('queue fetch failed', String(err.message || err));
            return QUEUE_POLL_ERROR_MS;
        }

        const items = (queue && queue.items) || [];
        if (!items.length) {
            setStatus('idle', 'no work pending');
            return QUEUE_POLL_IDLE_MS;
        }

        const item = items[0];
        try {
            if (item.type === 'chapter-list') await handleChapterList(item);
            else if (item.type === 'chapter') await handleChapter(item);
            else throw new Error(`unknown item type ${item.type}`);
            return 1_000;  // immediately go again
        } catch (err) {
            console.error('[ripraven] work item failed', item, err);
            setStatus('error', String(err.message || err));
            if (item.claim_token) {
                try {
                    await postJson(`${SHEGGLE}/api/ripraven/queue/release`, { claim_token: item.claim_token });
                } catch (e) { /* server will TTL it */ }
            }
            return QUEUE_POLL_ERROR_MS;
        }
    }

    (async function loop() {
        // give the page a moment to render so the overlay slots in cleanly
        await sleep(500);
        while (true) {
            const delay = await tick();
            await sleep(delay);
        }
    })();
})();
