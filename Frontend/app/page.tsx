'use client';

import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Map from 'react-map-gl/mapbox';
import { Marker, Source, Layer } from 'react-map-gl/mapbox';
import type { MapRef } from 'react-map-gl/mapbox';
import { ShieldCheck, Sparkles, MapPin, ArrowUp, X, Sun, Moon, Check } from 'lucide-react';
import insightsData from '@/data/insights.json';
import 'mapbox-gl/dist/mapbox-gl.css';

type ViewState = 'IDLE' | 'THINKING' | 'RESULTS';
type DisplayMode = 'single' | 'itinerary';

interface Recommendation {
  id: string;
  title: string;
  cost: string;
  agent_reasoning?: string;
  score?: string;
  startTime?: string;
  endTime?: string;
  coordinates?: [number, number];
}

interface ItineraryGroup {
  group_name: string;
  items: Recommendation[];
}

// All API keys from env (required for production e.g. yourcommonground.tech)
const MAPBOX_ACCESS_TOKEN =
  process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN ?? '';
const hasMapboxToken = Boolean(MAPBOX_ACCESS_TOKEN);

const INITIAL_BUDGET = 200;
const transition = { type: 'spring' as const, damping: 28, stiffness: 300 };

// Brown University (Providence, RI) – initial viewport
const BROWN_VIEWPORT = {
  longitude: -71.4025,
  latitude: 41.8268,
  zoom: 15,
};

// Fallback coordinates when recommendation has none (Brown / Providence area)
const RECOMMENDATION_COORDINATES: Record<string, [number, number]> = {
  'rec-1': [-71.396, 41.848],
  'rec-2': [-71.4002, 41.8275],
  'rec-3': [-71.403, 41.826],
};

function parseCost(costStr: string): number {
  return parseFloat(costStr.replace(/[^0-9.]/g, '')) || 0;
}

/** "09:00" -> minutes since midnight for comparison */
function parseTimeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

function formatTimeLabel(t: string): string {
  const [h, m] = t.split(':').map(Number);
  if (h === undefined) return t;
  const period = h >= 12 ? 'PM' : 'AM';
  const hour = h % 12 || 12;
  return `${hour}:${String(m ?? 0).padStart(2, '0')} ${period}`;
}

function getCoords(rec: Recommendation): [number, number] | null {
  if (rec.coordinates && rec.coordinates.length >= 2) return rec.coordinates as [number, number];
  const fallback = RECOMMENDATION_COORDINATES['rec-' + rec.id] ?? RECOMMENDATION_COORDINATES[rec.id];
  return fallback ?? null;
}

const itinerariesData = insightsData.itineraries as unknown as ItineraryGroup[];

/** Flat list of all items (dedupe by id) for Impromptu mode */
function flattenRecommendations(groups: ItineraryGroup[]): Recommendation[] {
  const seen = new Set<string>();
  const out: Recommendation[] = [];
  for (const g of groups) {
    for (const r of g.items) {
      if (!seen.has(r.id)) {
        seen.add(r.id);
        out.push(r);
      }
    }
  }
  return out;
}

