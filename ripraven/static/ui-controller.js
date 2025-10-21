// UIController - Manages UI elements, interactions, and visual state

const UIController = {
    // DOM Elements
    seriesSelect: null,
    chapterSelect: null,
    status: null,
    comicContainer: null,
    recentSection: null,
    recentList: null,
    chapterIndicator: null,
    downloadStatus: null,
    downloadText: null,
    progressFill: null,
    importSection: null,
    header: null,
    headerToggle: null,
    headerContent: null,

    /**
     * Initialize the UI controller
     */
    init: function() {
        this.setupElements();
        this.setupEventListeners();
        this.setupInitialState();
    },

    /**
     * Setup DOM element references
     */
    setupElements: function() {
        this.seriesSelect = document.getElementById('seriesSelect');
        this.chapterSelect = document.getElementById('chapterSelect');
        this.status = document.getElementById('status');
        this.comicContainer = document.getElementById('comicContainer');
        this.recentSection = document.getElementById('recentSection');
        this.recentList = document.getElementById('recentList');
        this.chapterIndicator = document.getElementById('chapterIndicator');
        this.downloadStatus = document.getElementById('downloadStatus');
        this.downloadText = document.getElementById('downloadText');
        this.progressFill = document.getElementById('progressFill');
        this.importSection = document.querySelector('.import-section');
        this.header = document.querySelector('.header');
        this.headerToggle = document.getElementById('headerToggle');
        this.headerContent = document.getElementById('headerContent');
    },

    /**
     * Setup event listeners
     */
    setupEventListeners: function() {
        if (this.seriesSelect) {
            this.seriesSelect.addEventListener('change', () => this.onSeriesChange());
        }

        if (this.chapterSelect) {
            this.chapterSelect.addEventListener('change', () => this.onChapterChange());
        }

        if (this.headerToggle) {
            this.headerToggle.addEventListener('click', () => this.onHeaderToggle());
        }
    },

    /**
     * Setup initial UI state
     */
    setupInitialState: function() {
        this.toggleImportSection(true);
        this.setHeaderCollapsed(false);
    },

    // Series and Chapter Management
    populateSeriesSelect: function(seriesData) {
        if (!this.seriesSelect) return;

        this.seriesSelect.innerHTML = '<option value="">Select a series...</option>';

        seriesData.forEach(series => {
            const option = document.createElement('option');
            option.value = series.name;
            option.textContent = `${series.name} (${series.chapters.length} chapters)`;
            this.seriesSelect.appendChild(option);
        });

        this.updateStatus(`Found ${seriesData.length} series`);
    },

    populateChapterSelect: function(series) {
        if (!this.chapterSelect) return;

        this.chapterSelect.disabled = false;
        this.chapterSelect.innerHTML = '<option value="">Select a chapter...</option>';

        series.chapters.forEach(chapter => {
            const option = document.createElement('option');
            option.value = chapter.name;
            const status = chapter.is_complete ? '✅' : '⚠️';
            option.textContent = `${chapter.name} ${status} (${chapter.page_count} pages)`;
            this.chapterSelect.appendChild(option);
        });

        this.updateStatus(`${series.chapters.length} chapters available`);
    },

    onSeriesChange: function() {
        const seriesName = this.seriesSelect ? this.seriesSelect.value : '';
        this.toggleImportSection(!seriesName);

        if (!seriesName) {
            if (this.chapterSelect) {
                this.chapterSelect.innerHTML = '<option value="">Select series first</option>';
                this.chapterSelect.disabled = true;
            }
            return;
        }

        const seriesData = window.RipRaven.StateManager ? window.RipRaven.StateManager.getSeriesData() : [];
        const series = seriesData.find(s => s.name === seriesName);
        if (!series) return;

        // Update state
        if (window.RipRaven.StateManager) {
            window.RipRaven.StateManager.setCurrentSeries(seriesName);
        }

        this.populateChapterSelect(series);
    },

    onChapterChange: async function() {
        const chapterName = this.chapterSelect ? this.chapterSelect.value : '';
        const currentSeries = window.RipRaven.StateManager ? window.RipRaven.StateManager.getCurrentSeries() : null;

        if (!chapterName || !currentSeries) return;

        // Update state
        if (window.RipRaven.StateManager) {
            window.RipRaven.StateManager.setCurrentChapter(chapterName);
        }

        // Update URL when chapter is manually selected
        const chapterNum = window.RipRaven.parseChapterNumber(chapterName);
        if (chapterNum && window.RipRaven.NavigationManager) {
            let method = 'push';
            const historyMode = window.RipRaven.NavigationManager.getHistoryMode();
            if (historyMode === 'replace') {
                method = 'replace';
            } else if (historyMode === 'none') {
                method = 'none';
            }
            window.RipRaven.NavigationManager.updateURL(currentSeries, chapterNum, { method });
        }

        // Set history mode to push for future interactions
        if (window.RipRaven.NavigationManager) {
            window.RipRaven.NavigationManager.setHistoryMode('push');
        }

        await this.loadChapter();
    },


    // Chapter Loading
    loadChapter: async function() {
        const currentSeries = window.RipRaven.StateManager ? window.RipRaven.StateManager.getCurrentSeries() : null;
        const currentChapter = window.RipRaven.StateManager ? window.RipRaven.StateManager.getCurrentChapter() : null;

        if (!currentSeries || !currentChapter) return;

        this.updateStatus('Loading infinite chapters...');

        if (window.RipRaven.ChapterRenderer) {
            window.RipRaven.ChapterRenderer.showLoading();
        }

        try {
            // Extract chapter number from chapter name
            const chapterNum = window.RipRaven.parseChapterNumber(currentChapter);

            if (window.RipRaven.StateManager) {
                window.RipRaven.StateManager.setCurrentStartChapter(chapterNum);
            }

            // Load infinite chapters starting from current chapter
            const data = await window.RipRaven.APIClient.loadInfiniteChapters(currentSeries, chapterNum);

            if (data.chapters.length === 0) {
                if (window.RipRaven.ChapterRenderer) {
                    window.RipRaven.ChapterRenderer.showError('No chapters found.');
                }
                return;
            }

            // Render chapters
            if (window.RipRaven.ChapterRenderer) {
                window.RipRaven.ChapterRenderer.renderInfiniteChapters(data.chapters);
            }

            // Show chapter indicator
            this.showChapterIndicator();

            // Check download status
            this.checkDownloadStatus();

            const totalPages = data.chapters.reduce((sum, ch) => sum + ch.page_count, 0);
            this.updateStatus(`Reading: ${currentSeries} - ${data.chapters.length} chapters (${totalPages} pages total)`);

        } catch (error) {
            if (window.RipRaven.ChapterRenderer) {
                window.RipRaven.ChapterRenderer.showError();
            }
            this.updateStatus('Error loading chapters');
            console.error('Error loading chapters:', error);
        }
    },

    // Recent Chapters Management
    updateRecentSection: function(recentChapters) {
        if (!recentChapters || recentChapters.length === 0) {
            if (this.recentSection) {
                this.recentSection.style.display = 'none';
            }
            return;
        }

        if (this.recentSection) {
            this.recentSection.style.display = 'block';
        }

        if (this.recentList) {
            this.recentList.innerHTML = '';

            recentChapters.forEach(recent => {
                const item = document.createElement('div');
                item.className = 'recent-item';
                const chapterNum = window.RipRaven.parseChapterNumber(recent.chapter);
                const safeChapter = chapterNum || 1;
                item.textContent = `${recent.series} · Chapter ${safeChapter}`;
                item.addEventListener('click', () => {
                    this.loadRecentChapter(recent.series, safeChapter);
                });
                this.recentList.appendChild(item);
            });
        }
    },

    loadRecentChapter: function(seriesName, chapterNum) {
        if (Number.isNaN(Number(chapterNum))) {
            console.warn('[UIController] Unable to parse chapter number:', chapterNum);
            return;
        }

        const normalizedSeries = window.RipRaven.UrlUtils.normalizeSeriesSlug(seriesName);

        if (window.RipRaven.StateManager) {
            window.RipRaven.StateManager.scheduleNavigation(normalizedSeries, Number(chapterNum), {
                historyMode: 'push',
                source: 'recent'
            });
        }
    },

    // UI State Management
    updateStatus: function(message) {
        if (this.status) {
            this.status.textContent = message;
        }
    },

    showNoChapterSelected: function() {
        this.updateStatus('Open a chapter from the RipRaven library to begin reading.');
        if (this.comicContainer) {
            this.comicContainer.innerHTML = '<div class="error">No chapter selected. Visit <a href="/ripraven">the library</a> to choose one.</div>';
        }
        if (this.chapterSelect) {
            this.chapterSelect.disabled = true;
        }
    },

    // Header Management
    toggleImportSection: function(visible) {
        if (!this.importSection) return;
        this.importSection.style.display = visible ? '' : 'none';
    },

    setHeaderCollapsed: function(collapsed) {
        if (!this.header || !this.headerToggle) return;
        this.header.classList.toggle('collapsed', collapsed);

        const label = collapsed ? 'Show Header' : 'Hide Header';
        this.headerToggle.textContent = label;
        this.headerToggle.setAttribute('aria-expanded', (!collapsed).toString());
    },

    onHeaderToggle: function() {
        if (!this.header) return;
        const shouldCollapse = !this.header.classList.contains('collapsed');
        this.setHeaderCollapsed(shouldCollapse);
    },

    // Chapter Indicator Management
    updateChapterIndicator: function(chapterNum) {
        if (this.chapterIndicator) {
            this.chapterIndicator.textContent = `Chapter ${chapterNum}`;
        }
    },

    showChapterIndicator: function() {
        if (this.chapterIndicator) {
            this.chapterIndicator.classList.remove('hidden');
        }
    },

    hideChapterIndicator: function() {
        if (this.chapterIndicator) {
            this.chapterIndicator.classList.add('hidden');
        }
    },

    // Download Status Management
    checkDownloadStatus: async function() {
        const currentSeries = window.RipRaven.StateManager ? window.RipRaven.StateManager.getCurrentSeries() : null;
        if (!currentSeries || !window.RipRaven.APIClient) return;

        try {
            const data = await window.RipRaven.APIClient.checkDownloadStatus(currentSeries);

            const activeDownloads = data.statuses.filter(status =>
                status.status === 'downloading' || status.status === 'pending'
            );

            if (activeDownloads.length > 0) {
                this.showDownloadStatus(activeDownloads);
            } else {
                this.hideDownloadStatus();
            }
        } catch (error) {
            console.error('Error checking download status:', error);
        }
    },

    showDownloadStatus: function(downloads) {
        if (this.downloadText) {
            this.downloadText.textContent = `Downloading ${downloads.length} chapters...`;
        }
        if (this.progressFill) {
            this.progressFill.style.width = '50%'; // Placeholder progress
        }
        if (this.downloadStatus) {
            this.downloadStatus.classList.remove('hidden');
        }

        // Hide after a few seconds
        setTimeout(() => this.hideDownloadStatus(), 5000);
    },

    hideDownloadStatus: function() {
        if (this.downloadStatus) {
            this.downloadStatus.classList.add('hidden');
        }
    }
};

// Export for global access
window.RipRaven.UIController = UIController;