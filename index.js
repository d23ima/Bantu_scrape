import { useState, useEffect } from 'react';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
);

export default function Home() {
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchArticles();
  }, []);

  async function fetchArticles() {
    const { data, error } = await supabase
      .from('articles')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(50);
    if (error) console.error(error);
    else setArticles(data);
    setLoading(false);
  }

  const copyAsText = () => {
    const text = articles.map(a => 
      `• ${a.title}\n  Source: ${a.source_name}\n  Original: ${a.primary_source_url || a.url}\n  Summary: ${a.summary}\n`
    ).join('\n');
    navigator.clipboard.writeText(text);
    alert('Copied to clipboard!');
  };

  if (loading) return <div>Loading...</div>;

  return (
    <div style={{ padding: '20px', maxWidth: '800px', margin: 'auto' }}>
      <h1>Positive Africa News</h1>
      <button onClick={copyAsText} style={{ marginBottom: '20px' }}>
        Copy all as text
      </button>
      {articles.map(article => (
        <div key={article.id} style={{ borderBottom: '1px solid #ccc', marginBottom: '15px', paddingBottom: '10px' }}>
          <h3>{article.title}</h3>
          <p><strong>Source:</strong> {article.source_name}</p>
          <p><strong>Published:</strong> {new Date(article.published_at).toLocaleDateString()}</p>
          <p><strong>Summary:</strong> {article.summary}</p>
          <p>
            <strong>Original source:</strong>{' '}
            <a href={article.primary_source_url || article.url} target="_blank" rel="noopener noreferrer">
              {article.primary_source_url || article.url}
            </a>
          </p>
        </div>
      ))}
    </div>
  );
}
