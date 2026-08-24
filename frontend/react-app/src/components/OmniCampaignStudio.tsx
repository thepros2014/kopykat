import React, { useState } from 'react';

type Channel = 'amazon' | 'shopify' | 'etsy' | 'tiktok' | 'ebay';

interface CampaignAssets {
  blog_post?: { title?: string; content?: string };
  email_drip?: Array<{ subject?: string; body?: string }>;
  social_posts?: string[];
}

const channels: Channel[] = ['amazon', 'shopify', 'etsy', 'tiktok', 'ebay'];

function plainText(value: string | undefined): string {
  if (!value) return '';
  const parsed = new DOMParser().parseFromString(value, 'text/html');
  return parsed.body.textContent?.trim() || '';
}

async function readError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    const detail = Array.isArray(payload.detail) ? payload.detail[0]?.msg : payload.detail;
    return detail || 'Campaign generation failed.';
  } catch {
    return 'Campaign generation failed.';
  }
}

export const OmniCampaignStudio: React.FC = () => {
  const [productName, setProductName] = useState('');
  const [productContext, setProductContext] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedChannel, setSelectedChannel] = useState<Channel>('amazon');
  const [campaign, setCampaign] = useState<CampaignAssets | null>(null);
  const [error, setError] = useState('');

  const generateCampaign = async () => {
    const keyword = productName.trim();
    const productDesc = productContext.trim();
    if (!keyword || !productDesc) {
      setError('Enter a product name and product context before generating.');
      return;
    }

    const token = localStorage.getItem('sc_token');
    if (!token) {
      setError('Sign in before generating a campaign.');
      return;
    }

    setIsGenerating(true);
    setError('');
    setCampaign(null);
    try {
      const response = await fetch('/api/campaign/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer ' + token,
        },
        body: JSON.stringify({ keyword, product_desc: productDesc }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const payload = await response.json();
      setCampaign(payload.assets || null);
      if (!payload.assets) setError('The API returned no campaign assets.');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Campaign generation failed.');
    } finally {
      setIsGenerating(false);
    }
  };

  const blogTitle = campaign?.blog_post?.title || 'No blog asset returned';
  const blogContent = plainText(campaign?.blog_post?.content);
  const emails = campaign?.email_drip || [];
  const socialPosts = campaign?.social_posts || [];

  return (
    <div>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 800, margin: '0 0 8px 0' }}>Multi-Modal Omni-Campaign Studio</h1>
        <p style={{ color: '#9494a6', margin: 0, fontSize: '15px' }}>
          Generate reviewable campaign assets from the production API. Nothing is published automatically.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: '30px' }}>
        <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '24px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '16px' }}>Product Input Details</h3>
          <label style={{ display: 'block', fontSize: '13px', color: '#9494a6', marginBottom: '6px' }} htmlFor="react-product-name">
            Product Name or Title
          </label>
          <input
            id="react-product-name"
            type="text"
            value={productName}
            onChange={(event) => setProductName(event.target.value)}
            placeholder="e.g. Stainless Steel Insulated Travel Tumbler"
            style={{ width: '100%', padding: '10px 14px', background: 'rgba(0,0,0,0.3)', border: '1px solid #272730', borderRadius: '8px', color: '#fff', marginBottom: '16px' }}
          />

          <label style={{ display: 'block', fontSize: '13px', color: '#9494a6', marginBottom: '6px' }} htmlFor="react-product-context">
            Product Context and Selling Angle
          </label>
          <textarea
            id="react-product-context"
            value={productContext}
            onChange={(event) => setProductContext(event.target.value)}
            placeholder="Describe verified features, audience, and positioning."
            rows={5}
            style={{ width: '100%', padding: '10px 14px', background: 'rgba(0,0,0,0.3)', border: '1px solid #272730', borderRadius: '8px', color: '#fff', marginBottom: '20px' }}
          />

          <button
            onClick={generateCampaign}
            disabled={isGenerating}
            style={{ width: '100%', background: isGenerating ? '#4c1d95' : 'linear-gradient(135deg, #7c3aed 0%, #9333ea 100%)', color: '#fff', border: 'none', borderRadius: '8px', padding: '14px', fontWeight: 700, cursor: isGenerating ? 'wait' : 'pointer' }}
          >
            {isGenerating ? 'Generating from API...' : 'Generate Reviewable Campaign'}
          </button>
          {error && <p role="alert" style={{ color: '#fca5a5', fontSize: '13px', marginTop: '14px' }}>{error}</p>}
        </div>

        <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '24px' }}>
          <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid #272730', paddingBottom: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
            {channels.map((channel) => (
              <button
                key={channel}
                onClick={() => setSelectedChannel(channel)}
                aria-pressed={selectedChannel === channel}
                style={{
                  padding: '6px 14px',
                  borderRadius: '6px',
                  border: 'none',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  textTransform: 'capitalize',
                  background: selectedChannel === channel ? '#7c3aed' : 'rgba(255,255,255,0.05)',
                  color: selectedChannel === channel ? '#fff' : '#9494a6',
                }}
              >
                {channel}
              </button>
            ))}
          </div>

          {!campaign ? (
            <div style={{ border: '1px dashed #4c1d95', borderRadius: '8px', padding: '24px', color: '#9494a6', lineHeight: 1.6 }}>
              <strong style={{ color: '#fff' }}>No preview generated.</strong>
              <p style={{ margin: '8px 0 0' }}>
                Enter source details and generate from the API. The selected {selectedChannel} tab is a review context only until a marketplace-specific adapter returns data.
              </p>
            </div>
          ) : (
            <div>
              <div style={{ fontSize: '13px', color: '#38bdf8', fontWeight: 700, marginBottom: '6px' }}>
                Generated source assets for {selectedChannel}
              </div>
              <h3 style={{ fontSize: '17px', margin: '0 0 12px' }}>{blogTitle}</h3>
              <p style={{ fontSize: '13px', color: '#c4c4d0', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                {blogContent || 'No blog content returned.'}
              </p>

              {emails.length > 0 && (
                <div style={{ borderTop: '1px solid #272730', marginTop: '20px', paddingTop: '16px' }}>
                  <h4 style={{ margin: '0 0 10px', fontSize: '14px' }}>Email assets</h4>
                  {emails.slice(0, 5).map((email, index) => (
                    <div key={(email.subject || 'email') + '-' + index} style={{ marginBottom: '12px', color: '#9494a6', fontSize: '13px' }}>
                      <strong style={{ color: '#fff' }}>{email.subject || 'Email ' + (index + 1)}</strong>
                      <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{plainText(email.body)}</div>
                    </div>
                  ))}
                </div>
              )}

              {socialPosts.length > 0 && (
                <div style={{ borderTop: '1px solid #272730', marginTop: '20px', paddingTop: '16px' }}>
                  <h4 style={{ margin: '0 0 10px', fontSize: '14px' }}>Social assets</h4>
                  {socialPosts.slice(0, 5).map((post, index) => (
                    <p key={post + '-' + index} style={{ color: '#9494a6', fontSize: '13px', lineHeight: 1.5, margin: '0 0 8px' }}>
                      {post}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default OmniCampaignStudio;
