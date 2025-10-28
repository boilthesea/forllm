import { apiRequest } from './api.js';

let ebookData = null;
let voiceOptions = null;

async function initAudiobookGenerator() {
    await loadVoiceOptions(); // Load voices first

    const openEbookBtn = document.getElementById('audiobook-open-ebook-btn');
    const fileInput = document.getElementById('audiobook-file-input');
    const chapterList = document.getElementById('audiobook-chapter-list');

    if (openEbookBtn) {
        openEbookBtn.addEventListener('click', () => {
            fileInput.click();
        });
    }

    if (fileInput) {
        fileInput.addEventListener('change', handleFileUpload);
    }

    if (chapterList) {
        chapterList.addEventListener('click', handleChapterSelection);
    }

    const queueBtn = document.getElementById('audiobook-queue-btn');
    if (queueBtn) {
        queueBtn.addEventListener('click', queueAudiobook);
    }
}

async function loadVoiceOptions() {
    try {
        const data = await apiRequest('/api/tts/voices');
        voiceOptions = data;
        populateLanguageSelector();
    } catch (error) {
        console.error('Failed to load TTS voice options:', error);
        const langContainer = document.getElementById('audiobook-language-select');
        if (langContainer) {
            langContainer.innerHTML = '<p class="error-message">Could not load voices.</p>';
        }
    }
}

function populateLanguageSelector() {
    const langContainer = document.getElementById('audiobook-language-select');
    if (!langContainer || !voiceOptions || !voiceOptions.tts_models) return;

    const kokoroModel = voiceOptions.tts_models.find(m => m.id === 'kokoro');
    if (!kokoroModel) return;

    const languages = [...new Set(kokoroModel.voices.map(v => v.language))];
    
    const langMap = {
        'en': 'English', 'es': 'Spanish', 'fr': 'French', 'hi': 'Hindi',
        'it': 'Italian', 'ja': 'Japanese', 'pt': 'Portuguese', 'zh': 'Chinese'
    };

    langContainer.innerHTML = '';
    languages.forEach((langCode, index) => {
        const radioWrapper = document.createElement('div');
        radioWrapper.className = 'radio-option';

        const radioInput = document.createElement('input');
        radioInput.type = 'radio';
        radioInput.id = `lang-${langCode}`;
        radioInput.name = 'audiobook-language';
        radioInput.value = langCode;
        if (index === 0) { // Default select English
            radioInput.checked = true;
        }

        const radioLabel = document.createElement('label');
        radioLabel.htmlFor = `lang-${langCode}`;
        radioLabel.textContent = langMap[langCode] || langCode;

        radioWrapper.appendChild(radioInput);
        radioWrapper.appendChild(radioLabel);
        langContainer.appendChild(radioWrapper);
    });

    langContainer.addEventListener('change', (event) => {
        if (event.target.name === 'audiobook-language') {
            populateVoiceSelector(event.target.value);
        }
    });

    // Initial population
    // Initial population for the default language (first in the list)
    if (languages.length > 0) {
        populateVoiceSelector(languages[0]);
    }
}

function populateVoiceSelector(languageCode) {
    const voiceSelect = document.getElementById('audiobook-voice-select');
    if (!voiceSelect || !voiceOptions) return;

    const kokoroModel = voiceOptions.tts_models.find(m => m.id === 'kokoro');
    const voices = kokoroModel.voices.filter(v => v.language === languageCode);

    voiceSelect.innerHTML = '';
    if (voices.length === 0) {
        voiceSelect.innerHTML = '<option value="">No voices for this language</option>';
        return;
    }

    voices.forEach(voice => {
        const option = document.createElement('option');
        option.value = voice.code;
        // Example: "Heart - American Female"
        const accent = voice.accent.charAt(0).toUpperCase() + voice.accent.slice(1);
        const gender = voice.gender.charAt(0).toUpperCase() + voice.gender.slice(1);
        option.textContent = `${voice.name} - ${accent} ${gender}`;
        voiceSelect.appendChild(option);
    });
}


