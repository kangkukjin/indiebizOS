// Vercel Serverless Function for Guestbook with Firebase Realtime DB

export default async function handler(req, res) {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  // 캐시 비활성화
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  // Firebase Realtime DB URL (환경변수로 설정)
  const FIREBASE_DB_URL = process.env.FIREBASE_DB_URL || 'https://your-project.firebaseio.com';
  const FIREBASE_DB_SECRET = process.env.FIREBASE_DB_SECRET || '';

  const authParam = FIREBASE_DB_SECRET ? `?auth=${FIREBASE_DB_SECRET}` : '';

  try {
    // GET: 방명록 조회
    if (req.method === 'GET') {
      const response = await fetch(
        `${FIREBASE_DB_URL}/guestbook.json${authParam}`
      );
      const data = await response.json();

      if (!data) {
        return res.status(200).json({ entries: [] });
      }

      // Firebase 객체를 배열로 변환하고 최신순 정렬
      const entries = Object.entries(data)
        .map(([id, entry]) => ({ id, ...entry }))
        .sort((a, b) => b.timestamp - a.timestamp);

      return res.status(200).json({ entries });
    }

    // POST: 방명록 작성
    if (req.method === 'POST') {
      const { name, message, password } = req.body;

      if (!name || !message) {
        return res.status(400).json({ error: '이름과 메시지를 입력해주세요.' });
      }

      if (name.length > 50 || message.length > 500) {
        return res.status(400).json({ error: '이름은 50자, 메시지는 500자 이내로 작성해주세요.' });
      }

      const entry = {
        name: name.trim(),
        message: message.trim(),
        password: password ? simpleHash(password) : null,
        timestamp: Date.now(),
        date: new Date().toLocaleDateString('ko-KR', {
          year: 'numeric',
          month: 'long',
          day: 'numeric'
        })
      };

      const response = await fetch(
        `${FIREBASE_DB_URL}/guestbook.json${authParam}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(entry)
        }
      );

      const result = await response.json();
      return res.status(201).json({ success: true, id: result.name });
    }

    // DELETE: 방명록 삭제
    if (req.method === 'DELETE') {
      const { id, password } = req.body;

      if (!id) {
        return res.status(400).json({ error: '삭제할 항목을 찾을 수 없습니다.' });
      }

      // 먼저 해당 항목 조회
      const getResponse = await fetch(
        `${FIREBASE_DB_URL}/guestbook/${id}.json${authParam}`
      );
      const entry = await getResponse.json();

      if (!entry) {
        return res.status(404).json({ error: '항목을 찾을 수 없습니다.' });
      }

      // 비밀번호 확인
      if (entry.password && entry.password !== simpleHash(password)) {
        return res.status(403).json({ error: '비밀번호가 일치하지 않습니다.' });
      }

      // 삭제
      await fetch(
        `${FIREBASE_DB_URL}/guestbook/${id}.json${authParam}`,
        { method: 'DELETE' }
      );

      return res.status(200).json({ success: true });
    }

    return res.status(405).json({ error: 'Method not allowed' });

  } catch (error) {
    console.error('Guestbook API error:', error);
    return res.status(500).json({ error: '서버 오류가 발생했습니다.' });
  }
}

// 간단한 해시 함수 (보안용이 아닌 기본 비교용)
function simpleHash(str) {
  if (!str) return null;
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return hash.toString(16);
}
