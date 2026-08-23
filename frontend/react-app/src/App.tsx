import React, { useState, useEffect } from 'react';
import OverviewDashboard from './components/OverviewDashboard';
import OmniCampaignStudio from './components/OmniCampaignStudio';
import MarketplaceConnectors from './components/MarketplaceConnectors';
import AnalyticsStudio from './components/AnalyticsStudio';
import MRRAdminTelemetry from './components/MRRAdminTelemetry';

export type NavigationTab = 'overview' | 'campaigns' | 'connectors' | 'analytics' | 'admin-mrr';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavigationTab>('overview');
  const [userProfile, setUserProfile] = useState({
    name: 'Merchant Partner',
    plan: 'Standard Brand',
    campaignsRemaining: 842,
    monthlyLimit: 1000,
  });

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#09090b', color: '#f4f4f7' }}>
      {/* Sidebar Navigation */}
      <aside style={{ width: '260px', background: '#121217', borderRight: '1px solid #272730', padding: '24px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ fontSize: '20px', fontWeight: 800, color: '#fff', marginBottom: '32px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>KopyKat</span>
          <span style={{ fontSize: '11px', background: 'rgba(124,58,237,0.2)', border: '1px solid #7c3aed', color: '#a78bfa', padding: '2px 8px', borderRadius: '12px' }}>React 18</span>
        </div>

        <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
          <button
            onClick={() => setActiveTab('overview')}
            style={{
              padding: '12px 16px',
              borderRadius: '8px',
              textAlign: 'left',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
              background: activeTab === 'overview' ? 'rgba(124, 58, 237, 0.15)' : 'transparent',
              color: activeTab === 'overview' ? '#fff' : '#9494a6',
              borderLeft: activeTab === 'overview' ? '3px solid #7c3aed' : '3px solid transparent'
            }}
          >
            Dashboard Overview
          </button>

          <button
            onClick={() => setActiveTab('campaigns')}
            style={{
              padding: '12px 16px',
              borderRadius: '8px',
              textAlign: 'left',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
              background: activeTab === 'campaigns' ? 'rgba(124, 58, 237, 0.15)' : 'transparent',
              color: activeTab === 'campaigns' ? '#fff' : '#9494a6',
              borderLeft: activeTab === 'campaigns' ? '3px solid #7c3aed' : '3px solid transparent'
            }}
          >
            Omni-Campaign Studio
          </button>

          <button
            onClick={() => setActiveTab('connectors')}
            style={{
              padding: '12px 16px',
              borderRadius: '8px',
              textAlign: 'left',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
              background: activeTab === 'connectors' ? 'rgba(124, 58, 237, 0.15)' : 'transparent',
              color: activeTab === 'connectors' ? '#fff' : '#9494a6',
              borderLeft: activeTab === 'connectors' ? '3px solid #7c3aed' : '3px solid transparent'
            }}
          >
            Marketplace Connectors
          </button>

          <button
            onClick={() => setActiveTab('analytics')}
            style={{
              padding: '12px 16px',
              borderRadius: '8px',
              textAlign: 'left',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
              background: activeTab === 'analytics' ? 'rgba(124, 58, 237, 0.15)' : 'transparent',
              color: activeTab === 'analytics' ? '#fff' : '#9494a6',
              borderLeft: activeTab === 'analytics' ? '3px solid #7c3aed' : '3px solid transparent'
            }}
          >
            Growth & SEO Analytics
          </button>

          <button
            onClick={() => setActiveTab('admin-mrr')}
            style={{
              padding: '12px 16px',
              borderRadius: '8px',
              textAlign: 'left',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
              background: activeTab === 'admin-mrr' ? 'rgba(124, 58, 237, 0.15)' : 'transparent',
              color: activeTab === 'admin-mrr' ? '#fff' : '#9494a6',
              borderLeft: activeTab === 'admin-mrr' ? '3px solid #7c3aed' : '3px solid transparent'
            }}
          >
            Institutional MRR Telemetry
          </button>
        </nav>

        <div style={{ padding: '16px', background: 'rgba(0,0,0,0.3)', borderRadius: '8px', border: '1px solid #272730' }}>
          <div style={{ fontSize: '12px', color: '#9494a6' }}>Current Plan</div>
          <div style={{ fontSize: '14px', fontWeight: 700, color: '#a78bfa' }}>{userProfile.plan}</div>
          <div style={{ fontSize: '12px', color: '#9494a6', marginTop: '6px' }}>
            {userProfile.campaignsRemaining} / {userProfile.monthlyLimit} Campaigns
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main style={{ flex: 1, padding: '40px', overflowY: 'auto' }}>
        {activeTab === 'overview' && <OverviewDashboard profile={userProfile} />}
        {activeTab === 'campaigns' && <OmniCampaignStudio />}
        {activeTab === 'connectors' && <MarketplaceConnectors />}
        {activeTab === 'analytics' && <AnalyticsStudio />}
        {activeTab === 'admin-mrr' && <MRRAdminTelemetry />}
      </main>
    </div>
  );
};

export default App;
