// RipRaven Utilities - Shared functions across components

/**
 * API Base URL Detection
 * Detects the correct API base URL for mounted vs standalone scenarios
 */
function getApiBaseUrl() {
    const rawPath = window.location.pathname.replace(/\/$/, '');
    const apiMatch = rawPath.match(/^(.*?\/api\/ripraven)(?:\/.*)?$/);
    const resolvedApiBase = (apiMatch ? apiMatch[1] : '') || '/api/ripraven';
    return resolvedApiBase.replace(/\/{2,}/g, '/').replace(/\/$/, '');
}

/**
 * Display Base URL Detection
 * Gets the canonical display base for URL routing
 */
function getDisplayBaseUrl() {
    const rawPath = window.location.pathname.replace(/\/$/, '');
    const displayMatch = rawPath.match(/^(.*?\/ripraven)(?:\/.*)?$/);
    const canonicalDisplayBase = '/ripraven';
    return displayMatch ? displayMatch[1] : canonicalDisplayBase;
}

/**
 * URL Encoding Helpers
 */
const UrlUtils = {
    /**
     * Normalize series slug by replacing spaces/dashes with underscores
     */
    normalizeSeriesSlug: function(value) {
        if (!value) return value;
        return value.replace(/[\s-]+/g, '_');
    },

    /**
     * Parse series and chapter from current URL
     */
    parseSeriesChapterFromURL: function() {
        const url = new URL(window.location.href);
        const parts = url.pathname.replace(/\/$/, '').split('/').filter(Boolean);
        const seriesSlug = parts.length >= 2 ? decodeURIComponent(parts[1]) : null;
        let chapterParam = parseInt(url.searchParams.get('chapter'), 10);

        if (!seriesSlug) {
            return null;
        }

        if (!Number.isFinite(chapterParam) || chapterParam <= 0) {
            // Backwards compatibility: allow /ripraven/<series>/<chapter>
            if (parts.length >= 3 && /^\d+$/.test(parts[2])) {
                chapterParam = parseInt(parts[2], 10);
            } else {
                return null;
            }
        }

        return { series: seriesSlug, chapter: chapterParam };
    },

    /**
     * Update browser URL and history
     */
    updateURL: function(seriesName, chapterNum, options = {}) {
        const method = options.method || 'replace';
        const force = Boolean(options.force);
        const baseRoot = '/ripraven';
        const slugSource = seriesName || (chapterNum ? seriesName : null);
        const encodedSeries = slugSource ? encodeURIComponent(slugSource) : '';
        let targetPath = baseRoot;
        if (encodedSeries) {
            targetPath += `/${encodedSeries}`;
        }
        if (seriesName && chapterNum) {
            targetPath += `?chapter=${chapterNum}`;
        }

        const currentPath = window.location.pathname.replace(/\/$/, '') || '/';
        const currentWithQuery = currentPath + window.location.search;
        const pathsDiffer = currentWithQuery !== targetPath;
        const state = (seriesName && chapterNum)
            ? { series: seriesName, chapter: chapterNum }
            : {};

        if (method === 'none') {
            UrlUtils.updateDocumentTitle(seriesName, chapterNum);
            return;
        }

        if (method === 'push') {
            if (pathsDiffer || force) {
                history.pushState(state, '', targetPath);
            } else {
                history.replaceState(state, '', targetPath);
            }
        } else {
            if (pathsDiffer || force) {
                history.replaceState(state, '', targetPath);
            } else if (seriesName && chapterNum) {
                history.replaceState(state, '', targetPath);
            }
        }

        UrlUtils.updateDocumentTitle(seriesName, chapterNum);
    },

    /**
     * Update document title based on current series/chapter
     */
    updateDocumentTitle: function(seriesName, chapterNum) {
        if (seriesName && chapterNum) {
            document.title = `${seriesName} · Chapter ${chapterNum} | RipRaven`;
        } else {
            document.title = 'RipRaven Comic Reader';
        }
    }
};

/**
 * DOM Manipulation Helpers
 */
