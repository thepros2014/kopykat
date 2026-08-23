import React, { useState } from 'react';

export const MarketplaceConnectors: React.FC = () => {
  const [connectors, setConnectors] = useState([
    { name: 'Shopify Store', status: 'Connected', stock: '942 SKUs', type: 'Native' },
    { name: 'Amazon Seller Central', status: 'Connected', stock: '614 SKUs', type: 'SP-API' },
    { name: 'Etsy Artisan Hub', status: 'Connected', stock: '128 SKUs', type: 'OAuth 2.0' },
    { name: 'TikTok Shop Merchant', status: 'Connected', stock: '210 SKUs', type: 'Webhook' },
    { name: 'eBay Merchant Portal', status: 'Connected', stock: '430 SKUs', type: 'REST API' }
  ]);

  return (
    <div>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 800, margin: '0 0 8px 0' }}>Autonomous Marketplace Connectors</h1>
        <p style={{ color: '#9494a6', margin: 0, fontSize: '15px' }}>
          Real-time inventory synchronization with SSRF protection and cryptographic webhook deduplication.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
        {connectors.map((c, i) => (
          <div key={i} style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0 }}>{c.name}</h3>
              <span style={{ fontSize: '11px', background: 'rgba(16,185,129,0.15)', color: '#10b981', border: '1px solid #10b981', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
                {c.status}
              </span>
            </div>

            <div style={{ fontSize: '13px', color: '#9494a6', marginBottom: '8px' }}>
              <strong>Synced Inventory:</strong> {c.stock}
            </div>
            <div style={{ fontSize: '13px', color: '#9494a6', marginBottom: '16px' }}>
              <strong>Protocol:</strong> {c.type} (SafeAsyncHTTPClient)
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <button style={{ flex: 1, padding: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid #272730', borderRadius: '6px', color: '#fff', fontSize: '12px', cursor: 'pointer' }}>
                Test Connection
              </button>
              <button style={{ flex: 1, padding: '8px', background: 'rgba(124,58,237,0.15)', border: '1px solid #7c3aed', borderRadius: '6px', color: '#c4b5fd', fontSize: '12px', cursor: 'pointer' }}>
                Reconcile Drift
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default MarketplaceConnectors;
