// RipRaven Comic Reader - Refactored to use module objects

class ComicReader {
    constructor() {
        // Initialize all modules
        this.initializeModules();

        // Setup global reference for other modules to access
        window.comicReader = this;

        // Setup keyboard shortcuts
        window.RipRaven.setupKeyboardShortcuts();

        // Initialize the application
        this.initialize();
    }

    /**
     * Initialize all module objects
     */
    initializeModules() {
        // Initialize modules in dependency order
        window.RipRaven.NavigationManager.init();
        window.RipRaven.APIClient.init();
        window.RipRaven.StateManager.init();
        window.RipRaven.UIController.init();

        // Initialize chapter renderer with comic container
        const comicContainer = document.getElementById('comicContainer');
        if (comicContainer) {
            window.RipRaven.ChapterRenderer.init(comicContainer);
        }
    }

    /**
     * Initialize the application
     */
    async initialize() {
        try {
            // Load initial data
            await this.loadSeries();
            await this.loadRecent();

            // URL-based navigation is already handled by StateManager.init()
        } catch (error) {
            console.error('Error initializing ComicReader:', error);
            window.RipRaven.UIController.updateStatus('Error initializing application');
        }
    }

    /**
     * Load series data from API
     */
    async loadSeries() {
        try {
            window.RipRaven.UIController.updateStatus('Loading series...');
            const seriesData = await window.RipRaven.APIClient.loadSeries();

            // Update state and UI
            window.RipRaven.StateManager.setSeriesData(seriesData);
            window.RipRaven.UIController.populateSeriesSelect(seriesData);

        } catch (error) {
            console.error('Error loading series:', error);
            window.RipRaven.UIController.updateStatus('Error loading series');
        }
    }

    /**
     * Load recent chapters from API
     */
    async loadRecent() {
        try {
            const recentData = await window.RipRaven.APIClient.loadRecent();

            // Update state and UI
            window.RipRaven.StateManager.setRecentChapters(recentData);
            window.RipRaven.UIController.updateRecentSection(recentData);

        } catch (error) {
            console.error('Error loading recent chapters:', error);
        }
    }

    /**
     * Parse URL and navigate if needed
     */
    parseAndLoadFromURL() {
        const parsed = window.RipRaven.NavigationManager.parseFromURL();
        if (!parsed) {
            window.RipRaven.StateManager.showNoChapterSelected();
            return;
        }

        const { series, chapter } = parsed;
        const normalizedSeries = window.RipRaven.UrlUtils.normalizeSeriesSlug(series);

        // Set active series in navigation manager
        window.RipRaven.NavigationManager.setActiveSeriesSlug(series);

        // Schedule navigation through state manager
        window.RipRaven.StateManager.scheduleNavigation(normalizedSeries, chapter, {
            historyMode: 'replace',
            source: 'initial'
        });

        // Update URL
        window.RipRaven.NavigationManager.updateURL(normalizedSeries, chapter, {
            method: 'replace',
            force: true
        });
    }

    /**
     * Public method for scheduled navigation (for compatibility)
     */
    scheduleNavigation(seriesName, chapterNum, options = {}) {
        window.RipRaven.StateManager.scheduleNavigation(seriesName, chapterNum, options);
    }

    /**
     * Legacy methods for compatibility
     */

    // Method to be called when series data is available (compatibility)
    tryProcessPendingNavigation() {
        // This is now handled by StateManager
        return window.RipRaven.StateManager.tryProcessPendingNavigation();
    }

    // Method for finding series (compatibility)
    findSeries(inputName) {
        return window.RipRaven.StateManager.findSeries(inputName);
    }

    // Getters for state (compatibility)
    get currentSeries() {
        return window.RipRaven.StateManager.getCurrentSeries();
    }

    get currentChapter() {
        return window.RipRaven.StateManager.getCurrentChapter();
    }

    get seriesData() {
        return window.RipRaven.StateManager.getSeriesData();
    }

    get recentChapters() {
        return window.RipRaven.StateManager.getRecentChapters();
    }

    get chaptersData() {
        return window.RipRaven.StateManager.getChaptersData();
    }

    // Setters for state (compatibility)
    set currentSeries(value) {
        window.RipRaven.StateManager.setCurrentSeries(value);
    }

    set currentChapter(value) {
        window.RipRaven.StateManager.setCurrentChapter(value);
    }

    set seriesData(value) {
        window.RipRaven.StateManager.setSeriesData(value);
    }

    /**
     * Cleanup method
     */
    cleanup() {
        if (window.RipRaven.ChapterRenderer) {
            window.RipRaven.ChapterRenderer.cleanup();
        }
    }
}

// Initialize ComicReader when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new ComicReader();
});