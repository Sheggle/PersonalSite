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
        const path = window.location.pathname;
        if (path.startsWith('/api/ripraven') && !path.endsWith('.html')) {
            const suffix = path.slice('/api/ripraven'.length);
            const canonicalPath = `/ripraven${suffix}`;
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
        const encodedSeries = seriesName ? encodeURIComponent(seriesName) : '';
        let targetPath = this.displayBase;
        if (encodedSeries) {
            targetPath += `/${encodedSeries}`;
        }
        if (seriesName && chapterNum) {
            targetPath += `?chapter=${chapterNum}`;
        }

        const state = (seriesName && chapterNum) ? { series: seriesName, chapter: chapterNum } : {};

        if (method === 'push') {
            history.pushState(state, '', targetPath);
        } else {
            history.replaceState(state, '', targetPath);
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