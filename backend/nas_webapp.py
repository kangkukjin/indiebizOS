"""
nas_webapp.py - NAS 기본 웹앱 HTML
get_default_webapp_html() 함수 제공

api_nas.py에서 분리됨
별도의 static/nas/index.html이 있으면 이 파일은 폴백으로만 사용됨
"""


def get_default_webapp_html() -> str:
    """기본 NAS 웹앱 HTML"""
    return '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IndieBiz Remote Finder</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .file-item:hover { background-color: #f3f4f6; }
        .file-item.selected { background-color: #dbeafe; }
        video { max-height: 70vh; }
        img.preview { max-height: 70vh; max-width: 100%; object-fit: contain; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <div id="app" class="container mx-auto p-4 max-w-4xl">
        <!-- 로그인 화면 -->
        <div id="login-screen" class="hidden">
            <div class="bg-white rounded-xl shadow-lg p-8 max-w-md mx-auto mt-20">
                <h1 class="text-2xl font-bold text-center mb-6">&#128450; IndieBiz Remote Finder</h1>
                <form id="login-form" class="space-y-4">
                    <input type="password" id="password" placeholder="비밀번호"
                        class="w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none">
                    <button type="submit"
                        class="w-full py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition">
                        로그인
                    </button>
                    <p id="login-error" class="text-red-500 text-center hidden"></p>
                </form>
            </div>
        </div>

        <!-- 파일 탐색기 화면 -->
        <div id="explorer-screen" class="hidden">
            <!-- 헤더 -->
            <div class="bg-white rounded-xl shadow-lg p-4 mb-4">
                <div class="flex items-center justify-between">
                    <h1 class="text-xl font-bold">&#128450; Remote Finder</h1>
                    <button id="logout-btn" class="text-gray-500 hover:text-red-500">로그아웃</button>
                </div>
                <!-- 경로 표시 -->
                <div id="breadcrumb" class="mt-2 text-sm text-gray-600 flex items-center gap-2">
                    <span id="current-path">/</span>
                </div>
            </div>

            <!-- 파일 목록 -->
            <div class="bg-white rounded-xl shadow-lg overflow-hidden">
                <div id="file-list" class="divide-y">
                    <!-- 파일 아이템들이 여기에 렌더링됨 -->
                </div>
                <div id="empty-message" class="hidden p-8 text-center text-gray-500">
                    폴더가 비어있습니다
                </div>
            </div>
        </div>

        <!-- 미리보기 모달 -->
        <div id="preview-modal" class="hidden fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div class="bg-white rounded-xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
                <div class="flex items-center justify-between p-4 border-b">
                    <h3 id="preview-title" class="font-semibold truncate"></h3>
                    <button id="close-preview" class="text-gray-500 hover:text-gray-700 text-2xl">&times;</button>
                </div>
                <div id="preview-content" class="p-4 overflow-auto max-h-[calc(90vh-80px)]">
                    <!-- 미리보기 콘텐츠 -->
                </div>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = window.location.origin + '/nas';
        let currentPath = '';
        let sessionToken = null;

        // 초기화
        async function init() {
            const authCheck = await fetch(API_BASE + '/auth/check', { credentials: 'include' });
            const authData = await authCheck.json();

            if (!authData.enabled) {
                document.body.innerHTML = '<div class="p-20 text-center"><h1 class="text-2xl">&#128274; NAS 비활성화</h1><p>설정에서 활성화해주세요.</p></div>';
                return;
            }

            if (authData.authenticated) {
                showExplorer();
                loadFiles('');
            } else {
                showLogin();
            }
        }

        function showLogin() {
            document.getElementById('login-screen').classList.remove('hidden');
            document.getElementById('explorer-screen').classList.add('hidden');
        }

        function showExplorer() {
            document.getElementById('login-screen').classList.add('hidden');
            document.getElementById('explorer-screen').classList.remove('hidden');
        }

        // 로그인
        document.getElementById('login-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const password = document.getElementById('password').value;
            const errorEl = document.getElementById('login-error');

            try {
                const res = await fetch(API_BASE + '/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password }),
                    credentials: 'include'
                });

                if (res.ok) {
                    const data = await res.json();
                    sessionToken = data.session_token;
                    showExplorer();
                    loadFiles('');
                } else {
                    errorEl.textContent = '비밀번호가 올바르지 않습니다';
                    errorEl.classList.remove('hidden');
                }
            } catch (err) {
                errorEl.textContent = '연결 오류';
                errorEl.classList.remove('hidden');
            }
        });

        // 로그아웃
        document.getElementById('logout-btn').addEventListener('click', async () => {
            await fetch(API_BASE + '/auth/logout', { method: 'POST', credentials: 'include' });
            showLogin();
        });

        // 파일 목록 로드
        async function loadFiles(path) {
            currentPath = path;

            const res = await fetch(API_BASE + '/files?path=' + encodeURIComponent(path), {
                credentials: 'include'
            });

            if (res.status === 401) {
                showLogin();
                return;
            }

            const data = await res.json();
            renderFiles(data);
        }

        // 파일 목록 렌더링
        function renderFiles(data) {
            const listEl = document.getElementById('file-list');
            const emptyEl = document.getElementById('empty-message');
            const pathEl = document.getElementById('current-path');

            pathEl.textContent = data.path;

            if (data.items.length === 0) {
                listEl.innerHTML = '';
                emptyEl.classList.remove('hidden');
                return;
            }

            emptyEl.classList.add('hidden');

            let html = '';

            // 상위 폴더
            if (data.parent) {
                html += `
                    <div class="file-item p-3 flex items-center gap-3 cursor-pointer" onclick="loadFiles('${data.parent}')">
                        <span class="text-2xl">&#11014;&#65039;</span>
                        <span class="text-gray-600">상위 폴더</span>
                    </div>
                `;
            }

            for (const item of data.items) {
                const icon = item.is_dir ? '&#128193;' : getFileIcon(item.category);
                const size = item.size ? formatSize(item.size) : '';
                const escapedPath = item.path.replace(/'/g, "\\\\'");

                if (item.is_dir) {
                    html += `
                        <div class="file-item p-3 flex items-center gap-3 cursor-pointer" onclick="loadFiles('${escapedPath}')">
                            <span class="text-2xl">${icon}</span>
                            <div class="flex-1 min-w-0">
                                <p class="font-medium truncate">${item.name}</p>
                            </div>
                        </div>
                    `;
                } else {
                    html += `
                        <div class="file-item p-3 flex items-center gap-3 cursor-pointer" onclick="openFile('${escapedPath}', '${item.category}', '${item.name}')">
                            <span class="text-2xl">${icon}</span>
                            <div class="flex-1 min-w-0">
                                <p class="font-medium truncate">${item.name}</p>
                                <p class="text-sm text-gray-500">${size}</p>
                            </div>
                        </div>
                    `;
                }
            }

            listEl.innerHTML = html;
        }

        function getFileIcon(category) {
            const icons = {
                video: '&#127916;',
                audio: '&#127925;',
                image: '&#128444;&#65039;',
                text: '&#128196;',
                pdf: '&#128213;',
                other: '&#128230;'
            };
            return icons[category] || '&#128230;';
        }

        function formatSize(bytes) {
            const units = ['B', 'KB', 'MB', 'GB'];
            let i = 0;
            while (bytes >= 1024 && i < units.length - 1) {
                bytes /= 1024;
                i++;
            }
            return bytes.toFixed(1) + ' ' + units[i];
        }

        // 파일 열기
        async function openFile(path, category, name) {
            const modal = document.getElementById('preview-modal');
            const title = document.getElementById('preview-title');
            const content = document.getElementById('preview-content');

            title.textContent = name;

            const fileUrl = API_BASE + '/file?path=' + encodeURIComponent(path);

            if (category === 'video') {
                // 코덱 분석
                let probeData = null;
                try {
                    const probeRes = await fetch(API_BASE + '/probe?path=' + encodeURIComponent(path), { credentials: 'include' });
                    if (probeRes.ok) probeData = await probeRes.json();
                } catch(e) {}

                const needsTranscode = probeData && probeData.needs_transcode;

                // 외부 자막 수집
                let trackTags = '';
                try {
                    const subRes = await fetch(API_BASE + '/subtitles?path=' + encodeURIComponent(path), { credentials: 'include' });
                    if (subRes.ok) {
                        const subData = await subRes.json();
                        if (subData.subtitles && subData.subtitles.length > 0) {
                            subData.subtitles.forEach((sub, idx) => {
                                let subUrl = API_BASE + '/subtitle?path=' + encodeURIComponent(sub.path);
                                if (sub.smi_class) subUrl += '&smi_class=' + encodeURIComponent(sub.smi_class);
                                const isDefault = idx === 0 ? 'default' : '';
                                const label = sub.lang_label || sub.filename;
                                const srclang = sub.lang_code || 'ko';
                                trackTags += `<track kind="subtitles" src="${subUrl}" srclang="${srclang}" label="${label}" ${isDefault}>`;
                            });
                        }
                    }
                } catch(e) {}

                // 내장 자막 수집
                if (probeData && probeData.subtitle_tracks && probeData.subtitle_tracks.length > 0) {
                    probeData.subtitle_tracks.forEach((st, idx) => {
                        const stUrl = API_BASE + '/embedded-subtitle?path=' + encodeURIComponent(path) + '&track=' + st.index;
                        const isDefault = !trackTags && idx === 0 ? 'default' : '';
                        const label = st.title || st.language || ('Track ' + st.index);
                        const srclang = st.language || 'und';
                        trackTags += `<track kind="subtitles" src="${stUrl}" srclang="${srclang}" label="[내장] ${label}" ${isDefault}>`;
                    });
                }

                if (needsTranscode) {
                    // 트랜스코딩 모드
                    const srcUrl = API_BASE + '/transcode?path=' + encodeURIComponent(path);
                    content.innerHTML = `
                        <video id="nas-video" controls autoplay class="w-full" crossorigin="anonymous">
                            <source src="${srcUrl}" type="video/mp4">
                            ${trackTags}
                        </video>
                        <div id="seek-notice" class="text-center text-sm text-gray-500 mt-2 hidden">탐색 중...</div>
                    `;
                    // 탐색(seek) 처리: 새 트랜스코딩 세션
                    const video = document.getElementById('nas-video');
                    let isSeeking = false;
                    video.addEventListener('seeking', () => {
                        if (isSeeking) return;
                        isSeeking = true;
                        const seekTime = video.currentTime;
                        document.getElementById('seek-notice').classList.remove('hidden');
                        video.src = API_BASE + '/transcode?path=' + encodeURIComponent(path) + '&start=' + seekTime;
                        video.play().catch(() => {});
                        setTimeout(() => {
                            isSeeking = false;
                            document.getElementById('seek-notice').classList.add('hidden');
                        }, 3000);
                    });
                } else {
                    // 직접 재생 (호환 코덱)
                    content.innerHTML = `<video controls autoplay class="w-full" crossorigin="anonymous"><source src="${fileUrl}">${trackTags}</video>`;
                }
            } else if (category === 'audio') {
                content.innerHTML = `<audio controls autoplay class="w-full"><source src="${fileUrl}"></audio>`;
            } else if (category === 'image') {
                content.innerHTML = `<img src="${fileUrl}" class="preview mx-auto">`;
            } else if (category === 'text') {
                fetch(API_BASE + '/text?path=' + encodeURIComponent(path), { credentials: 'include' })
                    .then(r => r.json())
                    .then(data => {
                        content.innerHTML = `<pre class="whitespace-pre-wrap text-sm bg-gray-50 p-4 rounded">${escapeHtml(data.content)}</pre>`;
                    });
            } else if (category === 'pdf') {
                content.innerHTML = `<iframe src="${fileUrl}" class="w-full h-[70vh]"></iframe>`;
            } else {
                content.innerHTML = `<div class="text-center py-8"><a href="${fileUrl}" download class="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600">다운로드</a></div>`;
            }

            modal.classList.remove('hidden');
        }

        function escapeHtml(str) {
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }

        // 미디어 요소 정리 (메모리 누수 방지)
        function cleanupMediaElements() {
            const container = document.getElementById('preview-content');
            const videos = container.querySelectorAll('video');
            const audios = container.querySelectorAll('audio');
            videos.forEach(v => { v.pause(); v.removeAttribute('src'); v.load(); });
            audios.forEach(a => { a.pause(); a.removeAttribute('src'); a.load(); });
        }

        function closePreviewModal() {
            cleanupMediaElements();
            document.getElementById('preview-modal').classList.add('hidden');
            document.getElementById('preview-content').innerHTML = '';
        }

        // 미리보기 닫기
        document.getElementById('close-preview').addEventListener('click', closePreviewModal);

        document.getElementById('preview-modal').addEventListener('click', (e) => {
            if (e.target.id === 'preview-modal') closePreviewModal();
        });

        // ESC 키로 모달 닫기
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closePreviewModal();
        });

        // 시작
        init();
    </script>
</body>
</html>'''
