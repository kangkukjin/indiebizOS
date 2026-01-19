export default async function handler(req, res) {
  const CHANNEL_ID = 'UCRp0B_T34RfJtE7UlozWeUA';
  const API_KEY = 'AIzaSyA9Ka_tfOYagVXx1zdc4GNbgESyfRInPFA';

  // 고정 플레이리스트 3개
  const playlists = [
    {
      videoId: '4J60nnOSzCk',
      playlistId: 'PLRRKTBlCwE80drDvSNk9FTPkcdfTmobIg',
      title: '파인만의 물리학강의',
      thumbnail: 'https://img.youtube.com/vi/4J60nnOSzCk/mqdefault.jpg',
      isPlaylist: true
    },
    {
      videoId: 'hvjdWtIt-QI',
      playlistId: 'PLRRKTBlCwE830lSR5Jn13Mj-zK6qfAOv9',
      title: '하이젠베르크의 부분과 전체',
      thumbnail: 'https://img.youtube.com/vi/hvjdWtIt-QI/mqdefault.jpg',
      isPlaylist: true
    },
    {
      videoId: '1UVZs_75sKo',
      playlistId: 'PLRRKTBlCwE82DtCRPoz_MKI5Dn36NdpZw',
      title: '퍼시그의 선과 모터사이클 관리술',
      thumbnail: 'https://img.youtube.com/vi/1UVZs_75sKo/mqdefault.jpg',
      isPlaylist: true
    }
  ];

  try {
    // YouTube Data API로 최신 영상 1개 가져오기
    const apiUrl = `https://www.googleapis.com/youtube/v3/search?key=${API_KEY}&channelId=${CHANNEL_ID}&part=snippet&order=date&maxResults=1&type=video`;
    const response = await fetch(apiUrl);
    const data = await response.json();

    let latestVideo = null;
    if (data.items && data.items.length > 0) {
      const item = data.items[0];
      latestVideo = {
        videoId: item.id.videoId,
        title: item.snippet.title,
        thumbnail: item.snippet.thumbnails.high?.url || item.snippet.thumbnails.medium?.url,
        published: formatDate(item.snippet.publishedAt),
        isPlaylist: false
      };
    }

    // 최신 영상 + 플레이리스트 조합
    const videos = latestVideo ? [latestVideo, ...playlists] : playlists;

    res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=1800');
    res.status(200).json({ videos, channelId: CHANNEL_ID });
  } catch (error) {
    console.error('YouTube fetch error:', error);
    // API 실패시 플레이리스트만 반환
    res.status(200).json({ videos: playlists, channelId: CHANNEL_ID });
  }
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}.${month}.${day}`;
  } catch {
    return '';
  }
}
