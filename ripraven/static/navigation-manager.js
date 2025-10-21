// NavigationManager - Handles URL parsing, history, and routing

const NavigationManager = {
    // Internal state
    historyMode: 'push',
    displayBase: '/ripraven',
    activeSeriesSlug: null,

    /**
     * Initialize the navigation manager
     */
    init: function() {
        this.displayBase = window.RipRaven.getDisplayBaseUrl();
        window.addEventListener('popstate', () => this.onPopState());
        this.canonicalizePath();
    },

    /**
     * Canonicalize the current path if needed
     */
    canonicalizePath: function() {
        const rawPath = window.location.pathname.replace(/\/$/, '');
        const apiMatch = rawPath.match(/^(.*?\/api\/ripraven)(?:\/.*)?$/);
        const displayMatch = rawPath.match(/^(.*?\/ripraven)(?:\/.*)?$/);

        if (!displayMatch && apiMatch && !rawPath.endsWith('.html')) {
            const suffix = rawPath.slice(apiMatch[1].length) || '';
            const canonicalPath = `${this.displayBase}${suffix}` || this.displayBase;
            history.replaceState(history.state ?? {}, '', canonicalPath);
        }
    },

    /**
     * Parse series and chapter from current URL
     */
    parseFromURL: function() {
        return window.RipRaven.UrlUtils.parseSeriesChapterFromURL();
    },

    /**
     * Update browser URL and history
     */
    updateURL: function(seriesName, chapterNum, options = {}) {
        const method = options.method || 'replace';
        const force = Boolean(options.force);
        const baseRoot = this.displayBase;
        const slugSource = seriesName || (chapterNum ? this.activeSeriesSlug : null);
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
            this.updateDocumentTitle(seriesName, chapterNum);
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

        this.updateDocumentTitle(seriesName, chapterNum);
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
    },

    /**
     * Handle browser back/forward navigation
     */
    onPopState: function() {
        const parsed = this.parseFromURL();
        if (parsed) {
            const normalizedSeries = window.RipRaven.UrlUtils.normalizeSeriesSlug(parsed.series);
            // Directly call StateManager to avoid circular dependencies
            if (window.RipRaven.StateManager) {
                window.RipRaven.StateManager.scheduleNavigation(normalizedSeries, parsed.chapter, {
                    historyMode: 'replace',
                    source: 'popstate-path'
                });
            }
        } else {
            window.location.replace('/ripraven');
        }
    },

    /**
     * Set the current history mode
     */
    setHistoryMode: function(mode) {
        this.historyMode = mode;
    },

    /**
     * Get the current history mode
     */
    getHistoryMode: function() {
        return this.historyMode;
    },

    /**
     * Set the active series slug
     */
    setActiveSeriesSlug: function(slug) {
        this.activeSeriesSlug = slug;
    },

    /**
     * Get the active series slug
     */
    getActiveSeriesSlug: function() {
        return this.activeSeriesSlug;
    }
};

// Export for global access
window.RipRaven.NavigationManager = NavigationManager;