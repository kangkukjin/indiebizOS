export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // API: YouTube 검색 (AI 활용)
    if (url.pathname === "/api/search" && request.method === "POST") {
      try {
        const { prompt } = await request.json();
        
        // AI를 사용하여 플레이리스트 구성
        const aiResponse = await env.AI.run("@cf/meta/llama-3-8b-instruct", {
          messages: [
            { role: "system", content: "You are a professional music curator. Based on the user's request, create a high-quality playlist of 10-15 songs. Return ONLY a JSON array of strings, where each string is 'Song Title - Artist'. Example: [\"Bohemian Rhapsody - Queen\", \"Imagine - John Lennon\"]. No extra text." },
            { role: "user", content: prompt }
          ]
        });
        
        let searchQueries;
        try {
          const cleanedResponse = aiResponse.response.trim().match(/\[.*\]/s)[0];
          searchQueries = JSON.parse(cleanedResponse);
        } catch (e) {
          searchQueries = [aiResponse.response.trim().replace(/^"|"$/g, '')];
        }
        
        const results = [];
        const searchPromises = searchQueries.slice(0, 15).map(async (query) => {
          try {
            const searchUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;
            const response = await fetch(searchUrl, {
              headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" }
            });
            const html = await response.text();
            const videoIdMatch = html.match(/"videoRenderer":\{"videoId":"([^"]+)"/);
            const titleMatch = html.match(/"title":\{"runs":\[\{"text":"([^"]+)"\}\]/);
            
            if (videoIdMatch) {
              return {
                videoId: videoIdMatch[1],
                title: titleMatch ? titleMatch[1] : query
              };
            }
          } catch (e) { return null; }
          return null;
        });

        const searchResults = await Promise.all(searchPromises);
        results.push(...searchResults.filter(r => r !== null));
        
        return new Response(JSON.stringify({ success: true, results }), { headers: { "Content-Type": "application/json" } });
      } catch (err) {
        return new Response(JSON.stringify({ success: false, error: err.message }), { status: 500 });
      }
    }

    // API: 오디오 스트림 URL 추출 (프록시 경로 반환)
    if (url.pathname === "/api/audio-url" && request.method === "POST") {
      try {
        const { videoId } = await request.json();
        const proxyUrl = `${url.origin}/api/proxy-audio?v=${videoId}`;
        return new Response(JSON.stringify({ success: true, audioUrl: proxyUrl }), { headers: { "Content-Type": "application/json" } });
      } catch (err) {
        return new Response(JSON.stringify({ success: false, error: err.message }), { status: 500 });
      }
    }

    // API: 오디오 프록시 (Piped API + Fallback)
    if (url.pathname === "/api/proxy-audio") {
      const videoId = url.searchParams.get("v");
      if (!videoId) return new Response("Missing videoId", { status: 400 });

      try {
        // 1. Piped API 시도 (가장 안정적)
        const pipedInstances = [
          "https://pipedapi.kavin.rocks",
          "https://api.piped.dev",
          "https://pipedapi.leptons.xyz"
        ];
        
        let audioStream = null;
        for (const instance of pipedInstances) {
          try {
            const pipedRes = await fetch(`${instance}/streams/${videoId}`);
            if (pipedRes.ok) {
              const data = await pipedRes.json();
              audioStream = data.audioStreams
                .filter(s => s.mimeType.startsWith("audio/"))
                .sort((a, b) => b.bitrate - a.bitrate)[0];
              if (audioStream) break;
            }
          } catch (e) { continue; }
        }

        if (!audioStream) {
          // 2. Fallback: YouTube 직접 스크래핑
          const ytUrl = `https://www.youtube.com/watch?v=${videoId}`;
          const ytRes = await fetch(ytUrl, {
            headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" }
          });
          const html = await ytRes.text();
          const match = html.match(/ytInitialPlayerResponse\s*=\s*({.+?});/);
          if (match) {
            const playerResponse = JSON.parse(match[1]);
            const formats = playerResponse.streamingData?.adaptiveFormats || [];
            const format = formats
              .filter(f => f.mimeType && f.mimeType.startsWith("audio/"))
              .sort((a, b) => (b.averageBitrate || 0) - (a.averageBitrate || 0))[0];
            if (format && format.url) {
              audioStream = { url: format.url, mimeType: format.mimeType };
            }
          }
        }

        if (!audioStream || !audioStream.url) {
          throw new Error("오디오 스트림을 추출할 수 없습니다.");
        }

        // 스트림 프록시 실행
        const rangeHeader = request.headers.get("Range");
        const fetchOptions = {
          headers: { "User-Agent": "Mozilla/5.0" }
        };
        if (rangeHeader) fetchOptions.headers["Range"] = rangeHeader;

        const audioResponse = await fetch(audioStream.url, fetchOptions);
        
        const newHeaders = new Headers(audioResponse.headers);
        newHeaders.set("Access-Control-Allow-Origin", "*");
        newHeaders.set("Content-Type", audioStream.mimeType.split(';')[0]);
        // 브라우저 캐싱 허용
        newHeaders.set("Cache-Control", "public, max-age=3600");

        return new Response(audioResponse.body, {
          status: audioResponse.status,
          headers: newHeaders
        });
      } catch (err) {
        return new Response("Proxy Error: " + err.message, { status: 500 });
      }
    }

    return new Response(getHTML(), { headers: { "Content-Type": "text/html; charset=utf-8" } });
  }
};

