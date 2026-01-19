export default async function handler(req, res) {
  const RSS_URL = 'https://irepublic.tistory.com/rss';

  try {
    const response = await fetch(RSS_URL);
    const xml = await response.text();

    // Parse RSS XML
    const posts = parseRSS(xml);

    res.setHeader('Cache-Control', 's-maxage=600, stale-while-revalidate=300');
    res.status(200).json({ posts });
  } catch (error) {
    console.error('RSS fetch error:', error);
    res.status(500).json({ error: 'Failed to fetch RSS', posts: [] });
  }
}

function parseRSS(xml) {
  const posts = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/g;
  const titleRegex = /<title><!\[CDATA\[(.*?)\]\]><\/title>|<title>(.*?)<\/title>/;
  const linkRegex = /<link>(.*?)<\/link>/;
  const descRegex = /<description>([\s\S]*?)<\/description>/;
  const dateRegex = /<pubDate>(.*?)<\/pubDate>/;
  const categoryRegex = /<category>(.*?)<\/category>/;

  let match;
  while ((match = itemRegex.exec(xml)) !== null && posts.length < 5) {
    const item = match[1];

    const titleMatch = item.match(titleRegex);
    const linkMatch = item.match(linkRegex);
    const descMatch = item.match(descRegex);
    const dateMatch = item.match(dateRegex);
    const categoryMatch = item.match(categoryRegex);

    const title = titleMatch ? (titleMatch[1] || titleMatch[2]) : '';
    const link = linkMatch ? linkMatch[1] : '';
    const pubDate = dateMatch ? dateMatch[1] : '';
    const category = categoryMatch ? categoryMatch[1] : '';

    // Get full HTML content
    let fullContent = '';
    if (descMatch) {
      fullContent = descMatch[1]
        .replace(/<!\[CDATA\[/g, '')
        .replace(/\]\]>/g, '')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&')
        .replace(/&quot;/g, '"');
    }

    // Create short description (text only, first 150 chars)
    const cleanDesc = fullContent
      .replace(/<[^>]*>/g, '')
      .replace(/&nbsp;/g, ' ')
      .trim()
      .slice(0, 150);

    posts.push({
      title: title.trim(),
      link: link.trim(),
      description: cleanDesc + (cleanDesc.length >= 150 ? '...' : ''),
      content: fullContent, // Full HTML content for modal
      date: formatDate(pubDate),
      category: category
    });
  }

  return posts;
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