/** Memoized Impromptu card to avoid re-renders when dragging drawer */
const ImpromptuCard = React.memo(function ImpromptuCard_({
  rec,
  isSelected,
  isHighlighted,
  cardBg,
  drawerText,
  drawerMuted,
  isDarkMode,
  onAuthorize,
}: {
  rec: Recommendation;
  isSelected: boolean;
  isHighlighted: boolean;
  cardBg: string;
  drawerText: string;
  drawerMuted: string;
  isDarkMode: boolean;
  onAuthorize: (id: string) => void;
}) {
  return (
    <article
      id={`card-${rec.id}`}
      className={`flex flex-col h-full min-h-0 border rounded-2xl p-4 md:p-5 shadow-sm scroll-mt-4 transition-shadow min-w-0 ${cardBg} ${
        isHighlighted ? 'card-highlight-pulse ring-2 ring-visa-blue ring-offset-2' : ''
      }`}
    >
      <div className="flex flex-col flex-grow min-h-0 overflow-hidden">
        <div className="flex justify-between items-start mb-2 md:mb-3">
          <span
            className={`trust-badge text-[10px] md:text-xs font-bold px-2 py-0.5 md:px-2.5 md:py-1 rounded border flex items-center gap-1 uppercase ${
              isDarkMode
                ? 'bg-emerald-500/25 text-emerald-300 border-emerald-500/50'
                : 'bg-emerald-50 text-emerald-700 border-emerald-100'
            }`}
          >
            <ShieldCheck className="w-3 h-3 md:w-3.5 md:h-3.5 shrink-0" /> {(rec as Recommendation & { score?: string }).score ?? '85'}% TRUST
          </span>
          <span className={`font-price font-bold text-sm md:text-base ${drawerText}`}>{rec.cost}</span>
        </div>
        <h4 className={`font-heading font-bold text-sm md:text-lg ${drawerText} mb-1`}>{rec.title}</h4>
        <p className={`font-sans text-[11px] md:text-sm mb-3 md:mb-4 ${drawerMuted} line-clamp-3 flex-grow min-h-0`}>{rec.agent_reasoning ?? 'Part of your curated experience.'}</p>
      </div>
      <button
        type="button"
        onClick={() => onAuthorize(rec.id)}
        className={`font-heading w-full py-3 md:py-4 rounded-xl font-bold text-xs md:text-sm tracking-tight transition-all shrink-0 mt-auto ${
          isSelected
            ? 'bg-visa-gold text-slate-900 hover:bg-visa-gold/90'
            : 'bg-visa-blue text-white hover:bg-visa-blue-dark'
        }`}
      >
        {isSelected ? '✓ In plan — tap to remove' : 'Authorize — add to plan'}
      </button>
    </article>
  );
});

/** Memoized Itinerary card */
const ItineraryCard = React.memo(function ItineraryCard_({
  rec,
  isSelected,
  isHighlighted,
  cardBg,
  drawerText,
  drawerMuted,
  isDarkMode,
  onAuthorize,
}: {
  rec: Recommendation;
  isSelected: boolean;
  isHighlighted: boolean;
  cardBg: string;
  drawerText: string;
  drawerMuted: string;
  isDarkMode: boolean;
  onAuthorize: (id: string) => void;
}) {
  return (
    <article
      id={`card-${rec.id}`}
      className={`flex flex-col h-full min-h-0 border rounded-2xl p-6 shadow-sm scroll-mt-4 transition-shadow min-w-0 ${cardBg} ${
        isHighlighted ? 'card-highlight-pulse ring-2 ring-visa-blue ring-offset-2' : ''
      }`}
    >
      <div className="relative flex items-center gap-2 mb-3 shrink-0 pl-8">
        <div className={`absolute left-[12px] top-0.75 shrink-0 rounded-full flex items-center justify-center ${
          isSelected ? 'w-6 h-6 bg-visa-gold text-slate-900' : 'w-3 h-3 bg-visa-blue'
        }`} aria-hidden>
          {isSelected && <Check className="w-3.5 h-3.5" strokeWidth={3} />}
        </div>
        <div className="flex-1 min-w-0">
          <span className={`font-sans text-xs font-bold ${drawerText}`}>
            {rec.startTime && formatTimeLabel(rec.startTime)} – {rec.endTime ? formatTimeLabel(rec.endTime) : '—'}
          </span>
        </div>
        <span className={`font-price font-bold text-sm shrink-0 ${drawerText}`}>{rec.cost}</span>
      </div>
      <div className="flex flex-col flex-grow min-h-0 overflow-hidden">
        <div className="flex justify-between items-start mb-1">
          <span
            className={`trust-badge text-[10px] md:text-xs font-bold px-2 py-0.5 rounded border flex items-center gap-1 w-fit uppercase ${
              isDarkMode
                ? 'bg-emerald-500/25 text-emerald-300 border-emerald-500/50'
                : 'bg-emerald-50 text-emerald-700 border-emerald-100'
            }`}
          >
            <ShieldCheck className="w-3 h-3 shrink-0" /> {(rec as Recommendation & { score?: string }).score ?? '85'}% TRUST
          </span>
        </div>
        <h4 className={`font-heading font-bold text-sm md:text-base ${drawerText} mb-1`}>{rec.title}</h4>
        <p className={`font-sans text-[11px] md:text-sm ${drawerMuted} line-clamp-3 flex-grow min-h-0`}>{rec.agent_reasoning ?? 'Part of this itinerary.'}</p>
      </div>
      <div className="mt-auto min-h-6 shrink-0" aria-hidden />
      <div className="shrink-0">
        <button
          type="button"
          onClick={() => onAuthorize(rec.id)}
          className={`font-heading w-full py-3 md:py-4 rounded-xl font-bold text-xs md:text-sm tracking-tight transition-all ${
            isSelected
              ? 'bg-visa-gold text-slate-900 hover:bg-visa-gold/90'
              : 'bg-visa-blue text-white hover:bg-visa-blue-dark'
          }`}
        >
          {isSelected ? '✓ In plan — tap to remove' : 'Authorize — add to plan'}
        </button>
      </div>
    </article>
  );
});

