import React, { useState } from 'react';

export const AnalyticsStudio: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'seo' | 'drip' | 'leads' | 'margins'>('seo');

  return (
    <div>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 800, margin: '0 0 8px 0' }}>Growth & Performance Analytics</h1>
        <p style={{ color: '#9494a6', margin: 0, fontSize: '15px' }}>
          Deep-dive telemetry across SEO organic search, post-purchase email sequences, and Reddit opportunity discovery.
        </p>
      </div>

      {/* Analytics Tabs */}
      <div style={{ display: 'flex', gap: '12px', borderBottom: '1px solid #272730', paddingBottom: '12px', marginBottom: '24px' }}>
        <button
          onClick={() => setActiveTab('seo')}
          style={{
            padding: '8px 18px',
            borderRadius: '8px',
            border: 'none',
            fontWeight: 600,
            cursor: 'pointer',
            background: activeTab === 'seo' ? '#7c3aed' : 'rgba(255,255,255,0.05)',
            color: activeTab === 'seo' ? '#fff' : '#9494a6'
          }}
        >
          SEO Blog & Organic Traffic
        </button>

        <button
          onClick={() => setActiveTab('drip')}
          style={{
            padding: '8px 18px',
            borderRadius: '8px',
            border: 'none',
            fontWeight: 600,
            cursor: 'pointer',
            background: activeTab === 'drip' ? '#7c3aed' : 'rgba(255,255,255,0.05)',
            color: activeTab === 'drip' ? '#fff' : '#9494a6'
          }}
        >
          Post-Purchase Email Sequences
        </button>

        <button
          onClick={() => setActiveTab('leads')}
          style={{
            padding: '8px 18px',
            borderRadius: '8px',
            border: 'none',
            fontWeight: 600,
            cursor: 'pointer',
            background: activeTab === 'leads' ? '#7c3aed' : 'rgba(255,255,255,0.05)',
            color: activeTab === 'leads' ? '#fff' : '#9494a6'
          }}
        >
          Reddit & Social Lead Discovery
        </button>

        <button
          onClick={() => setActiveTab('margins')}
          style={{
            padding: '8px 18px',
            borderRadius: '8px',
            border: 'none',
            fontWeight: 600,
            cursor: 'pointer',
            background: activeTab === 'margins' ? '#7c3aed' : 'rgba(255,255,255,0.05)',
            color: activeTab === 'margins' ? '#fff' : '#9494a6'
          }}
        >
          Profit Margin & Marketplace Fees
        </button>
      </div>

      {/* Tab 1: SEO Analytics */}
      {activeTab === 'seo' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px', marginBottom: '24px' }}>
            <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
              <div style={{ fontSize: '13px', color: '#9494a6' }}>Published SEO Articles</div>
              <div style={{ fontSize: '28px', fontWeight: 800, color: '#38bdf8', marginTop: '6px' }}>48 Posts</div>
              <div style={{ fontSize: '12px', color: '#10b981', marginTop: '4px' }}>+12 this month</div>
            </div>
            <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
              <div style={{ fontSize: '13px', color: '#9494a6' }}>Estimated Monthly Organic Visits</div>
              <div style={{ fontSize: '28px', fontWeight: 800, color: '#10b981', marginTop: '6px' }}>18,420</div>
              <div style={{ fontSize: '12px', color: '#10b981', marginTop: '4px' }}>+34.2% MoM growth</div>
            </div>
            <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
              <div style={{ fontSize: '13px', color: '#9494a6' }}>Google Indexing Rate</div>
              <div style={{ fontSize: '28px', fontWeight: 800, color: '#a78bfa', marginTop: '6px' }}>96.8%</div>
              <div style={{ fontSize: '12px', color: '#9494a6', marginTop: '4px' }}>Automated sitemap pings</div>
            </div>
          </div>

          <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '24px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '16px' }}>Top Ranking Automated Blog Posts</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {[
                { title: 'The Complete Guide to Choosing Leak-Proof Travel Tumblers', visits: '4,280 visits', ctr: '4.8%' },
                { title: 'How to Prevent Stainless Steel Coffee Tumbler Odors', visits: '3,120 visits', ctr: '5.2%' },
                { title: 'Top 5 Eco-Friendly Gift Ideas for Office Commuters', visits: '2,890 visits', ctr: '3.9%' }
              ].map((post, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 16px', background: 'rgba(0,0,0,0.3)', borderRadius: '8px', border: '1px solid #272730' }}>
                  <span style={{ fontSize: '14px', fontWeight: 500 }}>{post.title}</span>
                  <div style={{ display: 'flex', gap: '20px', fontSize: '13px', color: '#9494a6' }}>
                    <span style={{ color: '#38bdf8' }}>{post.visits}</span>
                    <span style={{ color: '#10b981' }}>CTR: {post.ctr}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Drip Analytics */}
      {activeTab === 'drip' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px', marginBottom: '24px' }}>
            <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
              <div style={{ fontSize: '13px', color: '#9494a6' }}>Sequence Open Rate</div>
              <div style={{ fontSize: '28px', fontWeight: 800, color: '#10b981', marginTop: '6px' }}>64.2%</div>
              <div style={{ fontSize: '12px', color: '#9494a6', marginTop: '4px' }}>Industry average: 28.5%</div>
            </div>
            <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
              <div style={{ fontSize: '13px', color: '#9494a6' }}>Click-Through Rate</div>
              <div style={{ fontSize: '28px', fontWeight: 800, color: '#38bdf8', marginTop: '6px' }}>28.4%</div>
              <div style={{ fontSize: '12px', color: '#10b981', marginTop: '4px' }}>High purchase intent</div>
            </div>
            <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
              <div style={{ fontSize: '13px', color: '#9494a6' }}>Repeat Revenue Generated</div>
              <div style={{ fontSize: '28px', fontWeight: 800, color: '#f472b6', marginTop: '6px' }}>$4,120</div>
              <div style={{ fontSize: '12px', color: '#10b981', marginTop: '4px' }}>Attributed to automated drips</div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Reddit Leads */}
      {activeTab === 'leads' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px', marginBottom: '24px' }}>
            <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
              <div style={{ fontSize: '13px', color: '#9494a6' }}>Monitored Discussions</div>
              <div style={{ fontSize: '28px', fontWeight: 800, color: '#a78bfa', marginTop: '6px' }}>142 Threads</div>
              <div style={{ fontSize: '12px', color: '#9494a6', marginTop: '4px' }}>Non-blocking async scout</div>
            </div>
            <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
              <div style={{ fontSize: '13px', color: '#9494a6' }}>High-Intent Leads Found</div>
              <div style={{ fontSize: '28px', fontWeight: 800, color: '#10b981', marginTop: '6px' }}>38 Buyers</div>
              <div style={{ fontSize: '12px', color: '#10b981', marginTop: '4px' }}>Seeking product recommendations</div>
            </div>
            <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
              <div style={{ fontSize: '13px', color: '#9494a6' }}>Draft Reply Conversion</div>
              <div style={{ fontSize: '28px', fontWeight: 800, color: '#38bdf8', marginTop: '6px' }}>22.5%</div>
              <div style={{ fontSize: '12px', color: '#10b981', marginTop: '4px' }}>Authentic helpful replies</div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Profit Margins */}
      {activeTab === 'margins' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px', marginBottom: '24px' }}>
            <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
              <div style={{ fontSize: '13px', color: '#9494a6' }}>Average Net Margin</div>
              <div style={{ fontSize: '28px', fontWeight: 800, color: '#10b981', marginTop: '6px' }}>44.2%</div>
              <div style={{ fontSize: '12px', color: '#9494a6', marginTop: '4px' }}>After all platform & ad fees</div>
            </div>
            <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
              <div style={{ fontSize: '13px', color: '#9494a6' }}>Fee Breakdown Tracked</div>
              <div style={{ fontSize: '28px', fontWeight: 800, color: '#f59e0b', marginTop: '6px' }}>15.3%</div>
              <div style={{ fontSize: '12px', color: '#9494a6', marginTop: '4px' }}>Amazon/TikTok/Shopify fees</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AnalyticsStudio;
