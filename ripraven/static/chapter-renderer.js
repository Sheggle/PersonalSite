// ChapterRenderer - Handles DOM manipulation, infinite scroll, and chapter rendering

/**
 * Compare two chapter numbers (handles fractional chapters like 1.1, 1.2).
 * Returns: negative if a < b, positive if a > b, 0 if equal.
 */
function compareChapterNumbers(a, b) {
    const partsA = String(a).split('.').map(Number);
    const partsB = String(b).split('.').map(Number);

    // Compare major version
    if (partsA[0] !== partsB[0]) {
        return partsA[0] - partsB[0];
    }
    // Compare minor version (default to 0 if not present)
    const minorA = partsA[1] || 0;
    const minorB = partsB[1] || 0;
    return minorA - minorB;
}

const ChapterRenderer = {
    // Internal state
    comicContainer: null,
    chapterObserver: null,
    isInitialSetup: false,
    chapterBoundaries: [],
    isLoadingNextChapters: false,

    /**
     * Initialize the chapter renderer
     */
    init: function(comicContainer) {
        this.comicContainer = comicContainer;
        this.setupScrollTracking();
    },

    /**
     * Setup intersection observer for scroll tracking
     */
    setupScrollTracking: function() {
        this.chapterObserver = new IntersectionObserver((entries) => {
            // During initial setup, ignore intersection events for a short period
            if (this.isInitialSetup) {
                return;
            }

            entries.forEach(entry => {
                // Keep as string to support fractional chapters (1.1, 1.2, etc.)
                const chapterNum = entry.target.dataset.chapterNum;

                if (entry.isIntersecting && chapterNum) {
                    const chapterName = `chapter_${chapterNum}`;

                    // Notify state manager about chapter change
                    if (window.RipRaven.StateManager) {
                        window.RipRaven.StateManager.setCurrentDisplayChapter(chapterNum);
                        window.RipRaven.StateManager.setCurrentChapter(chapterName);
                    }

                    // Update URL and save progress
                    if (window.RipRaven.NavigationManager && window.RipRaven.StateManager) {
                        const currentSeries = window.RipRaven.StateManager.currentSeries;
                        window.RipRaven.NavigationManager.updateURL(currentSeries, chapterNum, { method: 'replace' });
                    }

                    // Update chapter indicator
                    if (window.RipRaven.UIController) {
                        window.RipRaven.UIController.updateChapterIndicator(chapterNum);
                    }

                    // Save reading progress
                    this.saveReadingProgress();

                    // Check for new content if at frontier
                    this.checkForNewContent(chapterNum);
                }
            });
        }, {
            rootMargin: '-20% 0px -70% 0px', // Trigger when chapter is 20% down from top
            threshold: 0
        });
    },

    /**
     * Render infinite chapters to the DOM
     */
    renderInfiniteChapters: function(chaptersData) {
        // Set initial setup flag to prevent intersection observer updates during DOM insertion
        this.isInitialSetup = true;

        this.comicContainer.innerHTML = '';
        this.chapterBoundaries = []; // Keep for backward compatibility

        let highestChapterInBatch = window.RipRaven.StateManager ? window.RipRaven.StateManager.maxLoadedChapter || null : null;

        chaptersData.forEach((chapter, chapterIndex) => {
            // Add chapter divider (except for first chapter)
            if (chapterIndex > 0) {
                const divider = document.createElement('div');
                divider.className = 'chapter-divider';
                divider.innerHTML = `<div class="chapter-divider-text">Chapter ${chapter.chapter_num}</div>`;
                this.comicContainer.appendChild(divider);
            }

            // Create chapter container for Intersection Observer
            const chapterContainer = document.createElement('div');
            chapterContainer.className = 'chapter-container';
            chapterContainer.dataset.chapterNum = chapter.chapter_num;

            // Add all images for this chapter
            chapter.images.forEach((imageUrl, pageIndex) => {
                const pageDiv = document.createElement('div');
                pageDiv.className = 'comic-page';
                pageDiv.dataset.chapterNum = chapter.chapter_num;
                pageDiv.dataset.pageNum = pageIndex + 1;

                const img = document.createElement('img');
                // Prepend base path for mounted apps
                const apiBase = window.RipRaven.APIClient ? window.RipRaven.APIClient.getApiBase() : '';
                img.src = apiBase ? `${apiBase}/${imageUrl}` : `/${imageUrl}`;
                img.alt = `Chapter ${chapter.chapter_num} Page ${pageIndex + 1}`;
                img.loading = 'lazy'; // Lazy load images

                pageDiv.appendChild(img);
                chapterContainer.appendChild(pageDiv);
            });

            this.comicContainer.appendChild(chapterContainer);

            // Observe this chapter for scroll tracking
            this.chapterObserver.observe(chapterContainer);

            // Update highest chapter using comparison function for fractional chapters
            if (highestChapterInBatch === null || compareChapterNumbers(chapter.chapter_num, highestChapterInBatch) > 0) {
                highestChapterInBatch = chapter.chapter_num;
            }
        });

        // Update state manager with new data
        if (window.RipRaven.StateManager) {
            window.RipRaven.StateManager.setMaxLoadedChapter(highestChapterInBatch);
            window.RipRaven.StateManager.setChaptersData(chaptersData);
        }

        // Set initial chapter indicator
        if (chaptersData.length > 0) {
            if (window.RipRaven.StateManager) {
                window.RipRaven.StateManager.setCurrentDisplayChapter(chaptersData[0].chapter_num);
            }
            if (window.RipRaven.UIController) {
                window.RipRaven.UIController.updateChapterIndicator(chaptersData[0].chapter_num);
            }
        }

        // Enable intersection observer updates after DOM has settled
        setTimeout(() => {
            this.isInitialSetup = false;
        }, 500); // Wait 500ms for DOM to settle

        // Force layout calculation for accurate boundaries (keep for compatibility)
        setTimeout(() => this.updateChapterBoundaries(), 1000);
    },

    /**
     * Inject new chapters seamlessly
     */
    injectNewChapters: function(newChapters) {
        if (!Array.isArray(newChapters) || newChapters.length === 0) {
            return;
        }

        const currentScrollY = window.scrollY;

        newChapters.forEach((chapter) => {
            // Add chapter divider
            const divider = document.createElement('div');
            divider.className = 'chapter-divider';
            divider.innerHTML = `<div class="chapter-divider-text">Chapter ${chapter.chapter_num}</div>`;
            this.comicContainer.appendChild(divider);

            // Create chapter container
            const chapterContainer = document.createElement('div');
            chapterContainer.className = 'chapter-container';
            chapterContainer.dataset.chapterNum = chapter.chapter_num;

            // Add all images for this chapter
            chapter.images.forEach((imageUrl, pageIndex) => {
                const pageDiv = document.createElement('div');
                pageDiv.className = 'comic-page';
                pageDiv.dataset.chapterNum = chapter.chapter_num;
                pageDiv.dataset.pageNum = pageIndex + 1;

                const img = document.createElement('img');
                const apiBase = window.RipRaven.APIClient ? window.RipRaven.APIClient.getApiBase() : '';
                img.src = apiBase ? `${apiBase}/${imageUrl}` : `/${imageUrl}`;
                img.alt = `Chapter ${chapter.chapter_num} Page ${pageIndex + 1}`;
                img.loading = 'lazy';

                pageDiv.appendChild(img);
                chapterContainer.appendChild(pageDiv);
            });

            this.comicContainer.appendChild(chapterContainer);

            // Observe this chapter for scroll tracking
            this.chapterObserver.observe(chapterContainer);
        });

        // Update state manager
        if (window.RipRaven.StateManager) {
            window.RipRaven.StateManager.appendChaptersData(newChapters);
            // Find highest chapter using comparison function for fractional chapters
            let currentMax = window.RipRaven.StateManager.maxLoadedChapter || null;
            newChapters.forEach(ch => {
                if (currentMax === null || compareChapterNumbers(ch.chapter_num, currentMax) > 0) {
                    currentMax = ch.chapter_num;
                }
            });
            window.RipRaven.StateManager.setMaxLoadedChapter(currentMax);
        }

        // Maintain scroll position
        window.scrollTo(0, currentScrollY);

        // Refresh boundaries after DOM grows
        setTimeout(() => this.updateChapterBoundaries(), 500);
    },

    /**
     * Update chapter boundaries for backward compatibility
     */
    updateChapterBoundaries: function() {
        // Recalculate chapter boundaries based on actual rendered positions
        this.chapterBoundaries = [];
        const pages = this.comicContainer.querySelectorAll('.comic-page');
        let currentChapter = null;
        let chapterStartY = 0;

        pages.forEach((page, index) => {
            // Keep as string for fractional chapter support
            const chapterNum = page.dataset.chapterNum;

            if (currentChapter !== chapterNum) {
                // Finish previous chapter
                if (currentChapter !== null) {
                    this.chapterBoundaries.push({
                        chapterNum: currentChapter,
                        startY: chapterStartY,
                        endY: page.offsetTop
                    });
                }

                // Start new chapter
                currentChapter = chapterNum;
                chapterStartY = page.offsetTop;
            }
        });

        // Add the last chapter
        if (currentChapter !== null && pages.length > 0) {
            const lastPage = pages[pages.length - 1];
            this.chapterBoundaries.push({
                chapterNum: currentChapter,
                startY: chapterStartY,
                endY: lastPage.offsetTop + lastPage.offsetHeight
            });
        }
    },

    /**
     * Check for new content and inject if available
     */
    checkForNewContent: async function(chapterNum) {
        if (!window.RipRaven.StateManager || !window.RipRaven.APIClient) {
            return;
        }

        const currentSeries = window.RipRaven.StateManager.getCurrentSeries();

        if (!currentSeries || chapterNum === undefined || chapterNum === null) {
            return;
        }

        if (this.isLoadingNextChapters) {
            return;
        }

        this.isLoadingNextChapters = true;

        try {
            const newData = await window.RipRaven.APIClient.loadInfiniteChapters(currentSeries, chapterNum);

            const currentMax = window.RipRaven.StateManager.maxLoadedChapter || null;
            // Use comparison function for fractional chapters
            const chaptersToAppend = newData.chapters.filter(ch =>
                currentMax === null || compareChapterNumbers(ch.chapter_num, currentMax) > 0
            );

            if (chaptersToAppend.length > 0) {
                this.injectNewChapters(chaptersToAppend);
            }
        } catch (error) {
            console.error('Error checking for new content:', error);
        } finally {
            this.isLoadingNextChapters = false;
        }
    },

    /**
     * Save reading progress
     */
    saveReadingProgress: async function() {
        if (!window.RipRaven.StateManager || !window.RipRaven.APIClient) {
            return;
        }

        const currentSeries = window.RipRaven.StateManager.getCurrentSeries();
        const currentChapter = window.RipRaven.StateManager.currentChapter;

        if (!currentSeries || !currentChapter) {
            return;
        }

        try {
            await window.RipRaven.APIClient.saveRecentChapter(currentSeries, currentChapter);

            // Reload recent chapters to update UI
            if (window.comicReader && typeof window.comicReader.loadRecent === 'function') {
                await window.comicReader.loadRecent();
            }
        } catch (error) {
            console.error('Error saving reading progress:', error);
        }
    },

    /**
     * Clear all chapter content
     */
    clearContent: function() {
        if (this.comicContainer) {
            this.comicContainer.innerHTML = '';
        }
        this.chapterBoundaries = [];
    },

    /**
     * Show loading state
     */
    showLoading: function() {
        if (this.comicContainer) {
            this.comicContainer.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading infinite chapters...</p></div>';
        }
    },

    /**
     * Show error state
     */
    showError: function(message = 'Error loading chapters. Please try again.') {
        if (this.comicContainer) {
            this.comicContainer.innerHTML = `<div class="error">${message}</div>`;
        }
    },

    /**
     * Cleanup - stop observers and reset state
     */
    cleanup: function() {
        if (this.chapterObserver) {
            this.chapterObserver.disconnect();
            this.chapterObserver = null;
        }
    }
};

// Export for global access
window.RipRaven.ChapterRenderer = ChapterRenderer;