export default function VICAppleMapsDemo() {
  const [viewState, setViewState] = useState<ViewState>('IDLE');
  const [chatInput, setChatInput] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [drawerHeightPercent, setDrawerHeightPercent] = useState(50);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [displayMode, setDisplayMode] = useState<DisplayMode>('single');
  const [activeItineraryIndex, setActiveItineraryIndex] = useState(0);
  const dragRef = useRef({ isDragging: false, startY: 0, startPercent: 0 });
  const mapRef = useRef<MapRef | null>(null);

  const recommendations = useMemo(() => flattenRecommendations(itinerariesData), []);

  const activeGroupItems = useMemo(() => {
    if (displayMode !== 'itinerary' || !itinerariesData[activeItineraryIndex]) return [];
    const items = itinerariesData[activeItineraryIndex].items.slice();
    items.sort((a, b) => {
      const sa = a.startTime ? parseTimeToMinutes(a.startTime) : 0;
      const sb = b.startTime ? parseTimeToMinutes(b.startTime) : 0;
      return sa - sb;
    });
    return items;
  }, [displayMode, activeItineraryIndex]);

  const itemsForView = displayMode === 'single' ? recommendations : activeGroupItems;

  const itineraryTotalCost = useMemo(
    () => activeGroupItems.reduce((sum, r) => sum + parseCost(r.cost), 0),
    [activeGroupItems]
  );

  const spent = useMemo(
    () =>
      recommendations
        .filter((r) => selectedIds.includes(r.id))
        .reduce((sum, r) => sum + parseCost(r.cost), 0),
    [selectedIds, recommendations]
  );

  const remainingBudget = useMemo(
    () => Math.max(0, Math.round((INITIAL_BUDGET - spent) * 100) / 100),
    [spent]
  );

  useEffect(() => {
    setSelectedIds([]);
  }, [displayMode, activeItineraryIndex]);

  // Global map auto-bounding: fit visible pins when mode or itinerary group changes
  useEffect(() => {
    if (viewState !== 'RESULTS' || !hasMapboxToken || !mapRef.current) return;
    const coords = itemsForView.map((r) => getCoords(r)).filter((c): c is [number, number] => c !== null);
    if (coords.length === 0) return;
    const lngs = coords.map((c) => c[0]);
    const lats = coords.map((c) => c[1]);
    let minLng = Math.min(...lngs);
    let maxLng = Math.max(...lngs);
    let minLat = Math.min(...lats);
    let maxLat = Math.max(...lats);
    if (coords.length === 1) {
      const delta = 0.002;
      minLng -= delta; maxLng += delta; minLat -= delta; maxLat += delta;
    }
    const map = mapRef.current.getMap();
    if (!map) return;
    map.fitBounds(
      [[minLng, minLat], [maxLng, maxLat]],
      { padding: { top: 50, bottom: 300, left: 50, right: 50 }, duration: 1000 }
    );
  }, [viewState, displayMode, activeItineraryIndex, itemsForView, hasMapboxToken]);

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

  const handleAuthorizeFullItinerary = useCallback(() => {
    const ids = activeGroupItems.map((r) => r.id);
    setSelectedIds((prev) => {
      const allSelected = ids.every((id) => prev.includes(id));
      if (allSelected) return prev.filter((id) => !ids.includes(id));
      const combined = prev.slice();
      ids.forEach((id) => { if (!combined.includes(id)) combined.push(id); });
      return combined;
    });
  }, [activeGroupItems]);

  const itineraryLineGeoJSON = useMemo(() => {
    if (displayMode !== 'itinerary' || activeGroupItems.length < 2) return null;
    const coords = activeGroupItems
      .map((r) => getCoords(r))
      .filter((c): c is [number, number] => c !== null);
    if (coords.length < 2) return null;
    return {
      type: 'Feature' as const,
      properties: {},
      geometry: { type: 'LineString' as const, coordinates: coords },
    };
  }, [displayMode, activeGroupItems]);

  const [highlightedCardId, setHighlightedCardId] = useState<string | null>(null);

  const scrollToCard = useCallback((id: string) => {
    setHighlightedCardId(id);
    const el = document.getElementById(`card-${id}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, []);

  useEffect(() => {
    if (!highlightedCardId) return;
    const t = setTimeout(() => setHighlightedCardId(null), 2400);
    return () => clearTimeout(t);
  }, [highlightedCardId]);

  const onHandlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (viewState !== 'IDLE' && viewState !== 'RESULTS') return;
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
    if (viewState !== 'IDLE' && viewState !== 'RESULTS') return;
    const onMove = (e: PointerEvent) => {
      if (!dragRef.current.isDragging) return;
      const viewportHeight = window.visualViewport?.height ?? window.innerHeight;
      const deltaY = e.clientY - dragRef.current.startY;
      const deltaPercent = (-deltaY / viewportHeight) * 100;
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
      ? '100dvh'
      : `${drawerHeightPercent}dvh`;

  const isDrawerFull =
    viewState === 'THINKING' || (viewState === 'RESULTS' && drawerHeightPercent >= 90);

  const mapStyle = isDarkMode
    ? 'mapbox://styles/mapbox/dark-v11'
    : 'mapbox://styles/mapbox/light-v11';

  const drawerBg = isDarkMode ? 'bg-slate-900' : 'bg-white';
  const drawerText = isDarkMode ? 'text-slate-100' : 'text-slate-900';
  const drawerMuted = isDarkMode ? 'text-slate-400' : 'text-slate-500';
  const drawerBorder = isDarkMode ? 'border-slate-700' : 'border-slate-100';
  const inputBg = isDarkMode ? 'bg-slate-800' : 'bg-slate-100';
  const cardBg = isDarkMode ? 'bg-slate-800 border-slate-700' : 'bg-white border-slate-100';

  return (
    <div
      className={`fixed inset-0 w-full h-[100dvh] min-h-[100dvh] max-h-[100dvh] overflow-hidden font-sans ${
        isDarkMode ? 'bg-slate-950' : 'bg-slate-100'
      }`}
    >
      {/* Map layer: always full viewport (dvh for mobile); fixed so drawer scroll doesn’t move it */}
      <div className="absolute inset-0 w-full h-[100dvh] min-h-[100dvh]">
        {hasMapboxToken ? (
          <Map
            ref={mapRef}
            mapboxAccessToken={MAPBOX_ACCESS_TOKEN}
            initialViewState={BROWN_VIEWPORT}
            mapStyle={mapStyle}
            style={{ width: '100%', height: '100%' }}
            reuseMaps
          >
            {viewState === 'RESULTS' && itineraryLineGeoJSON && (
              <Source id="itinerary-route" type="geojson" data={itineraryLineGeoJSON}>
                <Layer
                  id="itinerary-route-line"
                  type="line"
                  paint={{
                    'line-color': '#003399',
                    'line-width': 3,
                    'line-dasharray': [2, 2],
                  }}
                />
              </Source>
            )}
            {viewState === 'RESULTS' &&
              itemsForView.map((rec) => {
                const coords = getCoords(rec);
                if (!coords) return null;
                const [longitude, latitude] = coords;
                return (
                  <Marker
                    key={rec.id}
                    longitude={longitude}
                    latitude={latitude}
                    anchor="bottom"
                    onClick={() => scrollToCard(rec.id)}
                  >
                    <button
                      type="button"
                      className="w-8 h-8 rounded-full border-2 border-white shadow-lg flex items-center justify-center hover:scale-110 active:scale-95 transition-transform focus:outline-none focus:ring-2 focus:ring-visa-gold focus:ring-offset-2 cursor-pointer"
                      style={{ backgroundColor: '#003399' }}
                      aria-label={`Go to ${rec.title}`}
                    >
                      <MapPin className="w-3.5 h-3.5 text-white" />
                    </button>
                  </Marker>
                );
              })}
          </Map>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-slate-100 to-slate-200">
            <div className="flex flex-col items-center gap-3 text-slate-400">
              <MapPin className="w-10 h-10" strokeWidth={1.5} />
              <span className="text-sm font-medium">Map</span>
              <span className="text-xs">Set NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN</span>
            </div>
          </div>
        )}

        {/* When drawer is full-screen: dim + blur map so it stays in background */}
        <AnimatePresence>
          {isDrawerFull && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
              className="absolute inset-0 bg-black/35 backdrop-blur-[2px] pointer-events-none"
              aria-hidden
            />
          )}
        </AnimatePresence>

        {/* Dark / Light toggle – top right over map */}
        <button
          type="button"
          onClick={() => setIsDarkMode((d) => !d)}
          className={`absolute top-3 right-3 z-10 p-2 rounded-xl shadow-lg transition-colors ${
            isDarkMode ? 'bg-slate-700 text-visa-gold' : 'bg-white text-visa-blue'
          }`}
          aria-label={isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {isDarkMode ? <Sun size={20} /> : <Moon size={20} />}
        </button>
      </div>

      {/* Drawer: fixed to bottom, height in dvh; GPU-accelerated for smooth scroll and drag */}
      <motion.div
        animate={{ height: drawerHeight }}
        transition={transition}
        className={`drawer-gpu absolute bottom-0 left-0 right-0 w-full ${drawerBg} rounded-t-3xl shadow-2xl z-20 flex flex-col`}
        style={{ transform: 'translateZ(0)' }}
      >
        <div
          onPointerDown={onHandlePointerDown}
          style={{ touchAction: 'none' }}
          className={`w-12 h-1.5 rounded-full mx-auto mt-3 mb-2 md:mt-4 md:mb-3 md:w-14 md:h-2 touch-none select-none cursor-ns-resize ${
            viewState === 'RESULTS'
              ? isDarkMode
                ? 'bg-slate-600 hover:bg-visa-gold/30'
                : 'bg-slate-300 hover:bg-visa-blue/20'
              : isDarkMode
                ? 'bg-slate-600'
                : 'bg-slate-200'
          }`}
          aria-hidden
        />

        <div className={`px-4 py-2 md:px-8 md:py-3 flex items-center justify-between ${drawerText}`}>
          <div className="flex items-center gap-2 md:gap-3">
            <div
              className={`p-1.5 md:p-2 rounded-lg ${
                viewState === 'THINKING' ? 'bg-visa-gold animate-pulse' : 'bg-visa-blue'
              }`}
            >
              <Sparkles className="w-4 h-4 md:w-5 md:h-5 text-white" />
            </div>
            <div>
              <h2 className="font-heading text-sm md:text-base font-bold leading-none tracking-tight">VIC Agent</h2>
              <p className={`font-heading text-[10px] md:text-xs font-bold uppercase tracking-tight ${drawerMuted}`}>
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
              className={`p-1.5 md:p-2 rounded-full ${
                isDarkMode ? 'bg-slate-700 text-slate-300 hover:bg-slate-600' : 'bg-slate-100 text-slate-400 hover:bg-slate-200'
              }`}
            >
              <X className="w-4 h-4 md:w-5 md:h-5" />
            </button>
          )}
        </div>

        <div
          className={`flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 md:px-8 md:py-6 min-h-0 w-full ${
            isDarkMode ? 'scrollbar-drawer-dark' : 'scrollbar-drawer'
          }`}
        >
          {/* Segmented control: visible in both IDLE and RESULTS */}
          <div className={`mb-4 flex items-center justify-between gap-3 ${drawerText}`}>
            <span className="font-heading text-xs font-bold uppercase tracking-tight text-slate-500">MODE</span>
            <div
              className={`flex rounded-xl p-1 ${isDarkMode ? 'bg-slate-800' : 'bg-slate-100'}`}
              role="group"
              aria-label="Display mode"
            >
              <button
                type="button"
                onClick={() => setDisplayMode('single')}
                className={`font-heading px-4 py-2 rounded-lg text-sm font-bold tracking-tight transition-all ${
                  displayMode === 'single'
                    ? 'bg-white text-visa-blue shadow-sm'
                    : isDarkMode
                      ? 'text-slate-400 hover:text-slate-200'
                      : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                Impromptu
              </button>
              <button
                type="button"
                onClick={() => setDisplayMode('itinerary')}
                className={`font-heading px-4 py-2 rounded-lg text-sm font-bold tracking-tight transition-all ${
                  displayMode === 'itinerary'
                    ? 'bg-white text-visa-blue shadow-sm'
                    : isDarkMode
                      ? 'text-slate-400 hover:text-slate-200'
                      : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                Itinerary
              </button>
            </div>
          </div>

          {viewState === 'RESULTS' && displayMode === 'itinerary' && (
            <div className={`mb-4 flex gap-1 p-1 rounded-xl ${isDarkMode ? 'bg-slate-800' : 'bg-slate-100'}`} role="tablist" aria-label="Itinerary group">
              {itinerariesData.map((grp, idx) => (
                <button
                  key={grp.group_name}
                  type="button"
                  role="tab"
                  aria-selected={activeItineraryIndex === idx}
                  onClick={() => setActiveItineraryIndex(idx)}
                  className={`flex-1 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                    activeItineraryIndex === idx
                      ? 'bg-white text-visa-blue shadow-sm'
                      : isDarkMode
                        ? 'text-slate-400 hover:text-slate-200'
                        : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  {grp.group_name}
                </button>
              ))}
            </div>
          )}

          <AnimatePresence mode="wait">
            {viewState === 'IDLE' && (
              <motion.div
                key="idle"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="h-full flex flex-col justify-center px-2 md:px-4"
              >
                <p className={`font-sans text-center text-xs md:text-sm mb-4 md:mb-6 ${drawerMuted}`}>
                  Where are you? What’s your budget?
                </p>
                <div className="relative flex items-center gap-2 max-w-xl mx-auto w-full">
                  <input
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                    placeholder="I'm in NYC for a day with $200"
                    className={`font-sans w-full ${inputBg} p-4 pr-12 md:p-5 md:pr-14 rounded-2xl text-sm md:text-base placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-visa-blue/20 ${drawerText}`}
                  />
                  <button
                    onClick={handleSearch}
                    className="absolute right-2 md:right-3 p-2 md:p-2.5 bg-visa-blue text-white rounded-xl active:scale-95 transition-transform"
                  >
                    <ArrowUp className="w-5 h-5 md:w-6 md:h-6" />
                  </button>
                </div>
              </motion.div>
            )}

            {viewState === 'THINKING' && (
              <motion.div
                key="thinking"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="space-y-6 md:space-y-10 py-8 md:py-12"
              >
                <div className="flex items-center gap-3 md:gap-4">
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
                    className="w-8 h-8 md:w-10 md:h-10 rounded-full border-2 border-visa-blue border-t-transparent shrink-0"
                  />
                  <div>
                    <h3 className={`text-lg md:text-2xl font-bold tracking-tight ${drawerText}`}>
                      Analyzing NYC vendors...
                    </h3>
                    <p className={`text-sm md:text-base ${drawerMuted}`}>
                      Finding places that match your budget and style.
                    </p>
                  </div>
                </div>
                <div className="space-y-3 md:space-y-5">
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
                      className={`flex items-center gap-3 text-sm md:text-base ${drawerMuted}`}
                    >
                      <div className="w-5 h-5 md:w-6 md:h-6 rounded-full border-2 border-visa-blue border-t-transparent animate-spin shrink-0" />
                      {text}
                    </motion.div>
                  ))}
                </div>
              </motion.div>
            )}

            {viewState === 'RESULTS' && (
              <motion.div
                key="results"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="pb-4 flex flex-col gap-8"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
                  <h3
                    className={`font-heading font-bold text-xs md:text-sm uppercase tracking-widest ${drawerMuted}`}
                  >
                    {displayMode === 'itinerary' ? itinerariesData[activeItineraryIndex]?.group_name ?? 'Itinerary' : 'Recommended for You'}
                  </h3>
                  <span
                    className={`font-price text-xs md:text-sm font-bold px-2 py-1.5 md:px-3 md:py-2 rounded-md tracking-tighter ${
                      isDarkMode
                        ? 'bg-visa-gold/25 text-visa-gold border border-visa-gold/50'
                        : 'text-visa-blue bg-[#003399]/10'
                    }`}
                    title={displayMode === 'itinerary' ? 'Budget after full itinerary' : 'Updates in real time as you add/remove items'}
                  >
                    Budget: ${remainingBudget.toFixed(2)}
                  </span>
                </div>

                {displayMode === 'single' ? (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-8 items-stretch">
                    {itemsForView.map((rec) => (
                      <ImpromptuCard
                        key={rec.id}
                        rec={rec}
                        isSelected={selectedIds.includes(rec.id)}
                        isHighlighted={highlightedCardId === rec.id}
                        cardBg={cardBg}
                        drawerText={drawerText}
                        drawerMuted={drawerMuted}
                        isDarkMode={isDarkMode}
                        onAuthorize={handleAuthorize}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="w-full">
                    {activeGroupItems.length === 0 ? (
                      <p className={`font-sans py-8 text-center text-sm ${drawerMuted}`}>
                        No stops in this itinerary.
                      </p>
                    ) : (
                      <>
                        <div className="relative grid grid-cols-1 md:grid-cols-3 gap-x-8 gap-y-12 items-stretch before:absolute before:left-[19px] before:top-0 before:bottom-0 before:w-[2px] before:bg-slate-200 before:dark:bg-slate-600 before:content-[''] md:before:hidden">
                          {activeGroupItems.map((rec) => (
                            <ItineraryCard
                              key={rec.id}
                              rec={rec}
                              isSelected={selectedIds.includes(rec.id)}
                              isHighlighted={highlightedCardId === rec.id}
                              cardBg={cardBg}
                              drawerText={drawerText}
                              drawerMuted={drawerMuted}
                              isDarkMode={isDarkMode}
                              onAuthorize={handleAuthorize}
                            />
                          ))}
                        </div>
                        <div className={`mt-12 pt-6 border-t ${drawerBorder}`}>
                          <button
                            type="button"
                            onClick={handleAuthorizeFullItinerary}
                            className={`font-heading w-full py-4 rounded-xl font-bold text-sm tracking-tight transition-all ${
                              activeGroupItems.every((r) => selectedIds.includes(r.id))
                                ? 'bg-visa-gold text-slate-900 hover:bg-visa-gold/90'
                                : 'bg-visa-blue text-white hover:bg-visa-blue-dark'
                            }`}
                          >
                            {activeGroupItems.every((r) => selectedIds.includes(r.id))
                              ? '✓ Full itinerary in plan — tap to remove'
                              : <>Authorize Full Itinerary — <span className="font-price">${itineraryTotalCost.toFixed(2)}</span></>}
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {viewState === 'RESULTS' && (
          <div className={`p-4 md:p-6 border-t pb-safe shrink-0 ${drawerBorder} ${drawerBg}`}>
            <div className="relative flex items-center gap-2 max-w-4xl mx-auto">
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Refine search — e.g. add more budget..."
                className={`font-sans flex-1 ${inputBg} p-4 pr-12 md:p-5 md:pr-14 rounded-2xl text-sm md:text-base placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-visa-blue/20 ${drawerText}`}
              />
              <button
                onClick={handleSearch}
                className="absolute right-2 md:right-3 p-2 md:p-2.5 bg-visa-blue text-white rounded-xl active:scale-95 transition-transform"
              >
                <ArrowUp className="w-5 h-5 md:w-6 md:h-6" />
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
}
