"""Clear RavenScans' interactive Cloudflare challenge with a real Chrome.

The clearance cookie is usable by the regular httpx client afterwards, so the
browser and its virtual display only live for the duration of one challenge.
"""

import asyncio
import os
import shutil
import time
from typing import List, Tuple

from patchright.async_api import async_playwright

CHALLENGE_TIMEOUT_S = 90


async def _start_xvfb() -> Tuple[asyncio.subprocess.Process, str]:
    """Start Xvfb on a free display and wait until it is ready."""
    read_fd, write_fd = os.pipe()
    try:
        process = await asyncio.create_subprocess_exec(
            'Xvfb', '-displayfd', str(write_fd),
            '-screen', '0', '1280x720x24', '-nolisten', 'tcp',
            pass_fds=(write_fd,),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except Exception:
        os.close(read_fd)
        os.close(write_fd)
        raise
    os.close(write_fd)
    try:
        display = await asyncio.wait_for(
            asyncio.to_thread(os.read, read_fd, 32), timeout=10,
        )
    except Exception:
        if process.returncode is None:
            process.terminate()
        await process.wait()
        raise
    finally:
        os.close(read_fd)
    if not display:
        await process.wait()
        raise RuntimeError('Xvfb exited before providing a display')
    return process, f":{display.decode().strip()}"


async def _stop_xvfb(process: asyncio.subprocess.Process):
    if process.returncode is None:
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


async def _wait_out_challenge(page):
    """Let managed challenges clear themselves; click Turnstile if asked."""
    deadline = time.monotonic() + CHALLENGE_TIMEOUT_S
    next_click = time.monotonic() + 5
    while 'Just a moment' in await page.title():
        if time.monotonic() >= deadline:
            raise RuntimeError('Cloudflare challenge did not clear')
        if time.monotonic() >= next_click:
            for frame in page.frames:
                if 'challenges.cloudflare.com' not in frame.url:
                    continue
                try:
                    checkbox = frame.locator('input[type=checkbox]')
                    if await checkbox.count() and await checkbox.first.is_visible():
                        await checkbox.first.click(timeout=3000)
                        next_click = time.monotonic() + 10
                except Exception:
                    # The frame is replaced while the challenge runs. The next
                    # pass sees its new state; a failed click is not fatal.
                    pass
        await page.wait_for_timeout(500)


async def fetch_with_clearance(url: str, navigation_timeout_s: int) -> Tuple[str, str, List[dict]]:
    """Return the requested HTML plus the session httpx should reuse."""
    chrome = next((path for name in ('google-chrome', 'chromium', 'chromium-browser')
                   if (path := shutil.which(name))), None)
    if chrome is None:
        raise RuntimeError('Cloudflare clearance needs google-chrome or chromium')
    if shutil.which('Xvfb') is None:
        raise RuntimeError('Cloudflare clearance needs Xvfb')

    xvfb = playwright = browser = None
    try:
        xvfb, display = await _start_xvfb()
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            executable_path=chrome,
            headless=False,
            env={**os.environ, 'DISPLAY': display},
        )
        context = await browser.new_context(viewport={'width': 1365, 'height': 768})
        page = await context.new_page()
        await page.goto(url, wait_until='domcontentloaded',
                        timeout=navigation_timeout_s * 1000)
        await _wait_out_challenge(page)
        html = await page.content()
        user_agent = await page.evaluate('navigator.userAgent')
        cookies = [
            cookie for cookie in await context.cookies()
            if cookie['domain'] == 'ravenscans.org'
            or cookie['domain'].endswith('.ravenscans.org')
        ]
        return html, user_agent, cookies
    finally:
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()
        if xvfb is not None:
            await _stop_xvfb(xvfb)
