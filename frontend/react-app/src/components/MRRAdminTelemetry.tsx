import React, { useEffect, useState } from 'react';

interface PublicMetrics {
  total_campaigns_generated: number;
  supported_marketplaces_count: number;
  active_subscribers_mrr_usd: number;
  estimated_seller_hours_saved: number;
  platform_uptime_pct: number | null;
}

const formatCurrency = (value: number) => value.toLocaleString(undefined, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export const MRRAdminTelemetry: React.FC = () => {
  const [metrics, setMetrics] = useState<PublicMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/metrics/summary', {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error('Metrics endpoint unavailable.');
        return response.json() as Promise<PublicMetrics>;
      })
      .then(setMetrics)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return;
        setError(reason instanceof Error ? reason.message : 'Unable to load metrics.');
      });

    return () => controller.abort();
  }, []);

  const metricValue = (value: number | undefined) => value === undefined ? '—' : value.toLocaleString();

  return (
    <div>
      <div style={{ marginBottom: '32px' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: 'rgba(56,189,248,0.15)', color: '#38bdf8', border: '1px solid #38bdf8', padding: '4px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: 700, marginBottom: '12px' }}>
          VERIFIED PLATFORM METRICS
        </div>
        <h1 style={{ fontSize: '28px', fontWeight: 800, margin: '0 0 8px 0' }}>Executive Operations Dashboard</h1>
        <p style={{ color: '#9494a6', margin: 0, fontSize: '15px' }}>
          This view reports persisted application telemetry. Uninstrumented metrics stay unavailable instead of being estimated.
        </p>
      </div>

      {error && (
        <div role="alert" style={{ background: 'rgba(239,68,68,0.12)', border: '1px solid #ef4444', color: '#fca5a5', borderRadius: '8px', padding: '12px 16px', marginBottom: '20px' }}>
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px', marginBottom: '32px' }}>
        <div style={{ background: '#121217', border: '2px solid #10b981', borderRadius: '12px', padding: '24px' }}>
          <div style={{ fontSize: '13px', color: '#9494a6', textTransform: 'uppercase' }}>Verified MRR</div>
          <div style={{ fontSize: '36px', fontWeight: 800, color: '#10b981', marginTop: '6px' }}>
            ${metrics ? formatCurrency(metrics.active_subscribers_mrr_usd) : '—'}
          </div>
          <div style={{ fontSize: '12px', color: '#9494a6', marginTop: '6px' }}>Active billing state only</div>
        </div>

        <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '24px' }}>
          <div style={{ fontSize: '13px', color: '#9494a6', textTransform: 'uppercase' }}>Recorded Campaigns</div>
          <div style={{ fontSize: '36px', fontWeight: 800, color: '#38bdf8', marginTop: '6px' }}>
            {metricValue(metrics?.total_campaigns_generated)}
          </div>
          <div style={{ fontSize: '12px', color: '#9494a6', marginTop: '6px' }}>Database-backed count</div>
        </div>

        <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '24px' }}>
          <div style={{ fontSize: '13px', color: '#9494a6', textTransform: 'uppercase' }}>Native Marketplaces</div>
          <div style={{ fontSize: '36px', fontWeight: 800, color: '#a78bfa', marginTop: '6px' }}>
            {metricValue(metrics?.supported_marketplaces_count)}
          </div>
          <div style={{ fontSize: '12px', color: '#9494a6', marginTop: '6px' }}>Registered connector capabilities</div>
        </div>

        <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '24px' }}>
          <div style={{ fontSize: '13px', color: '#9494a6', textTransform: 'uppercase' }}>Estimated Hours Saved</div>
          <div style={{ fontSize: '36px', fontWeight: 800, color: '#f472b6', marginTop: '6px' }}>
            {metricValue(metrics?.estimated_seller_hours_saved)}
          </div>
          <div style={{ fontSize: '12px', color: '#9494a6', marginTop: '6px' }}>Derived from recorded campaigns</div>
        </div>
      </div>

      <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '24px' }}>
        <h2 style={{ fontSize: '18px', fontWeight: 700, margin: '0 0 12px 0' }}>Measurement status</h2>
        <p style={{ color: '#9494a6', margin: 0, lineHeight: 1.6 }}>
          Uptime, valuation, retention, acquisition cost, and margin remain <strong style={{ color: '#fff' }}>not available</strong> until their source systems and collection windows are configured. The protected admin API contains billing detail; this public dashboard never invents customer or revenue data.
        </p>
        <div style={{ marginTop: '16px', color: '#9494a6', fontSize: '14px' }}>
          Uptime monitor: <strong style={{ color: '#fff' }}>{metrics?.platform_uptime_pct === null || metrics?.platform_uptime_pct === undefined ? 'Not instrumented' : `${metrics.platform_uptime_pct}%`}</strong>
        </div>
      </div>
    </div>
  );
};

export default MRRAdminTelemetry;
