import React from 'react';

interface Props {
  profile: {
    name: string;
    plan: string;
    campaignsRemaining: number;
    monthlyLimit: number;
  };
}

export const OverviewDashboard: React.FC<Props> = ({ profile }) => {
  return (
    <div>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 800, margin: '0 0 8px 0' }}>Welcome back, {profile.name}</h1>
        <p style={{ color: '#9494a6', margin: 0, fontSize: '15px' }}>
          Here is your autonomous e-commerce syndication pipeline at a glance.
        </p>
      </div>

      {/* KPI Stats Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px', marginBottom: '32px' }}>
        <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
          <div style={{ fontSize: '13px', color: '#9494a6', textTransform: 'uppercase' }}>Active Channels</div>
          <div style={{ fontSize: '32px', fontWeight: 800, color: '#38bdf8', marginTop: '8px' }}>5 Stores</div>
          <div style={{ fontSize: '12px', color: '#10b981', marginTop: '4px' }}>Shopify, Amazon, Etsy, TikTok, eBay</div>
        </div>

        <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
          <div style={{ fontSize: '13px', color: '#9494a6', textTransform: 'uppercase' }}>Campaigns Remaining</div>
          <div style={{ fontSize: '32px', fontWeight: 800, color: '#a78bfa', marginTop: '8px' }}>{profile.campaignsRemaining}</div>
          <div style={{ fontSize: '12px', color: '#9494a6', marginTop: '4px' }}>Resets on 1st of each month</div>
        </div>

        <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
          <div style={{ fontSize: '13px', color: '#9494a6', textTransform: 'uppercase' }}>Inventory Sync Status</div>
          <div style={{ fontSize: '32px', fontWeight: 800, color: '#10b981', marginTop: '8px' }}>100% Live</div>
          <div style={{ fontSize: '12px', color: '#10b981', marginTop: '4px' }}>Zero oversell drift detected</div>
        </div>

        <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '20px' }}>
          <div style={{ fontSize: '13px', color: '#9494a6', textTransform: 'uppercase' }}>Time Saved This Month</div>
          <div style={{ fontSize: '32px', fontWeight: 800, color: '#f472b6', marginTop: '8px' }}>42.5 Hours</div>
          <div style={{ fontSize: '12px', color: '#9494a6', marginTop: '4px' }}>Replaced manual copywriting</div>
        </div>
      </div>

      {/* Quick Launch Card */}
      <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '28px', marginBottom: '32px' }}>
        <h2 style={{ fontSize: '18px', fontWeight: 700, margin: '0 0 12px 0' }}>Launch Multi-Marketplace Omni-Campaign</h2>
        <p style={{ color: '#9494a6', fontSize: '14px', marginBottom: '20px' }}>
          Input product details once to automatically generate verified listings for Amazon, Shopify, Etsy, TikTok Shop, and eBay.
        </p>
        <div style={{ display: 'flex', gap: '16px' }}>
          <input
            type="text"
            placeholder="e.g. Ergonomic Memory Foam Pillow with Cooling Gel"
            style={{ flex: 1, padding: '12px 16px', background: 'rgba(0,0,0,0.3)', border: '1px solid #272730', borderRadius: '8px', color: '#fff' }}
          />
          <button style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #9333ea 100%)', color: '#fff', border: 'none', borderRadius: '8px', padding: '12px 24px', fontWeight: 600, cursor: 'pointer' }}>
            Generate All 5 Channels
          </button>
        </div>
      </div>
    </div>
  );
};

export default OverviewDashboard;