function getHTML() {
  return `
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Music Station - Ultra Premium</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;700;900&display=swap');
        body { font-family: 'Pretendard', sans-serif; background-color: #000; color: #fff; }
        .glass { background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.1); }
        .active-track { background: rgba(59, 130, 246, 0.2); border-color: rgba(59, 130, 246, 0.5); }
        @keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .rotating { animation: rotate 20s linear infinite; }
        .text-giant { font-size: clamp(5rem, 15vw, 12rem); font-weight: 900; line-height: 0.8; letter-spacing: -0.05em; }
        .custom-scrollbar::-webkit-scrollbar { width: 8px; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 10px; }
        input::placeholder { color: rgba(255,255,255,0.2); }
    </style>
</head>
<body class="min-h-screen flex flex-col overflow-hidden">
    <!-- Background Effect -->
    <div class="fixed inset-0 pointer-events-none">
        <div class="absolute top-[-20%] left-[-10%] w-[70%] h-[70%] bg-blue-900/30 rounded-full blur-[120px]"></div>
        <div class="absolute bottom-[-20%] right-[-10%] w-[70%] h-[70%] bg-purple-900/30 rounded-full blur-[120px]"></div>
    </div>

    <div class="relative z-10 flex flex-col h-screen p-10 md:p-16">
        <!-- Header -->
        <header class="flex justify-between items-start mb-12">
            <div>
                <h1 class="text-giant bg-gradient-to-r from-white via-white to-gray-600 bg-clip-text text-transparent">
                    MUSIC<br>STATION
                </h1>
                <p class="text-2xl md:text-3xl text-gray-400 mt-6 font-medium">Llama 3 AI Curator</p>
            </div>
            <div id="status" class="hidden glass px-8 py-4 rounded-full text-xl font-bold text-blue-400 animate-pulse">
                AI가 음악을 찾는 중...
            </div>
        </header>

        <!-- Main Grid -->
        <main class="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-12 overflow-hidden">
            <!-- Left: Player (Huge) -->
            <div class="lg:col-span-7 flex flex-col justify-center items-center space-y-12">
                <div id="playerCard" class="w-full max-w-4xl flex flex-col items-center space-y-12 opacity-50 transition-opacity duration-500">
                    <!-- Disk -->
                    <div class="relative group">
                        <div id="disk" class="w-64 h-64 md:w-[450px] md:h-[450px] rounded-full bg-gradient-to-tr from-gray-900 via-blue-900 to-gray-900 flex items-center justify-center shadow-[0_0_80px_rgba(37,99,235,0.2)] border-[15px] border-white/5">
                            <div class="w-full h-full rounded-full border-[1px] border-white/10 flex items-center justify-center">
                                <div class="w-24 h-24 md:w-32 md:h-32 bg-black rounded-full border-4 border-white/10 flex items-center justify-center">
                                    <div class="w-4 h-4 bg-blue-500 rounded-full"></div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Info -->
                    <div class="text-center space-y-6 w-full">
                        <h2 id="trackTitle" class="text-4xl md:text-7xl font-black tracking-tighter leading-tight truncate px-4">
                            어떤 음악을 들을까요?
                        </h2>
                        <div class="flex items-center justify-center gap-12 mt-8">
                            <button onclick="playPrev()" class="p-4 hover:scale-125 transition-transform text-gray-500 hover:text-white">
                                <svg class="w-16 h-16" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
                            </button>
                            <button onclick="togglePlay()" id="playBtn" class="w-28 h-28 bg-white text-black rounded-full flex items-center justify-center hover:scale-110 transition-all shadow-xl">
                                <svg id="playIcon" class="w-12 h-12" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                                <svg id="pauseIcon" class="w-12 h-12 hidden" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                            </button>
                            <button onclick="playNext()" class="p-4 hover:scale-125 transition-transform text-gray-500 hover:text-white">
                                <svg class="w-16 h-16" fill="currentColor" viewBox="0 0 24 24"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
                            </button>
                        </div>
                        <audio id="audioElement" class="hidden"></audio>
                    </div>
                </div>
            </div>

            <!-- Right: Search & Playlist -->
            <div class="lg:col-span-5 flex flex-col space-y-8 overflow-hidden">
                <!-- Search -->
                <div class="relative">
                    <input type="text" id="prompt" placeholder="기분이나 장르를 입력하세요..." 
                        class="w-full bg-white/5 border-2 border-white/10 rounded-3xl py-8 px-10 text-3xl font-bold focus:outline-none focus:border-blue-500 transition-all">
                    <button onclick="searchMusic()" class="absolute right-4 top-4 bottom-4 bg-blue-600 hover:bg-blue-500 px-8 rounded-2xl transition-colors">
                        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                    </button>
                </div>

                <!-- List -->
                <div class="flex-1 flex flex-col glass rounded-[40px] p-8 overflow-hidden">
                    <div class="flex justify-between items-center mb-6 px-4">
                        <h3 class="text-3xl font-black uppercase tracking-widest text-gray-500">Playlist</h3>
                        <span id="queueCount" class="text-xl font-bold text-blue-500">0 Tracks</span>
                    </div>
                    <div id="playlist" class="flex-1 overflow-y-auto custom-scrollbar space-y-4 pr-2">
                        <div class="h-full flex items-center justify-center text-gray-600 text-2xl italic">
                            AI에게 음악 추천을 받아보세요.
                        </div>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <script>
        let queue = [];
        let currentIndex = -1;
        const audio = document.getElementById('audioElement');
        const status = document.getElementById('status');
        const playlistEl = document.getElementById('playlist');
        const disk = document.getElementById('disk');
        const playIcon = document.getElementById('playIcon');
        const pauseIcon = document.getElementById('pauseIcon');
        const playerCard = document.getElementById('playerCard');

        async function searchMusic() {
            const prompt = document.getElementById('prompt').value;
            if (!prompt) return;

            status.classList.remove('hidden');
            try {
                const res = await fetch('/api/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt })
                });
                const data = await res.json();
                if (!data.success) throw new Error(data.error);

                queue = data.results;
                document.getElementById('queueCount').textContent = \`\${queue.length} Tracks\`;
                renderPlaylist();
                if (queue.length > 0) playTrack(0);
            } catch (err) {
                alert("검색 중 오류가 발생했습니다: " + err.message);
            } finally {
                status.classList.add('hidden');
            }
        }

        function renderPlaylist() {
            playlistEl.innerHTML = queue.map((track, i) => \`
                <div onclick="playTrack(\${i})" class="group flex items-center gap-6 p-6 rounded-3xl border border-white/5 hover:bg-white/10 transition-all cursor-pointer \${i === currentIndex ? 'active-track' : ''}">
                    <div class="text-2xl font-black text-gray-700 w-10">\${i + 1}</div>
                    <div class="flex-1 min-w-0">
                        <div class="text-2xl font-bold truncate \${i === currentIndex ? 'text-blue-400' : 'text-gray-200'}">\${track.title}</div>
                    </div>
                    \${i === currentIndex ? '<div class="w-3 h-3 rounded-full bg-blue-500 animate-ping"></div>' : ''}
                </div>
            \`).join('');
        }

        async function playTrack(index) {
            if (index < 0 || index >= queue.length) return;
            currentIndex = index;
            const track = queue[index];
            
            playerCard.style.opacity = "1";
            document.getElementById('trackTitle').textContent = track.title;
            renderPlaylist();

            try {
                const res = await fetch('/api/audio-url', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ videoId: track.videoId })
                });
                const data = await res.json();
                
                audio.src = data.audioUrl;
                audio.load();
                const playPromise = audio.play();
                
                if (playPromise !== undefined) {
                    playPromise.catch(error => {
                        console.error("Auto-play prevented:", error);
                        // 사용자가 직접 클릭하도록 유도
                    });
                }
            } catch (err) {
                console.error("Playback error:", err);
                playNext();
            }
        }

        function togglePlay() {
            if (audio.paused) audio.play();
            else audio.pause();
        }

        function playNext() {
            if (currentIndex < queue.length - 1) playTrack(currentIndex + 1);
        }

        function playPrev() {
            if (currentIndex > 0) playTrack(currentIndex - 1);
        }

        audio.onplay = () => {
            disk.classList.add('rotating');
            playIcon.classList.add('hidden');
            pauseIcon.classList.remove('hidden');
        };
        audio.onpause = () => {
            disk.classList.remove('rotating');
            playIcon.classList.remove('hidden');
            pauseIcon.classList.add('hidden');
        };
        audio.onended = playNext;
        
        // 에러 핸들링 강화
        audio.onerror = () => {
            console.error("Audio error occurred");
            // 3초 후 다음 곡 시도
            setTimeout(playNext, 3000);
        };

        document.getElementById('prompt').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') searchMusic();
        });
    </script>
</body>
</html>
  `;
}
