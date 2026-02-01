'use client';

import React from 'react';

const BRAND_COLORS = [
  { name: 'Visa Blue', hex: '#003399', usage: 'Primary brand, CTAs, links' },
  { name: 'Visa Gold', hex: '#F7B600', usage: 'In-plan state, accents' },
  { name: 'Slate Trust 50', hex: '#f8fafc', usage: 'Backgrounds' },
  { name: 'Slate Trust 200', hex: '#e2e8f0', usage: 'Borders' },
  { name: 'Slate Trust 500', hex: '#64748b', usage: 'Muted text' },
  { name: 'Slate Trust 900', hex: '#0f172a', usage: 'Body text' },
];

export default function StyleGuide() {
  return (
    <div className="min-h-screen bg-slate-trust-50 p-8 font-sans">
      <h1 className="font-heading text-3xl font-bold text-slate-trust-900 mb-8">
        Common Ground Design System
      </h1>

      <section className="mb-12">
        <h2 className="font-heading text-xl font-bold text-slate-trust-900 mb-4">
          Brand Colors
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {BRAND_COLORS.map((c) => (
            <div
              key={c.hex}
              className="rounded-xl border border-slate-trust-200 overflow-hidden bg-white shadow-sm"
            >
              <div
                className="h-24 w-full"
                style={{ backgroundColor: c.hex }}
              />
              <div className="p-3">
                <p className="font-heading font-bold text-slate-trust-900">{c.name}</p>
                <p className="font-mono text-sm text-slate-trust-500">{c.hex}</p>
                <p className="text-xs text-slate-trust-500 mt-1">{c.usage}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-12">
        <h2 className="font-heading text-xl font-bold text-slate-trust-900 mb-4">
          Typography
        </h2>
        <div className="space-y-4 rounded-xl border border-slate-trust-200 bg-white p-6">
          <div>
            <p className="text-xs text-slate-trust-500 uppercase tracking-wider mb-1">Heading (Plus Jakarta Sans)</p>
            <h1 className="font-heading text-2xl font-bold text-slate-trust-900">Heading 1</h1>
            <h2 className="font-heading text-xl font-bold text-slate-trust-900">Heading 2</h2>
            <h3 className="font-heading text-lg font-bold text-slate-trust-900">Heading 3</h3>
          </div>
          <div>
            <p className="text-xs text-slate-trust-500 uppercase tracking-wider mb-1">Body (Inter)</p>
            <p className="text-slate-trust-900">
              Body text uses Inter for readability across the app.
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-trust-500 uppercase tracking-wider mb-1">Prices (JetBrains Mono)</p>
            <p className="font-mono font-bold text-visa-blue">$134.50</p>
            <p className="font-mono text-sm text-slate-trust-600">Budget: $200.00</p>
          </div>
        </div>
      </section>

      <section className="mb-12">
        <h2 className="font-heading text-xl font-bold text-slate-trust-900 mb-4">
          Button States
        </h2>
        <div className="flex flex-wrap gap-6">
          <div>
            <p className="text-xs text-slate-trust-500 mb-2">Standard (Visa Blue)</p>
            <button
              type="button"
              className="w-full min-w-[200px] py-3 rounded-xl font-bold text-sm bg-visa-blue text-white hover:bg-visa-blue-dark transition-colors"
            >
              Authorize — add to plan
            </button>
          </div>
          <div>
            <p className="text-xs text-slate-trust-500 mb-2">In Plan (Visa Gold)</p>
            <button
              type="button"
              className="w-full min-w-[200px] py-3 rounded-xl font-bold text-sm bg-visa-gold text-slate-900 hover:bg-visa-gold/90 transition-colors"
            >
              ✓ In plan — tap to remove
            </button>
          </div>
        </div>
      </section>

      <section>
        <h2 className="font-heading text-xl font-bold text-slate-trust-900 mb-4">
          Trust Badge (letter-spacing 0.05em)
        </h2>
        <span className="trust-badge inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded border bg-emerald-50 text-emerald-700 border-emerald-100 uppercase">
          94% TRUST
        </span>
      </section>
    </div>
  );
}
