document.addEventListener('DOMContentLoaded', () => {
    const downloadForm = document.getElementById('download-form');
    const videoUrlInput = document.getElementById('video-url');
    const cookieFileInput = document.getElementById('cookie-file');
    const submitBtn = document.getElementById('submit-btn');
    
    const errorCard = document.getElementById('error-card');
    const errorMessage = document.getElementById('error-message');
    
    const loadingState = document.getElementById('loading-state');
    const resultState = document.getElementById('result-state');
    
    const videoThumbnail = document.getElementById('video-thumbnail');
    const videoDuration = document.getElementById('video-duration');
    const videoTitle = document.getElementById('video-title');
    const videoUploader = document.getElementById('video-uploader');
    const formatsTbody = document.getElementById('formats-tbody');

    // Helper untuk memformat ukuran berkas (bytes ke MB/KB)
    function formatBytes(bytes) {
        if (!bytes) return '-';
        const k = 1024;
        const dm = 1; // decimal places
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    // Submit handler
    downloadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const url = videoUrlInput.value.trim();
        if (!url) return;

        // Reset state
        hideElement(errorCard);
        hideElement(resultState);
        showElement(loadingState);
        setButtonLoadingState(true);

        try {
            const formData = new FormData();
            formData.append('url', url);
            if (cookieFileInput && cookieFileInput.files.length > 0) {
                formData.append('cookie_file', cookieFileInput.files[0]);
            }

            const response = await fetch('/api/info', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Terjadi kesalahan sistem.');
            }

            // Tampilkan data hasil analisis
            renderVideoDetails(data);
            
            // Sembunyikan loading dan tampilkan hasil
            hideElement(loadingState);
            showElement(resultState);

        } catch (error) {
            console.error('Error fetching video info:', error);
            showError(error.message || 'Gagal memproses tautan video. Pastikan tautan valid dan didukung.');
            hideElement(loadingState);
        } finally {
            setButtonLoadingState(false);
        }
    });

    // Menampilkan detail video
    function renderVideoDetails(data) {
        videoThumbnail.src = data.thumbnail || 'https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?q=80&w=600&auto=format&fit=crop';
        videoDuration.textContent = data.duration || '0:00';
        videoTitle.textContent = data.title || 'Video Tanpa Judul';
        videoUploader.textContent = data.uploader || 'Unknown Creator';

        // Bersihkan body tabel format
        formatsTbody.innerHTML = '';

        if (!data.formats || data.formats.length === 0) {
            formatsTbody.innerHTML = `
                <tr>
                    <td colspan="4" class="px-5 py-8 text-center text-sm font-semibold text-slate-500">
                        Tidak ada format unduhan yang langsung didukung. Coba link video lainnya.
                    </td>
                </tr>
            `;
            return;
        }

        // Render format satu per satu
        data.formats.forEach(f => {
            const tr = document.createElement('tr');
            tr.className = 'hover:bg-slate-900/20 transition-colors';

            // Kategori Badge & Resolusi
            let typeBadge = '';
            let qualityText = f.resolution;
            
            if (f.type === 'video_audio') {
                typeBadge = `<span class="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-bold bg-violet-500/10 text-violet-400 border border-violet-500/20">Video + Audio</span>`;
            } else if (f.type === 'audio') {
                typeBadge = `<span class="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-bold bg-sky-500/10 text-sky-400 border border-sky-500/20">Audio Saja</span>`;
            } else if (f.type === 'video_only') {
                typeBadge = `<span class="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">Video Saja</span>`;
            }

            // Kolom Ukuran
            const sizeText = formatBytes(f.filesize);

            // Kolom Ekstensi / Format
            const extBadge = `<span class="px-2 py-0.5 rounded bg-slate-900 text-slate-400 text-xs font-semibold uppercase">${f.ext}</span>`;

            // Tombol download
            const cookieQuery = data.cookie_token ? `&token=${encodeURIComponent(data.cookie_token)}` : '';
        const downloadUrl = `/api/download?url=${encodeURIComponent(data.original_url)}&format_id=${encodeURIComponent(f.format_id)}${cookieQuery}`;

            tr.innerHTML = `
                <td class="px-5 py-4 whitespace-nowrap text-sm font-bold text-white">
                    <div class="flex flex-col gap-1">
                        <span>${qualityText}</span>
                        <span class="text-[11px] text-slate-500 font-medium">${f.note}</span>
                    </div>
                </td>
                <td class="px-5 py-4 whitespace-nowrap text-sm font-semibold text-slate-300">
                    ${sizeText}
                </td>
                <td class="px-5 py-4 whitespace-nowrap text-sm">
                    <div class="flex items-center gap-2">
                        ${extBadge}
                        ${typeBadge}
                    </div>
                </td>
                <td class="px-5 py-4 whitespace-nowrap text-right text-sm">
                    <a 
                        href="${downloadUrl}" 
                        target="_blank"
                        class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-900 hover:bg-violet-600 text-white font-semibold text-xs border border-slate-800 hover:border-transparent transition-all duration-300 shadow-md hover:shadow-violet-600/20 cursor-pointer"
                    >
                        <span>Unduh</span>
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" class="w-3.5 h-3.5">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
                        </svg>
                    </a>
                </td>
            `;

            formatsTbody.appendChild(tr);
        });
    }

    // Loader helper functions
    function setButtonLoadingState(isLoading) {
        if (isLoading) {
            submitBtn.disabled = true;
            submitBtn.classList.add('opacity-70', 'cursor-not-allowed');
            submitBtn.innerHTML = `
                <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>Menganalisis...</span>
            `;
        } else {
            submitBtn.disabled = false;
            submitBtn.classList.remove('opacity-70', 'cursor-not-allowed');
            submitBtn.innerHTML = `
                <span>Analisis</span>
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" class="w-4 h-4">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
                </svg>
            `;
        }
    }

    function showError(message) {
        errorMessage.textContent = message;
        showElement(errorCard);
    }

    function showElement(el) {
        el.classList.remove('hidden');
    }

    function hideElement(el) {
        el.classList.add('hidden');
    }
});
