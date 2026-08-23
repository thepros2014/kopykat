import React, { useState } from 'react';

export const OmniCampaignStudio: React.FC = () => {
  const [productName, setProductName] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedChannel, setSelectedChannel] = useState<'amazon' | 'shopify' | 'etsy' | 'tiktok' | 'ebay'>('amazon');

  return (
    <div>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 800, margin: '0 0 8px 0' }}>Multi-Modal Omni-Campaign Studio</h1>
        <p style={{ color: '#9494a6', margin: 0, fontSize: '15px' }}>
          Generate platform-compliant, structured copy for all 5 e-commerce channels simultaneously.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: '30px' }}>
        {/* Input Panel */}
        <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '24px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '16px' }}>Product Input Details</h3>
          
          <label style={{ display: 'block', fontSize: '13px', color: '#9494a6', marginBottom: '6px' }}>Product Name or Title</label>
          <input
            type="text"
            value={productName}
            onChange={(e) => setProductName(e.target.value)}
            placeholder="e.g. Stainless Steel Insulated Travel Tumbler"
            style={{ width: '100%', padding: '10px 14px', background: 'rgba(0,0,0,0.3)', border: '1px solid #272730', borderRadius: '8px', color: '#fff', marginBottom: '16px' }}
          />

          <label style={{ display: 'block', fontSize: '13px', color: '#9494a6', marginBottom: '6px' }}>Target Audience & Selling Angle</label>
          <textarea
            placeholder="e.g. Busy commuters who need 24-hour temperature retention with leak-proof lid."
            rows={4}
            style={{ width: '100%', padding: '10px 14px', background: 'rgba(0,0,0,0.3)', border: '1px solid #272730', borderRadius: '8px', color: '#fff', marginBottom: '20px' }}
          />

          <button
            onClick={() => setIsGenerating(true)}
            style={{ width: '100%', background: 'linear-gradient(135deg, #7c3aed 0%, #9333ea 100%)', color: '#fff', border: 'none', borderRadius: '8px', padding: '14px', fontWeight: 700, cursor: 'pointer' }}
          >
            {isGenerating ? 'Generating 5 Channel Schemas...' : 'Generate 5-Channel Campaign'}
          </button>
        </div>

        {/* Channel Preview Panel */}
        <div style={{ background: '#121217', border: '1px solid #272730', borderRadius: '12px', padding: '24px' }}>
          <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid #272730', paddingBottom: '12px', marginBottom: '16px' }}>
            {(['amazon', 'shopify', 'etsy', 'tiktok', 'ebay'] as const).map((channel) => (
              <button
                key={channel}
                onClick={() => setSelectedChannel(channel)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '6px',
                  border: 'none',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  textTransform: 'capitalize',
                  background: selectedChannel === channel ? '#7c3aed' : 'rgba(255,255,255,0.05)',
                  color: selectedChannel === channel ? '#fff' : '#9494a6'
                }}
              >
                {channel}
              </button>
            ))}
          </div>

          {selectedChannel === 'amazon' && (
            <div>
              <div style={{ fontSize: '13px', color: '#38bdf8', fontWeight: 700, marginBottom: '6px' }}>[Amazon Listing Format]</div>
              <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px' }}>
                Premium Insulated Stainless Steel Tumbler 32oz - 24Hr Cold Retention with Leak-Proof Straw Lid
              </div>
              <ul style={{ fontSize: '13px', color: '#9494a6', lineHeight: 1.6, paddingLeft: '20px' }}>
                <li>24-HOUR VACUUM INSULATION: Keeps beverages ice cold all day.</li>
                <li>100% LEAK-PROOF SPILL RESISTANT: Engineered seal for commute & travel.</li>
                <li>DURABLE 18/8 FOOD GRADE STEEL: Zero metallic taste, BPA-free.</li>
                <li>CUPHOLDER FRIENDLY DESIGN: Fits standard vehicle holders easily.</li>
                <li>EASY CLEAN & DISHWASHER SAFE: Detachable lid with bonus straw brush.</li>
              </ul>
            </div>
          )}

          {selectedChannel === 'shopify' && (
            <div>
              <div style={{ fontSize: '13px', color: '#10b981', fontWeight: 700, marginBottom: '6px' }}>[Shopify Brand Story & HTML]</div>
              <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px' }}>The Ultimate All-Day Travel Tumbler (32 oz)</div>
              <p style={{ fontSize: '13px', color: '#9494a6', lineHeight: 1.6 }}>
                Meet the tumbler engineered for morning commutes, weekend trail adventures, and all-day desk hydration.
                Built with triple-walled insulation, it locks in icy freshness for 24+ hours.
              </p>
            </div>
          )}

          {selectedChannel === 'etsy' && (
            <div>
              <div style={{ fontSize: '13px', color: '#f59e0b', fontWeight: 700, marginBottom: '6px' }}>[Etsy Artisan Schema & 13 Tags]</div>
              <p style={{ fontSize: '13px', color: '#9494a6', lineHeight: 1.6 }}>
                Hand-finished laser engraved stainless steel water bottle. Eco-friendly, reusable, perfect wedding party or holiday gift.
              </p>
              <div style={{ fontSize: '12px', color: '#a78bfa', marginTop: '10px' }}>
                <strong>13 Search Tags:</strong> travel tumbler, insulated mug, gift for commuter, reusable cup, engraved flask, 32oz bottle, coffee tumbler, metal flask, cold drink holder, gym bottle, iced coffee cup, teacher gift, custom flask.
              </div>
            </div>
          )}

          {selectedChannel === 'tiktok' && (
            <div>
              <div style={{ fontSize: '13px', color: '#ec4899', fontWeight: 700, marginBottom: '6px' }}>[TikTok Shop 30-Second Viral Script]</div>
              <p style={{ fontSize: '13px', color: '#9494a6', lineHeight: 1.6 }}>
                <strong>Hook (0-3s):</strong> "Stop throwing your money away on ice coffee that melts in 20 minutes!"<br/>
                <strong>Visual Demo (3-15s):</strong> Pour hot coffee into cup, flip upside down over white shirt with zero drips.<br/>
                <strong>Call to Action (15-30s):</strong> "Click the orange basket below before the 40% flash deal ends."
              </p>
            </div>
          )}

          {selectedChannel === 'ebay' && (
            <div>
              <div style={{ fontSize: '13px', color: '#a855f7', fontWeight: 700, marginBottom: '6px' }}>[eBay 80-Char Strict Title & Item Specifics]</div>
              <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>
                Insulated Stainless Steel Travel Tumbler 32oz Leakproof Lid Hot Cold Mug
              </div>
              <div style={{ fontSize: '12px', color: '#9494a6', lineHeight: 1.6 }}>
                Capacity: 32 oz | Material: 18/8 Stainless Steel | Features: Double Wall, Leak Proof | Type: Travel Mug
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default OmniCampaignStudio;
