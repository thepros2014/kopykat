import React, { useState } from 'react';

type AnalyticsTab = 'seo' | 'drip' | 'leads' | 'margins';

const tabLabels: Record<AnalyticsTab, string> = {
  seo: 'SEO Blog & Organic Traffic',
  drip: 'Post-Purchase Email Sequences',
  leads: 'Reddit & Social Lead Discovery',
  margins: 'Profit Margin & Marketplace Fees',
};

const descriptions: Record<AnalyticsTab, string> = {
  seo: 'SEO publication and search-console telemetry will appear after a site and measurement property are connected.',
  drip: 'Message delivery and conversion telemetry will appear after an email provider and customer event source are connected.',
  leads: 'Lead discovery telemetry will appear after a monitored source and an approved campaign are configured.',
  margins: 'Margin telemetry will appear after catalog cost, price, and marketplace fee inputs are recorded.',
};

export const AnalyticsStudio: React.FC = () => {
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('seo');

  return (
    <div>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 800, margin: '0 0 8px 0' }}>Growth & Performance Analytics</h1>
        <p style={{ color: '#9494a6', margin: 0, fontSize: '15px' }}>
          Only measured events are reported. Unconfigured sources remain explicitly empty.
        </p>
      </div>

      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', borderBottom: '1px solid #272730', paddingBottom: '12px', marginBottom: '24px' }}>
        {(Object.keys(tabLabels) as AnalyticsTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '8px 18px',
              borderRadius: '8px',
              border: 'none',
              fontWeight: 600,
              cursor: 'pointer',
              background: activeTab === tab ? '#7c3aed' : 'rgba(255,255,255,0.05)',
              color: activeTab === tab ? '#fff' : '#9494a6',
            }}
          >
            {tabLabels[tab]}
          </button>
        ))}
      </div>

      <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '32px', minHeight: '240px' }}>
        <div style={{ display: 'inline-flex', padding: '4px 10px', borderRadius: '999px', background: 'rgba(245,158,11,0.15)', color: '#fbbf24', border: '1px solid #f59e0b', fontSize: '12px', fontWeight: 700 }}>
          AWAITING DATA SOURCE
        </div>
        <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '18px 0 10px' }}>{tabLabels[activeTab]}</h2>
        <p style={{ color: '#9494a6', margin: 0, maxWidth: '700px', lineHeight: 1.6 }}>{descriptions[activeTab]}</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginTop: '28px' }}>
          {['Events recorded', 'Conversion rate', 'Attributed revenue'].map((label) => (
            <div key={label} style={{ background: 'rgba(0,0,0,0.25)', border: '1px solid #272730', borderRadius: '8px', padding: '16px' }}>
              <div style={{ color: '#9494a6', fontSize: '12px', textTransform: 'uppercase' }}>{label}</div>
              <div style={{ color: '#fff', fontSize: '24px', fontWeight: 800, marginTop: '8px' }}>Not available</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default AnalyticsStudio;