async function handleFileUpload(event) {
    const files = event.target.files;
    if (!files.length) {
        return;
    }
const file = files[0]; // Get the first file from the FileList

    const formData = new FormData();
    formData.append('ebook_file', file);

    const statusArea = document.getElementById('audiobook-status-area');
    statusArea.textContent = 'Uploading and processing ebook...';
    document.getElementById('audiobook-queue-btn').disabled = true;

    try {
        const response = await apiRequest('/api/audio/upload_ebook', 'POST', formData, true); // Use apiRequest
        ebookData = response;
        populateAudiobookUI(ebookData);
        statusArea.textContent = 'Ebook processed successfully. Please review the chapters.';
    } catch (error) {
        console.error('Error uploading ebook:', error);
        statusArea.textContent = `Error: ${error.message}`;
    }
}

function populateAudiobookUI(data) {
    document.getElementById('audiobook-title').textContent = data.title || 'No Title';
    document.getElementById('audiobook-author').textContent = data.author || 'Unknown Author';

    const coverImage = document.getElementById('audiobook-cover-image');
    if (data.cover_path) {
        // The path from calibre is temporary. We need a way to serve it.
        // For now, let's assume an endpoint `/api/audio/temp_cover?path=...`
        // This needs to be implemented on the backend.
        // As a placeholder, we won't set the src until that's done.
        // coverImage.src = `/api/audio/temp_cover?path=${encodeURIComponent(data.cover_path)}`;
        coverImage.style.display = 'none'; // Hide until backend endpoint exists
    } else {
        coverImage.style.display = 'none';
    }

    const chapterList = document.getElementById('audiobook-chapter-list');
    chapterList.innerHTML = '';
    data.chapters.forEach((chapter, index) => {
        const chapterItem = document.createElement('div');
        chapterItem.className = 'chapter-item';
        chapterItem.dataset.chapterIndex = index;

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = true;
        checkbox.id = `chapter-checkbox-${chapter.chapter_id}`;
        checkbox.dataset.chapterId = chapter.chapter_id;
        
        const label = document.createElement('label');
        label.htmlFor = `chapter-checkbox-${chapter.chapter_id}`;
        label.textContent = chapter.title;
        label.className = 'chapter-title-label';

        chapterItem.appendChild(checkbox);
        chapterItem.appendChild(label);
        chapterList.appendChild(chapterItem);
    });

    if (data.chapters.length > 0) {
        selectChapter(0); // Select first chapter by default
    }

    document.getElementById('audiobook-queue-btn').disabled = false;
}

function handleChapterSelection(event) {
    // Clicking anywhere on the item should select it for viewing
    const chapterItem = event.target.closest('.chapter-item');
    if (chapterItem) {
        const chapterIndex = parseInt(chapterItem.dataset.chapterIndex, 10);
        selectChapter(chapterIndex);
    }
}

function selectChapter(chapterIndex) {
    const chapterItems = document.querySelectorAll('#audiobook-chapter-list .chapter-item');
    chapterItems.forEach(item => {
        item.classList.remove('selected');
    });

    if (chapterItems[chapterIndex]) {
        chapterItems[chapterIndex].classList.add('selected');
    }

    const chapter = ebookData.chapters[chapterIndex];
    if (chapter) {
        document.getElementById('audiobook-chapter-text').value = chapter.text;
    }
}

