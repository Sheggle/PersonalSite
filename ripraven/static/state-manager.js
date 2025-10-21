// StateManager - Manages application state and data

const StateManager = {
    // Current state
    currentSeries: null,
    currentChapter: null,
    currentDisplayChapter: null,
    currentStartChapter: null,
    maxLoadedChapter: null,
    seriesData: [],
    recentChapters: [],
    chaptersData: [],
    pendingNavigation: null,

    /**
     * Initialize the state manager
     */
    init: function() {
        // Initialize state from URL if available
        this.initializeFromURL();
    },

    /**
     * Initialize state from current URL
     */
    initializeFromURL: function() {
        const parsed = window.RipRaven.NavigationManager ? window.RipRaven.NavigationManager.parseFromURL() : null;
        if (parsed) {
            const normalizedSeries = window.RipRaven.UrlUtils.normalizeSeriesSlug(parsed.series);
            this.scheduleNavigation(normalizedSeries, parsed.chapter, { historyMode: 'replace', source: 'initial' });
        }
    },

    // Series Management
    getCurrentSeries: function() {
        return this.currentSeries;
    },

    setCurrentSeries: function(series) {
        this.currentSeries = series;
        if (window.RipRaven.NavigationManager) {
            window.RipRaven.NavigationManager.setActiveSeriesSlug(series);
        }
    },

    getSeriesData: function() {
        return this.seriesData;
    },

    setSeriesData: function(data) {
        this.seriesData = data;
        // Process any pending navigation
        this.tryProcessPendingNavigation();
    },

    findSeries: function(inputName) {
        if (!Array.isArray(this.seriesData) || this.seriesData.length === 0) {
            return null;
        }

        const directMatch = this.seriesData.find(series => series.name === inputName);
        if (directMatch) {
            return directMatch;
        }

        const normalized = window.RipRaven.UrlUtils.normalizeSeriesSlug(inputName);
        const normalizedMatch = this.seriesData.find(series => series.name === normalized);
        if (normalizedMatch) {
            return normalizedMatch;
        }

        const lower = inputName.toLowerCase();
        const exactLower = this.seriesData.find(series => series.name.toLowerCase() === lower);
        if (exactLower) {
            return exactLower;
        }

        const normalizedLower = normalized.toLowerCase();
        return this.seriesData.find(series => series.name.toLowerCase() === normalizedLower) || null;
    },

    // Chapter Management
    getCurrentChapter: function() {
        return this.currentChapter;
    },

    setCurrentChapter: function(chapter) {
        this.currentChapter = chapter;
    },

    getCurrentDisplayChapter: function() {
        return this.currentDisplayChapter;
    },

    setCurrentDisplayChapter: function(chapter) {
        this.currentDisplayChapter = chapter;
    },

    getCurrentStartChapter: function() {
        return this.currentStartChapter;
    },

    setCurrentStartChapter: function(chapter) {
        this.currentStartChapter = chapter;
    },

    getMaxLoadedChapter: function() {
        return this.maxLoadedChapter;
    },

    setMaxLoadedChapter: function(chapter) {
        this.maxLoadedChapter = chapter;
    },

    getChaptersData: function() {
        return this.chaptersData;
    },

    setChaptersData: function(data) {
        this.chaptersData = data;
    },

    appendChaptersData: function(newChapters) {
        this.chaptersData = this.chaptersData.concat(newChapters);
    },

    // Recent Chapters Management
    getRecentChapters: function() {
        return this.recentChapters;
    },

    setRecentChapters: function(chapters) {
        this.recentChapters = chapters;
    },

    // Navigation Management
    scheduleNavigation: function(seriesName, chapterNum, options = {}) {
        if (!seriesName || Number.isNaN(Number(chapterNum))) {
            console.warn('[StateManager] Invalid navigation request:', seriesName, chapterNum);
            return;
        }

        const numericChapter = Number(chapterNum);
        this.pendingNavigation = {
            requestedSeries: seriesName,
            requestedChapter: numericChapter,
            options: options || {}
        };

        // Update navigation manager
        if (window.RipRaven.NavigationManager) {
            window.RipRaven.NavigationManager.setActiveSeriesSlug(seriesName);
        }

        this.tryProcessPendingNavigation();
    },

    tryProcessPendingNavigation: function() {
        if (!this.pendingNavigation) {
            return;
        }

        if (!Array.isArray(this.seriesData) || this.seriesData.length === 0) {
            return;
        }

        const { requestedSeries, requestedChapter, options } = this.pendingNavigation;
        const seriesInfo = this.findSeries(requestedSeries);

        if (!seriesInfo) {
            console.warn('[StateManager] Series not found:', requestedSeries);
            this.pendingNavigation = null;
            return;
        }

        const chapterName = `chapter_${requestedChapter}`;
        const chapterExists = Array.isArray(seriesInfo.chapters) && seriesInfo.chapters.some(ch => ch.name === chapterName);

        if (!chapterExists) {
            console.warn('[StateManager] Chapter not found:', requestedSeries, chapterName);
            this.pendingNavigation = null;
            return;
        }

        // Update navigation manager
        if (window.RipRaven.NavigationManager) {
            window.RipRaven.NavigationManager.setHistoryMode(options.historyMode || 'replace');
        }

        // Update state directly and trigger UI updates
        this.setCurrentSeries(seriesInfo.name);
        this.setCurrentChapter(chapterName);

        // Notify UI controller about navigation (avoid circular calls)
        if (window.RipRaven.UIController) {
            // Set the select values directly without triggering events
            const seriesSelect = document.getElementById('seriesSelect');
            const chapterSelect = document.getElementById('chapterSelect');

            if (seriesSelect) {
                seriesSelect.value = seriesInfo.name;
            }

            // Populate chapter options
            window.RipRaven.UIController.populateChapterSelect(seriesInfo);

            if (chapterSelect) {
                chapterSelect.value = chapterName;
            }

            // Load the chapter
            window.RipRaven.UIController.loadChapter();
        }

        this.pendingNavigation = null;
    },

    getPendingNavigation: function() {
        return this.pendingNavigation;
    },

    clearPendingNavigation: function() {
        this.pendingNavigation = null;
    },

    // Utility Methods
    showNoChapterSelected: function() {
        if (window.RipRaven.UIController) {
            window.RipRaven.UIController.showNoChapterSelected();
        }
    },

    /**
     * Reset all state to initial values
     */
    reset: function() {
        this.currentSeries = null;
        this.currentChapter = null;
        this.currentDisplayChapter = null;
        this.currentStartChapter = null;
        this.maxLoadedChapter = null;
        this.seriesData = [];
        this.recentChapters = [];
        this.chaptersData = [];
        this.pendingNavigation = null;
    },

    /**
     * Get current state snapshot for debugging
     */
    getStateSnapshot: function() {
        return {
            currentSeries: this.currentSeries,
            currentChapter: this.currentChapter,
            currentDisplayChapter: this.currentDisplayChapter,
            currentStartChapter: this.currentStartChapter,
            maxLoadedChapter: this.maxLoadedChapter,
            seriesCount: this.seriesData.length,
            recentCount: this.recentChapters.length,
            chaptersDataCount: this.chaptersData.length,
            hasPendingNavigation: !!this.pendingNavigation
        };
    }
};

// Export for global access
window.RipRaven.StateManager = StateManager;