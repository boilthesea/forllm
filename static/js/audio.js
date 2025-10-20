import { api } from './api.js';

let ebookData = null;

function initAudiobookGenerator() {
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
}

async function handleFileUpload(event) {
    const file = event.target.files;
    if (!file) {
        return;
    }

    const formData = new FormData();
    formData.append('ebook_file', file);

    const statusArea = document.getElementById('audiobook-status-area');
    statusArea.textContent = 'Uploading and processing ebook...';
    document.getElementById('audiobook-queue-btn').disabled = true;

    try {
        const response = await api.post('/api/audio/upload_ebook', formData, {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        });
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
    if (data.cover_image_path) {
        coverImage.src = data.cover_image_path;
        coverImage.style.display = 'block';
    } else {
        coverImage.style.display = 'none';
    }

    const chapterList = document.getElementById('audiobook-chapter-list');
    chapterList.innerHTML = '';
    data.chapters.forEach((chapter, index) => {
        const chapterItem = document.createElement('div');
        chapterItem.className = 'chapter-item';
        chapterItem.dataset.chapterIndex = index;
        chapterItem.textContent = chapter.title;
        chapterList.appendChild(chapterItem);
    });

    if (data.chapters.length > 0) {
        selectChapter(0);
    }

    document.getElementById('audiobook-queue-btn').disabled = false;
}

function handleChapterSelection(event) {
    if (event.target.classList.contains('chapter-item')) {
        const chapterIndex = parseInt(event.target.dataset.chapterIndex, 10);
        selectChapter(chapterIndex);
    }
}

function selectChapter(chapterIndex) {
    const chapterItems = document.querySelectorAll('#audiobook-chapter-list .chapter-item');
    chapterItems.forEach(item => {
        if (parseInt(item.dataset.chapterIndex, 10) === chapterIndex) {
            item.classList.add('selected');
        } else {
            item.classList.remove('selected');
        }
    });

    const chapter = ebookData.chapters[chapterIndex];
    if (chapter) {
        document.getElementById('audiobook-chapter-text').value = chapter.extracted_text;
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
        const audiobooks = await api.get('/api/audio/audiobooks');
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
        const book = await api.get(`/api/audio/audiobooks/${bookId}`);
        document.getElementById('player-book-title').textContent = book.title;
        document.getElementById('player-book-author').textContent = book.author;
        document.getElementById('player-cover-image').src = book.cover_image_path;

        const player = document.getElementById('audiobook-player');
        player.src = book.output_file_path;

        const chapterSelect = document.getElementById('player-chapter-select');
        chapterSelect.innerHTML = '';
        const chapters = JSON.parse(book.chapters_json);
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