const DOMUtils = {
    /**
     * Update loading message in an element
     */
    updateLoadingMessage: function(elementId, message) {
        const element = document.getElementById(elementId);
        if (element) {
            element.innerHTML = message;
        }
    },

    /**
     * Hide element by ID
     */
    hideElement: function(elementId) {
        const element = document.getElementById(elementId);
        if (element) {
            element.style.display = 'none';
        }
    },

    /**
     * Show element by ID
     */
    showElement: function(elementId) {
        const element = document.getElementById(elementId);
        if (element) {
            element.style.display = '';
        }
    },

    /**
     * Toggle class on element
     */
    toggleClass: function(element, className, condition) {
        if (element) {
            element.classList.toggle(className, condition);
        }
    }
};

/**
 * API Client Helpers
 */
const APIUtils = {
    /**
     * Make a GET request to the RipRaven API
     */
    get: async function(endpoint) {
        const apiBase = window.RipRaven.getApiBaseUrl();
        const response = await fetch(`${apiBase}${endpoint}`);
        if (!response.ok) {
            throw new Error(`API request failed: ${response.status}`);
        }
        return response.json();
    },

    /**
     * Make a POST request to the RipRaven API
     */
    post: async function(endpoint, data) {
        const apiBase = window.RipRaven.getApiBaseUrl();
        const response = await fetch(`${apiBase}${endpoint}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            throw new Error(`API request failed: ${response.status}`);
        }
        return response.json();
    }
};

/**
 * Import manga function - extracted from reader template
 */
async function importManga() {
    const urlInput = document.getElementById('mangaUrl');
    const importBtn = document.getElementById('importBtn');
    const importStatus = document.getElementById('importStatus');

    const url = urlInput.value.trim();

    if (!url) {
        importStatus.textContent = 'Please enter a RavenScans URL';
        importStatus.style.color = '#ff6b6b';
        return;
    }

    // Basic URL validation
    if (!url.includes('ravenscans.com')) {
        importStatus.textContent = 'Please enter a valid RavenScans URL';
        importStatus.style.color = '#ff6b6b';
        return;
    }

    // Disable button and show loading state
    importBtn.disabled = true;
    importBtn.textContent = 'Importing...';
    importStatus.textContent = 'Extracting manga information...';
    importStatus.style.color = '#cccccc';

    const apiBase = getApiBaseUrl();

    try {
        const response = await fetch(`${apiBase}/import-manga`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url: url })
        });

        const result = await response.json();

        if (response.ok) {
            importStatus.textContent = `✅ Successfully imported: ${result.series} - Chapter ${result.chapter}`;
            importStatus.style.color = '#4caf50';
            urlInput.value = '';

            // Refresh the series list to show the new manga
            window.location.reload();
        } else {
            importStatus.textContent = `❌ Error: ${result.detail || 'Import failed'}`;
            importStatus.style.color = '#ff6b6b';
        }
    } catch (error) {
        importStatus.textContent = `❌ Network error: ${error.message}`;
        importStatus.style.color = '#ff6b6b';
    } finally {
        // Re-enable button
        importBtn.disabled = false;
        importBtn.textContent = 'Import';
    }
}

/**
 * Keyboard shortcuts handler
 */
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        switch(e.key) {
            case 'ArrowUp':
            case 'k':
                window.scrollBy(0, -100);
                e.preventDefault();
                break;
            case 'ArrowDown':
            case 'j':
                window.scrollBy(0, 100);
                e.preventDefault();
                break;
            case ' ':
                window.scrollBy(0, window.innerHeight * 0.8);
                e.preventDefault();
                break;
            case 'Home':
                window.scrollTo(0, 0);
                e.preventDefault();
                break;
            case 'End':
                window.scrollTo(0, document.body.scrollHeight);
                e.preventDefault();
                break;
        }
    });
}

/**
 * Utility to parse chapter number from chapter name
 */
function parseChapterNumber(chapterName) {
    if (!chapterName) return null;
    const chapterNum = parseInt(String(chapterName).replace('chapter_', ''), 10);
    return Number.isFinite(chapterNum) ? chapterNum : null;
}

// Export utilities for global access
window.RipRaven = {
    getApiBaseUrl,
    getDisplayBaseUrl,
    UrlUtils,
    DOMUtils,
    APIUtils,
    importManga,
    setupKeyboardShortcuts,
    parseChapterNumber
};