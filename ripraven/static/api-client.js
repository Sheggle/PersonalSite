// APIClient - Handles all fetch operations and API communication

const APIClient = {
    // Internal state
    apiBase: '',

    /**
     * Initialize the API client
     */
    init: function() {
        this.apiBase = window.RipRaven.getApiBaseUrl();
    },

    /**
     * Load all available series
     */
    loadSeries: async function() {
        try {
            const response = await fetch(`${this.apiBase}/series`);
            if (!response.ok) {
                throw new Error(`Failed to load series: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('Error loading series:', error);
            throw error;
        }
    },

    /**
     * Load recent chapters
     */
    loadRecent: async function() {
        try {
            const response = await fetch(`${this.apiBase}/recent`);
            if (!response.ok) {
                throw new Error(`Failed to load recent chapters: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('Error loading recent chapters:', error);
            throw error;
        }
    },

    /**
     * Load infinite chapters starting from a specific chapter
     */
    loadInfiniteChapters: async function(seriesName, startingChapter) {
        try {
            const response = await fetch(`${this.apiBase}/infinite-chapters/${seriesName}/${startingChapter}`);
            if (!response.ok) {
                throw new Error(`Failed to load chapters: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('Error loading chapters:', error);
            throw error;
        }
    },

    /**
     * Save recent chapter to reading history
     */
    saveRecentChapter: async function(seriesName, chapterName) {
        try {
            const chapterNum = window.RipRaven.parseChapterNumber(chapterName);
            const response = await fetch(`${this.apiBase}/recent`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    series: seriesName,
                    chapter: chapterName,
                    last_read: new Date().toISOString(),
                    page_position: 0
                })
            });

            if (!response.ok) {
                throw new Error(`Failed to save recent chapter: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('Error saving recent chapter:', error);
            throw error;
        }
    },

    /**
     * Check download status for a series
     */
    checkDownloadStatus: async function(seriesName) {
        try {
            const response = await fetch(`${this.apiBase}/download-status/${seriesName}`);
            if (!response.ok) {
                throw new Error(`Failed to check download status: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('Error checking download status:', error);
            throw error;
        }
    },

    /**
     * Import manga from URL
     */
    importManga: async function(mangaUrl) {
        try {
            const response = await fetch(`${this.apiBase}/import-manga`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: mangaUrl })
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || 'Import failed');
            }

            return result;
        } catch (error) {
            console.error('Error importing manga:', error);
            throw error;
        }
    },

    /**
     * Generic GET request helper
     */
    get: async function(endpoint) {
        try {
            const response = await fetch(`${this.apiBase}${endpoint}`);
            if (!response.ok) {
                throw new Error(`API request failed: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error(`Error with GET ${endpoint}:`, error);
            throw error;
        }
    },

    /**
     * Generic POST request helper
     */
    post: async function(endpoint, data) {
        try {
            const response = await fetch(`${this.apiBase}${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            });

            if (!response.ok) {
                throw new Error(`API request failed: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`Error with POST ${endpoint}:`, error);
            throw error;
        }
    },

    /**
     * Get the API base URL
     */
    getApiBase: function() {
        return this.apiBase;
    }
};

// Export for global access
window.RipRaven.APIClient = APIClient;