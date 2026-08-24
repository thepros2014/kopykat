import React from 'react';

export const MarketplaceConnectors: React.FC = () => {
  const connectors = [
    { name: 'Shopify', status: 'Available', stock: 'No store connected', type: 'Native' },
    { name: 'Amazon', status: 'Available', stock: 'No store connected', type: 'SP-API' },
    { name: 'Etsy', status: 'Available', stock: 'No store connected', type: 'OAuth 2.0' },
    { name: 'TikTok Shop', status: 'Available', stock: 'No store connected', type: 'Webhook' },
    { name: 'eBay', status: 'Available', stock: 'No store connected', type: 'REST API' }
  ];

  return (
    <div>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 800, margin: '0 0 8px 0' }}>Autonomous Marketplace Connectors</h1>
        <p style={{ color: '#9494a6', margin: 0, fontSize: '15px' }}>
          Supported connector capabilities are shown here; live inventory appears only after a merchant authorizes a store.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
        {connectors.map((c, i) => (
          <div key={i} style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0 }}>{c.name}</h3>
              <span style={{ fontSize: '11px', background: 'rgba(56,189,248,0.15)', color: '#38bdf8', border: '1px solid #38bdf8', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
                {c.status}
              </span>
            </div>

            <div style={{ fontSize: '13px', color: '#9494a6', marginBottom: '8px' }}>
              <strong>Inventory:</strong> {c.stock}
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
