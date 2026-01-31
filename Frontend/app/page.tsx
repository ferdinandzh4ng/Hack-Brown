'use client';

import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ShieldCheck, Sparkles, MapPin, ArrowUp, X } from 'lucide-react';
import recommendationsData from '@/data/insights.json';

type ViewState = 'IDLE' | 'THINKING' | 'RESULTS';

const INITIAL_BUDGET = 200;
const transition = { type: 'spring' as const, damping: 28, stiffness: 300 };

function parseCost(costStr: string): number {
  return parseFloat(costStr.replace(/[^0-9.]/g, '')) || 0;
}

// Pin positions for map (percent from top/left) – one per recommendation
const PIN_POSITIONS: Record<string, { top: string; left: string }> = {
  'rec-1': { top: '28%', left: '32%' },
  'rec-2': { top: '48%', left: '52%' },
  'rec-3': { top: '68%', left: '68%' },
};

export default function VICAppleMapsDemo() {
  const [viewState, setViewState] = useState<ViewState>('IDLE');
  const [chatInput, setChatInput] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [drawerHeightPercent, setDrawerHeightPercent] = useState(50);
  const dragRef = useRef({ isDragging: false, startY: 0, startPercent: 0 });

  const recommendations = recommendationsData.recommendations;

  const spent = useMemo(
    () =>
      recommendations
        .filter((r) => selectedIds.includes(r.id))
        .reduce((sum, r) => sum + parseCost(r.cost), 0),
    [selectedIds, recommendations]
  );
  const remainingBudget = useMemo(() => Math.max(0, INITIAL_BUDGET - spent), [spent]);

  const handleSearch = useCallback(() => {
    if (!chatInput.trim()) return;
    setViewState('THINKING');
    setTimeout(() => setViewState('RESULTS'), 3000);
  }, [chatInput]);

  const handleAuthorize = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }, []);

  const scrollToCard = useCallback((id: string) => {
    const el = document.getElementById(`card-${id}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, []);

  // Draggable drawer: pointer handlers for handle
  const onHandlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (viewState !== 'RESULTS') return;
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      dragRef.current = {
        isDragging: true,
        startY: e.clientY,
        startPercent: drawerHeightPercent,
      };
    },
    [viewState, drawerHeightPercent]
  );

  useEffect(() => {
    if (viewState !== 'RESULTS') return;
    const onMove = (e: PointerEvent) => {
      if (!dragRef.current.isDragging) return;
      const deltaY = e.clientY - dragRef.current.startY;
      const deltaPercent = (-deltaY / window.innerHeight) * 100;
      const next = dragRef.current.startPercent + deltaPercent;
      setDrawerHeightPercent(Math.min(95, Math.max(20, next)));
    };
    const onUp = () => {
      dragRef.current.isDragging = false;
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointerleave', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointerleave', onUp);
    };
  }, [viewState]);

  const drawerHeight =
    viewState === 'THINKING'
      ? '100vh'
      : viewState === 'RESULTS'
        ? `${drawerHeightPercent}vh`
        : '50vh';
  const mapHeight =
    viewState === 'THINKING' ? 0 : viewState === 'RESULTS' ? `calc(100vh - ${drawerHeightPercent}vh)` : '50vh';

  return (
    <div className="max-w-md mx-auto h-screen bg-slate-100 overflow-hidden flex flex-col font-sans">
      {/* TOP: MAP (shrinks when drawer expands in RESULTS) */}
      <motion.div
        animate={{ height: viewState === 'THINKING' ? 0 : mapHeight }}
        transition={transition}
        className="relative shrink-0 overflow-hidden bg-slate-200"
      >
        <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-slate-100 to-slate-200">
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-slate-400 pointer-events-none">
            <MapPin className="w-10 h-10" strokeWidth={1.5} />
            <span className="text-sm font-medium tracking-wide">Map</span>
          </div>
          {viewState === 'RESULTS' &&
            recommendations.map((rec) => {
              const pos = PIN_POSITIONS[rec.id] ?? { top: '50%', left: '50%' };
              return (
                <motion.button
                  key={rec.id}
                  type="button"
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                  className="absolute w-8 h-8 -ml-4 -mt-4 rounded-full bg-visa-blue border-2 border-white shadow-lg flex items-center justify-center hover:scale-110 active:scale-95 transition-transform focus:outline-none focus:ring-2 focus:ring-visa-gold focus:ring-offset-2"
                  style={{ top: pos.top, left: pos.left }}
                  onClick={() => scrollToCard(rec.id)}
                  aria-label={`Go to ${rec.title}`}
                >
                  <MapPin className="w-3 h-3 text-white" />
                </motion.button>
              );
            })}
        </div>
      </motion.div>

      {/* BOTTOM: AGENT CHAT DRAWER (fixed or draggable height) */}
      <motion.div
        animate={{ height: drawerHeight }}
        transition={transition}
        className="bg-white rounded-t-3xl shadow-2xl z-20 flex flex-col relative shrink-0"
      >
        {/* Draggable Handle (RESULTS only) */}
        <div
          onPointerDown={onHandlePointerDown}
          className={`w-12 h-1.5 rounded-full mx-auto mt-3 mb-2 touch-none select-none ${
            viewState === 'RESULTS'
              ? 'bg-slate-300 cursor-ns-resize hover:bg-visa-blue/20'
              : 'bg-slate-200'
          }`}
          aria-hidden
        />

        {/* Agent Header */}
        <div className="px-6 py-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className={`p-1.5 rounded-lg ${
                viewState === 'THINKING' ? 'bg-visa-gold animate-pulse' : 'bg-visa-blue'
              }`}
            >
              <Sparkles size={16} className="text-white" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-900 leading-none">VIC Agent</h2>
              <p className="text-[10px] text-slate-400 font-medium uppercase tracking-tighter">
                Powered by Visa Intelligence
              </p>
            </div>
          </div>
          {viewState === 'RESULTS' && (
            <button
              onClick={() => {
                setViewState('IDLE');
                setChatInput('');
                setSelectedIds([]);
              }}
              className="p-1.5 bg-slate-100 rounded-full text-slate-400 hover:bg-slate-200"
            >
              <X size={16} />
            </button>
          )}
        </div>

        {/* Dynamic Content Area */}
        <div className="flex-1 overflow-y-auto px-6 py-4 min-h-0">
          <AnimatePresence mode="wait">
            {/* IDLE: search input */}
            {viewState === 'IDLE' && (
              <motion.div
                key="idle"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="h-full flex flex-col justify-center px-2"
              >
                <p className="text-center text-xs text-slate-400 mb-4">
                  Where are you? What’s your budget?
                </p>
                <div className="relative flex items-center gap-2">
                  <input
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                    placeholder="I'm in NYC for a day with $200"
                    className="w-full bg-slate-100 p-4 pr-12 rounded-2xl text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-visa-blue/20"
                  />
                  <button
                    onClick={handleSearch}
                    className="absolute right-2 p-2 bg-visa-blue text-white rounded-xl active:scale-95 transition-transform"
                  >
                    <ArrowUp size={20} />
                  </button>
                </div>
              </motion.div>
            )}

            {/* THINKING: full height, reasoning logs */}
            {viewState === 'THINKING' && (
              <motion.div
                key="thinking"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="space-y-8 py-10"
              >
                <div className="flex items-center gap-3">
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
                    className="w-8 h-8 rounded-full border-2 border-visa-blue border-t-transparent shrink-0"
                  />
                  <div>
                    <h3 className="text-xl font-bold text-slate-900 tracking-tight">
                      Analyzing NYC vendors...
                    </h3>
                    <p className="text-slate-500 text-sm">
                      Finding places that match your budget and style.
                    </p>
                  </div>
                </div>
                <div className="space-y-4">
                  {[
                    'Scanning local digital-first merchants',
                    'Matching your budget and preferences',
                    'Checking Visa Secure scores for nearby vendors',
                  ].map((text, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.6 }}
                      className="flex items-center gap-3 text-sm text-slate-600"
                    >
                      <div className="w-5 h-5 rounded-full border-2 border-visa-blue border-t-transparent animate-spin shrink-0" />
                      {text}
                    </motion.div>
                  ))}
                </div>
              </motion.div>
            )}

            {/* RESULTS: community cards + persistent input */}
            {viewState === 'RESULTS' && (
              <motion.div
                key="results"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="space-y-6 pb-4"
              >
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-bold text-slate-400 text-xs uppercase tracking-widest">
                    Recommended for You
                  </h3>
                  <span className="text-xs font-bold text-visa-blue bg-[#003399]/10 px-2 py-1 rounded-md tracking-tighter">
                    Budget: ${remainingBudget.toFixed(2)}
                  </span>
                </div>
                {recommendations.map((rec) => {
                  const isSelected = selectedIds.includes(rec.id);
                  return (
                    <div
                      key={rec.id}
                      id={`card-${rec.id}`}
                      className="border border-slate-100 rounded-2xl p-4 bg-white shadow-sm scroll-mt-4"
                    >
                      <div className="flex justify-between items-start mb-2">
                        <span className="bg-emerald-50 text-emerald-700 text-[10px] font-bold px-2 py-0.5 rounded border border-emerald-100 flex items-center gap-1">
                          <ShieldCheck size={10} /> {rec.score}% TRUST
                        </span>
                        <span className="font-bold text-slate-900">{rec.cost}</span>
                      </div>
                      <h4 className="font-bold text-slate-800">{rec.title}</h4>
                      <p className="text-[11px] text-slate-500 mb-3">{rec.agent_reasoning}</p>
                      <button
                        type="button"
                        onClick={() => handleAuthorize(rec.id)}
                        className={`w-full py-3 rounded-xl font-bold text-xs transition-all ${
                          isSelected
                            ? 'bg-visa-gold text-slate-900 hover:bg-visa-gold/90'
                            : 'bg-visa-blue text-white hover:bg-visa-blue-dark'
                        }`}
                      >
                        {isSelected ? '✓ In plan — tap to remove' : 'Authorize — add to plan'}
                      </button>
                    </div>
                  );
                })}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Persistent chat input: IDLE (inside content) and RESULTS (sticky); hidden in THINKING */}
        {viewState === 'RESULTS' && (
          <div className="p-4 bg-white border-t border-slate-100 pb-safe shrink-0">
            <div className="relative flex items-center gap-2">
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Refine search — e.g. add more budget..."
                className="flex-1 bg-slate-100 p-4 pr-12 rounded-2xl text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-visa-blue/20"
              />
              <button
                onClick={handleSearch}
                className="absolute right-2 p-2 bg-visa-blue text-white rounded-xl active:scale-95 transition-transform"
              >
                <ArrowUp size={20} />
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
}