async function queueAudiobook() {
    const statusArea = document.getElementById('audiobook-status-area');
    if (!ebookData || !ebookData.book_id) {
        statusArea.textContent = 'Error: No ebook data loaded.';
        return;
    }

    const voiceSelect = document.getElementById('audiobook-voice-select');
    const selectedVoice = voiceSelect.value;

    if (!selectedVoice) {
        statusArea.textContent = 'Error: Please select a voice.';
        return;
    }

    const selectedCheckboxes = document.querySelectorAll('#audiobook-chapter-list input[type="checkbox"]:checked');
    
    if (selectedCheckboxes.length === 0) {
        statusArea.textContent = 'Error: Please select at least one chapter.';
        return;
    }

    const selectedChapters = Array.from(selectedCheckboxes).map(checkbox => {
        const chapterId = parseInt(checkbox.dataset.chapterId, 10);
        // Find the full chapter data from our stored ebookData
        return ebookData.chapters.find(c => c.chapter_id === chapterId);
    });

    const selectedLanguage = document.querySelector('input[name="audiobook-language"]:checked').value;

    const payload = {
        book_id: ebookData.book_id,
        chapters: selectedChapters, // Send the full chapter objects
        voice: selectedVoice,
        lang_code: selectedLanguage
    };

    statusArea.textContent = 'Queueing audiobook generation...';
    document.getElementById('audiobook-queue-btn').disabled = true;

    try {
        const response = await apiRequest('/api/audio/queue_audiobook', 'POST', payload);
        statusArea.textContent = `Audiobook queued successfully (Job ID: ${response.parent_request_id}).`;
    } catch (error) {
        console.error('Error queueing audiobook:', error);
        statusArea.textContent = `Error: ${error.message}`;
        document.getElementById('audiobook-queue-btn').disabled = false;
    }
}

function initAudiobookLibrary() {
    document.addEventListener('DOMContentLoaded', () => {
        const backToLibraryBtn = document.getElementById('back-to-library-btn');
        if (backToLibraryBtn) {
            backToLibraryBtn.addEventListener('click', showAudiobookLibrary);
        }
    });
}

async function showAudiobookLibrary() {
    document.getElementById('audiobook-player-section').style.display = 'none';
    document.getElementById('audiobook-library-section').style.display = 'block';
    document.getElementById('audiobook-generation-section').style.display = 'none';

    try {
        const audiobooks = await apiRequest('/api/audio/audiobooks');
        const grid = document.getElementById('audiobook-grid');
        grid.innerHTML = '';
        if (audiobooks.length === 0) {
            grid.innerHTML = '<p>No completed audiobooks found.</p>';
            return;
        }
        audiobooks.forEach(book => {
            const bookElement = document.createElement('div');
            bookElement.className = 'audiobook-item';
            bookElement.dataset.bookId = book.id;
            bookElement.innerHTML = `
                <img src="${book.cover_image_path}" alt="Cover for ${book.title}">
                <div class="audiobook-info">
                    <h4>${book.title}</h4>
                    <p>${book.author}</p>
                </div>
            `;
            bookElement.addEventListener('click', () => showAudiobookPlayer(book.id));
            grid.appendChild(bookElement);
        });
    } catch (error) {
        console.error('Error fetching audiobooks:', error);
        document.getElementById('audiobook-grid').innerHTML = '<p>Error loading audiobooks.</p>';
    }
}

async function showAudiobookPlayer(bookId) {
    document.getElementById('audiobook-library-section').style.display = 'none';
    document.getElementById('audiobook-player-section').style.display = 'block';

    try {
        const book = await apiRequest(`/api/audio/audiobooks/${bookId}`);
        document.getElementById('player-book-title').textContent = book.title;
        document.getElementById('player-book-author').textContent = book.author;
        document.getElementById('player-cover-image').src = book.cover_image_path;

        const player = document.getElementById('audiobook-player');
        player.src = book.output_file_path;

        const chapterSelect = document.getElementById('player-chapter-select');
        chapterSelect.innerHTML = '';
        const chapters = book.chapters;
        chapters.forEach(chapter => {
            const option = document.createElement('option');
            option.value = chapter.start_time;
            option.textContent = chapter.title;
            chapterSelect.appendChild(option);
        });

        chapterSelect.addEventListener('change', () => {
            player.currentTime = parseFloat(chapterSelect.value);
            player.play();
        });

    } catch (error) {
        console.error(`Error fetching audiobook ${bookId}:`, error);
        // Handle error display
    }
}

export { initAudiobookGenerator, initAudiobookLibrary, showAudiobookLibrary };