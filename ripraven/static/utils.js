// RipRaven Utilities - Shared functions across components

/**
 * API Base URL Detection
 */
function getApiBaseUrl() {
    return '/api/ripraven';
}

/**
 * Display Base URL Detection
 */
function getDisplayBaseUrl() {
    return '/ripraven';
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
     * Handles fractional chapters like 1.1, 1.2, etc.
     */
    parseSeriesChapterFromURL: function() {
        const url = new URL(window.location.href);
        const parts = url.pathname.split('/').filter(Boolean);
        const seriesSlug = parts.length >= 2 ? decodeURIComponent(parts[1]) : null;
        const chapterParam = url.searchParams.get('chapter');

        if (!seriesSlug || !chapterParam) {
            return null;
        }

        // Parse as float to handle fractional chapters (1.1, 1.2, etc.)
        const chapterNum = parseFloat(chapterParam);
        if (!Number.isFinite(chapterNum) || chapterNum <= 0) {
            return null;
        }

        // Return as string to preserve fractional notation
        return { series: seriesSlug, chapter: chapterParam };
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
 * Returns string to support fractional chapters (1.1, 1.2, etc.)
 */
function parseChapterNumber(chapterName) {
    if (!chapterName) return null;
    // Remove 'chapter_' prefix and return as string
    const chapterNum = String(chapterName).replace('chapter_', '');
    // Validate it's a valid number (integer or decimal)
    const parsed = parseFloat(chapterNum);
    return Number.isFinite(parsed) && parsed > 0 ? chapterNum : null;
}

// Export utilities for global access
window.RipRaven = {
    getApiBaseUrl,
    getDisplayBaseUrl,
    UrlUtils,
    setupKeyboardShortcuts,
    parseChapterNumber
};