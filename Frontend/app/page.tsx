"use client";

import React, {
  useState,
  useMemo,
  useCallback,
  useRef,
  useEffect,
} from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import MapGL from "react-map-gl/mapbox";
import { Marker, Source, Layer } from "react-map-gl/mapbox";
import type { MapRef } from "react-map-gl/mapbox";
import {
  ShieldCheck,
  Sparkles,
  MapPin,
  ArrowUp,
  X,
  Sun,
  Moon,
  Check,
  ArrowRight,
} from "lucide-react";
import insightsData from "@/data/insights.json";
import { City } from "country-state-city";
import "mapbox-gl/dist/mapbox-gl.css";

type ViewState = "IDLE" | "THINKING" | "RESULTS";
type DisplayMode = "single" | "itinerary";

interface Recommendation {
  id: string;
  title: string;
  cost: string;
  agent_reasoning?: string;
  score?: string;
  startTime?: string;
  endTime?: string;
  coordinates?: [number, number];
  address?: string;
  type?: "venue" | "transit";
  transitMethod?: string;
}

interface ItineraryGroup {
  group_name: string;
  items: Recommendation[];
}

// All API keys from env (required for production e.g. yourcommonground.tech)
const MAPBOX_ACCESS_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN ?? "";
const hasMapboxToken = Boolean(MAPBOX_ACCESS_TOKEN);

const INITIAL_BUDGET = 200;
const transition = { type: "spring" as const, damping: 28, stiffness: 300 };

// Brown University (Providence, RI) – initial viewport
const BROWN_VIEWPORT = {
  longitude: -71.4025,
  latitude: 41.8268,
  zoom: 15,
};

// Fallback coordinates when recommendation has none (Brown / Providence area)
const RECOMMENDATION_COORDINATES: Record<string, [number, number]> = {
  "rec-1": [-71.396, 41.848],
  "rec-2": [-71.4002, 41.8275],
  "rec-3": [-71.403, 41.826],
  "anchor-starbucks": [-71.4103, 41.8245],
};

/** Anchor location: always first result (Impromptu and Itinerary). */
const ANCHOR_LOCATION: Recommendation = {
  id: "anchor-starbucks",
  title: "Starbucks",
  cost: "$6.50",
  address: "1 Financial Plaza, Providence, RI 02903",
  coordinates: [-71.4103, 41.8245],
  agent_reasoning:
    "Strategically located at Financial Plaza, this Starbucks is a Visa Digital-First partner. Perfect for a secure, frictionless start to your Providence journey.",
  score: "99",
  startTime: "08:00",
  endTime: "09:00",
};

function parseCost(costStr: string): number {
  return parseFloat(costStr.replace(/[^0-9.]/g, "")) || 0;
}

/** "09:00" -> minutes since midnight for comparison */
function parseTimeToMinutes(t: string): number {
  const [h, m] = t.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

function formatTimeLabel(t: string): string {
  const [h, m] = t.split(":").map(Number);
  if (h === undefined) return t;
  const period = h >= 12 ? "PM" : "AM";
  const hour = h % 12 || 12;
  return `${hour}:${String(m ?? 0).padStart(2, "0")} ${period}`;
}

function getCoords(rec: Recommendation): [number, number] | null {
  if (rec.coordinates && rec.coordinates.length >= 2)
    return rec.coordinates as [number, number];
  const fallback =
    RECOMMENDATION_COORDINATES["rec-" + rec.id] ??
    RECOMMENDATION_COORDINATES[rec.id];
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

const READ_MORE_THRESHOLD = 100;

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
  const text = rec.agent_reasoning ?? "Part of your curated experience.";
  const showReadMore = text.length > READ_MORE_THRESHOLD;
  const [expanded, setExpanded] = React.useState(false);

  return (
    <article
      id={`card-${rec.id}`}
      className={`flex flex-col h-full min-h-0 border rounded-2xl p-4 md:p-5 shadow-sm scroll-mt-4 transition-shadow min-w-0 ${cardBg} ${
        isHighlighted
          ? "card-highlight-pulse ring-2 ring-visa-blue ring-offset-2"
          : ""
      }`}
    >
      <div className="flex flex-col flex-grow min-h-0 overflow-hidden">
        <div className="flex justify-between items-start mb-2 md:mb-3">
          <span
            className={`trust-badge text-[10px] md:text-xs font-bold px-2 py-0.5 md:px-2.5 md:py-1 rounded border flex items-center gap-1 uppercase ${
              isDarkMode
                ? "bg-emerald-500/25 text-emerald-300 border-emerald-500/50"
                : "bg-emerald-50 text-emerald-700 border-emerald-100"
            }`}
          >
            <ShieldCheck className="w-3 h-3 md:w-3.5 md:h-3.5 shrink-0" />{" "}
            {(rec as Recommendation & { score?: string }).score ?? "85"}% TRUST
          </span>
          <span
            className={`font-price font-bold text-sm md:text-base ${drawerText}`}
          >
            {rec.cost}
          </span>
        </div>
        <h4
          className={`font-heading font-bold text-sm md:text-lg ${drawerText} mb-1`}
        >
          {rec.title}
        </h4>
        <p
          className={`font-sans text-[11px] md:text-sm mb-1 ${drawerMuted} flex-grow min-h-0 ${expanded ? "" : "line-clamp-2"} ${!showReadMore ? "mb-3 md:mb-4" : ""}`}
        >
          {text}
        </p>
        {showReadMore && (
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className={`font-sans font-medium text-[11px] md:text-xs mt-0.5 text-left mb-3 md:mb-4 ${drawerMuted} hover:underline focus:outline-none`}
          >
            {expanded ? "Show less" : "…read more"}
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={() => onAuthorize(rec.id)}
        className={`font-heading w-full py-3 md:py-4 rounded-xl font-bold text-xs md:text-sm tracking-tight transition-all shrink-0 mt-auto ${
          isSelected
            ? "bg-visa-gold text-slate-900 hover:bg-visa-gold/90"
            : "bg-visa-blue text-white hover:bg-visa-blue-dark"
        }`}
      >
        {isSelected ? "✓ In plan — tap to remove" : "Authorize — add to plan"}
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
  const text = rec.agent_reasoning ?? "Part of this itinerary.";
  const showReadMore = text.length > READ_MORE_THRESHOLD;
  const [expanded, setExpanded] = React.useState(false);

  return (
    <article
      id={`card-${rec.id}`}
      className={`flex flex-col h-full min-h-0 border rounded-2xl p-6 shadow-sm scroll-mt-4 transition-shadow min-w-0 ${cardBg} ${
        isHighlighted
          ? "card-highlight-pulse ring-2 ring-visa-blue ring-offset-2"
          : ""
      }`}
    >
      <div className="relative flex items-center gap-2 mb-3 shrink-0 pl-12">
        <div
          className={`absolute left-[10px] top-0.75 shrink-0 rounded-full flex items-center justify-center z-10 ${
            isSelected
              ? "w-6 h-6 bg-visa-gold text-slate-900 border-2 border-white shadow-sm"
              : "w-3 h-3 bg-visa-blue"
          }`}
          aria-hidden
        >
          {isSelected && <Check className="w-3.5 h-3.5" strokeWidth={3} />}
        </div>
        <div className="flex-1 min-w-0">
          <span className={`font-sans text-xs font-bold ${drawerText}`}>
            {rec.startTime && formatTimeLabel(rec.startTime)} –{" "}
            {rec.endTime ? formatTimeLabel(rec.endTime) : "—"}
          </span>
        </div>
        <span className={`font-price font-bold text-sm shrink-0 ${drawerText}`}>
          {rec.cost}
        </span>
      </div>
      <div className="flex flex-col flex-grow min-h-0 overflow-hidden">
        <div className="flex justify-between items-start mb-1">
          <span
            className={`trust-badge text-[10px] md:text-xs font-bold px-2 py-0.5 rounded border flex items-center gap-1 w-fit uppercase ${
              isDarkMode
                ? "bg-emerald-500/25 text-emerald-300 border-emerald-500/50"
                : "bg-emerald-50 text-emerald-700 border-emerald-100"
            }`}
          >
            <ShieldCheck className="w-3 h-3 shrink-0" />{" "}
            {(rec as Recommendation & { score?: string }).score ?? "85"}% TRUST
          </span>
        </div>
        <h4
          className={`font-heading font-bold text-sm md:text-base ${drawerText} mb-1`}
        >
          {rec.title}
        </h4>
        <p
          className={`font-sans text-[11px] md:text-sm ${drawerMuted} flex-grow min-h-0 ${expanded ? "" : "line-clamp-2"}`}
        >
          {text}
        </p>
        {showReadMore && (
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className={`font-sans font-medium text-[11px] md:text-xs mt-0.5 text-left ${drawerMuted} hover:underline focus:outline-none`}
          >
            {expanded ? "Show less" : "…read more"}
          </button>
        )}
      </div>
      <div className="mt-auto min-h-6 shrink-0" aria-hidden />
      <div className="shrink-0">
        <button
          type="button"
          onClick={() => onAuthorize(rec.id)}
          className={`font-heading w-full py-3 md:py-4 rounded-xl font-bold text-xs md:text-sm tracking-tight transition-all ${
            isSelected
              ? "bg-visa-gold text-slate-900 hover:bg-visa-gold/90"
              : "bg-visa-blue text-white hover:bg-visa-blue-dark"
          }`}
        >
          {isSelected ? "✓ In plan — tap to remove" : "Authorize — add to plan"}
        </button>
      </div>
    </article>
  );
});

export default function HelpingHandApp() {
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [viewState, setViewState] = useState<ViewState>("IDLE");
  const [chatInput, setChatInput] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [displayMode, setDisplayMode] = useState<DisplayMode>("itinerary");
  const [activeItineraryIndex, setActiveItineraryIndex] = useState(0);
  const mapRef = useRef<MapRef | null>(null);

  // Redirect to login if no session – login page is the first thing users see
  useEffect(() => {
    const token =
      typeof localStorage !== "undefined"
        ? localStorage.getItem("session_token")
        : null;
    if (!token) {
      router.replace("/login");
      return;
    }
    setAuthChecked(true);
  }, [router]);

  // Form state
  const [location, setLocation] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiRecommendations, setApiRecommendations] = useState<
    Recommendation[]
  >([]);
  const [transitInfo, setTransitInfo] = useState<Map<number, any>>(new Map());
  const [apiBudget, setApiBudget] = useState<number | null>(null);

  // Get all cities from library and format for dropdown
  const citiesList = useMemo(() => {
    const allCities = City.getAllCities();
    // Format as "City, State, Country" or "City, Country" if no state
    return allCities
      .map((city) => {
        if (city.stateCode) {
          return `${city.name}, ${city.stateCode}, ${city.countryCode}`;
        }
        return `${city.name}, ${city.countryCode}`;
      })
      .sort();
  }, []);

  // Use API recommendations if available, otherwise fall back to static data. Anchor Starbucks is always first.
  const recommendations = useMemo(() => {
    const base =
      apiRecommendations.length > 0
        ? apiRecommendations.filter((r) => r.id !== ANCHOR_LOCATION.id)
        : flattenRecommendations(itinerariesData).filter(
            (r) => r.id !== ANCHOR_LOCATION.id,
          );
    return [ANCHOR_LOCATION, ...base];
  }, [apiRecommendations]);

  // Create itinerary groups from API data or static data. Anchor Starbucks is always first in each group.
  const itineraryGroups = useMemo(() => {
    if (apiRecommendations.length > 0) {
      const rest = apiRecommendations.filter(
        (r) => r.id !== ANCHOR_LOCATION.id,
      );
      return [
        {
          group_name: `${location} Itinerary`,
          items: [ANCHOR_LOCATION, ...rest],
        },
      ];
    }
    return itinerariesData.map((g) => ({
      ...g,
      items: [
        ANCHOR_LOCATION,
        ...g.items.filter((r) => r.id !== ANCHOR_LOCATION.id),
      ],
    }));
  }, [apiRecommendations, location]);

  const activeGroupItems = useMemo(() => {
    if (displayMode !== "itinerary" || !itineraryGroups[activeItineraryIndex])
      return [];
    const items = itineraryGroups[activeItineraryIndex].items.slice();
    items.sort((a, b) => {
      const sa = a.startTime ? parseTimeToMinutes(a.startTime) : 0;
      const sb = b.startTime ? parseTimeToMinutes(b.startTime) : 0;
      return sa - sb;
    });
    return items;
  }, [displayMode, activeItineraryIndex, itineraryGroups]);

  const itemsForView =
    displayMode === "single" ? recommendations : activeGroupItems;

  const itineraryTotalCost = useMemo(
    () => activeGroupItems.reduce((sum, r) => sum + parseCost(r.cost), 0),
    [activeGroupItems],
  );

  const spent = useMemo(
    () =>
      recommendations
        .filter((r) => selectedIds.includes(r.id))
        .reduce((sum, r) => sum + parseCost(r.cost), 0),
    [selectedIds, recommendations],
  );

  const remainingBudget = useMemo(() => {
    // If we have API budget, calculate remaining from total cost
    if (apiBudget !== null) {
      const totalSpent = recommendations
        .filter((r) => selectedIds.includes(r.id))
        .reduce((sum, r) => sum + parseCost(r.cost), 0);
      return Math.max(0, Math.round((apiBudget - totalSpent) * 100) / 100);
    }
    // Otherwise use initial budget
    return Math.max(0, Math.round((INITIAL_BUDGET - spent) * 100) / 100);
  }, [spent, apiBudget, recommendations, selectedIds]);

  useEffect(() => {
    setSelectedIds([]);
  }, [displayMode, activeItineraryIndex]);

  // Coords used for fitBounds: when 2+ selected, fit to selection path; otherwise all visible pins
  const coordsForFitBounds = useMemo(() => {
    const selected = itemsForView
      .filter((r) => selectedIds.includes(r.id))
      .slice()
      .sort((a, b) => {
        const sa = a.startTime ? parseTimeToMinutes(a.startTime) : 0;
        const sb = b.startTime ? parseTimeToMinutes(b.startTime) : 0;
        return sa - sb;
      });
    const source = selected.length >= 2 ? selected : itemsForView;
    return source
      .map((r) => getCoords(r))
      .filter((c): c is [number, number] => c !== null);
  }, [itemsForView, selectedIds]);

  // Global map auto-bounding: fit to selection path when 2+ selected, else all pins
  useEffect(() => {
    if (viewState !== "RESULTS" || !hasMapboxToken || !mapRef.current) return;
    const coords = coordsForFitBounds;
    if (coords.length === 0) return;
    const lngs = coords.map((c) => c[0]);
    const lats = coords.map((c) => c[1]);
    let minLng = Math.min(...lngs);
    let maxLng = Math.max(...lngs);
    let minLat = Math.min(...lats);
    let maxLat = Math.max(...lats);
    if (coords.length === 1) {
      const delta = 0.002;
      minLng -= delta;
      maxLng += delta;
      minLat -= delta;
      maxLat += delta;
    }
    const map = mapRef.current.getMap();
    if (!map) return;
    map.fitBounds(
      [
        [minLng, minLat],
        [maxLng, maxLat],
      ],
      { padding: { top: 50, bottom: 350, left: 50, right: 50 }, duration: 800 },
    );
  }, [
    viewState,
    displayMode,
    activeItineraryIndex,
    coordsForFitBounds,
    hasMapboxToken,
  ]);

  // Geocode address using Mapbox
  const geocodeAddress = useCallback(
    async (address: string): Promise<[number, number] | null> => {
      if (!address || !MAPBOX_ACCESS_TOKEN) return null;

      try {
        const response = await fetch(
          `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(address)}.json?access_token=${MAPBOX_ACCESS_TOKEN}&limit=1`,
        );
        const data = await response.json();
        if (data.features && data.features.length > 0) {
          const [lng, lat] = data.features[0].center;
          return [lng, lat];
        }
      } catch (err) {
        console.error("Geocoding error:", err);
      }
      return null;
    },
    [],
  );

  // Transform backend response to frontend format
  const transformBackendResponse = useCallback(
    async (
      backendData: any,
    ): Promise<{
      recommendations: Recommendation[];
      transitInfo: Map<number, any>;
    }> => {
      if (!backendData || !backendData.activities)
        return { recommendations: [], transitInfo: new Map() };

      const activities = backendData.activities;
      const recommendations: Recommendation[] = [];
      const transitInfo = new Map<number, any>();

      // Convert activities object to array and process in order
      const activityEntries = Object.entries(activities).sort((a, b) => {
        const aTime = (a[1] as any).start_time || "";
        const bTime = (b[1] as any).start_time || "";
        return aTime.localeCompare(bTime);
      });

      let venueIndex = 0;

      for (let i = 0; i < activityEntries.length; i++) {
        const [key, activity] = activityEntries[i];
        const act = activity as any;

        // Handle transit activities - store them for arrows between venues
        if (act.type === "transit") {
          // Store transit info with the venue index (will be shown before the next venue)
          transitInfo.set(venueIndex, {
            method: act.method || "walking",
            duration: act.duration_minutes || 15,
            cost: act.cost || 0,
            description: act.description || "",
          });
          continue;
        }

        // Extract time from ISO string
        const startTimeStr = act.start_time
          ? new Date(act.start_time).toLocaleTimeString("en-US", {
              hour: "2-digit",
              minute: "2-digit",
              hour12: false,
            })
          : undefined;

        const endTimeStr = act.end_time
          ? new Date(act.end_time).toLocaleTimeString("en-US", {
              hour: "2-digit",
              minute: "2-digit",
              hour12: false,
            })
          : undefined;

        // Geocode address
        let coordinates: [number, number] | undefined;
        if (act.address) {
          const coords = await geocodeAddress(act.address);
          if (coords) coordinates = coords;
        }

        const recId = key.toLowerCase().replace(/\s+/g, "-");
        recommendations.push({
          id: recId,
          title: act.venue || "Unknown Venue",
          cost: `$${act.cost?.toFixed(2) || "0.00"}`,
          agent_reasoning:
            act.description || "Part of your curated experience.",
          score: "85",
          startTime: startTimeStr,
          endTime: endTimeStr,
          coordinates,
          address: act.address,
          type: act.type || "venue",
        });

        venueIndex++;
      }

      // Already sorted by time from backend, but ensure it
      recommendations.sort((a, b) => {
        if (!a.startTime || !b.startTime) return 0;
        return a.startTime.localeCompare(b.startTime);
      });

      return { recommendations, transitInfo };
    },
    [geocodeAddress],
  );

  const handleSearch = useCallback(async () => {
    // Validate form
    if (!chatInput.trim()) {
      setError("Please enter your request");
      return;
    }
    if (!location) {
      setError("Please select a location");
      return;
    }
    if (!startTime) {
      setError("Please select a start time");
      return;
    }
    if (!endTime) {
      setError("Please select an end time");
      return;
    }

    setError(null);
    setIsLoading(true);
    setViewState("THINKING");

    try {
      const startTimeISO = new Date(startTime).toISOString();
      const endTimeISO = new Date(endTime).toISOString();
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);
      const response = await fetch("http://localhost:8005/api/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_request: chatInput,
          location,
          start_time: startTimeISO,
          end_time: endTimeISO,
        }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (!response.ok) throw new Error(`API error: ${response.statusText}`);
      const result = await response.json();
      if (!result.success) throw new Error(result.error || "Unknown error");
      const { recommendations, transitInfo } = await transformBackendResponse(
        result.data,
      );
      const rest = recommendations.filter((r) => r.id !== ANCHOR_LOCATION.id);
      const recs = [ANCHOR_LOCATION, ...rest];
      setApiRecommendations(recs);
      setTransitInfo(transitInfo);
      setApiBudget(result.data?.budget ?? null);
      setError(null);
      if (recs.length > 0) {
        setViewState("RESULTS");
      } else {
        setError("No activities found");
        setViewState("IDLE");
      }
    } catch (err) {
      console.error("Search error:", err);
      setError(
        err instanceof Error ? err.message : "Failed to create schedule",
      );
      setViewState("IDLE");
    } finally {
      setIsLoading(false);
    }
  }, [chatInput, location, startTime, endTime, transformBackendResponse]);

  const handleAuthorize = useCallback((id: string) => {
    setSelectedIds((prev) => {
      // Impromptu: single selection only — new selection replaces previous
      if (displayMode === "single") {
        return prev.includes(id) ? [] : [id];
      }
      // Itinerary: toggle multi-select
      return prev.includes(id)
        ? prev.filter((x) => x !== id)
        : [...prev, id];
    });
  }, [displayMode]);

  const handleAuthorizeFullItinerary = useCallback(() => {
    const ids = activeGroupItems.map((r) => r.id);
    setSelectedIds((prev) => {
      const allSelected = ids.every((id) => prev.includes(id));
      if (allSelected) return prev.filter((id) => !ids.includes(id));
      const combined = prev.slice();
      ids.forEach((id) => {
        if (!combined.includes(id)) combined.push(id);
      });
      return combined;
    });
  }, [activeGroupItems]);

  // Route line only when 2+ items selected: time-sorted path (e.g. 08:00 Starbucks → next selected)
  const selectionPathGeoJSON = useMemo(() => {
    const selected = itemsForView
      .filter((r) => selectedIds.includes(r.id))
      .slice()
      .sort((a, b) => {
        const sa = a.startTime ? parseTimeToMinutes(a.startTime) : 0;
        const sb = b.startTime ? parseTimeToMinutes(b.startTime) : 0;
        return sa - sb;
      });
    if (selected.length < 2) return null;
    const coords = selected
      .map((r) => getCoords(r))
      .filter((c): c is [number, number] => c !== null);
    if (coords.length < 2) return null;
    return {
      type: "Feature" as const,
      properties: {},
      geometry: { type: "LineString" as const, coordinates: coords },
    };
  }, [itemsForView, selectedIds]);

  const [highlightedCardId, setHighlightedCardId] = useState<string | null>(
    null,
  );

  const scrollToCard = useCallback((id: string) => {
    setHighlightedCardId(id);
    const el = document.getElementById(`card-${id}`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, []);

  useEffect(() => {
    if (!highlightedCardId) return;
    const t = setTimeout(() => setHighlightedCardId(null), 2400);
    return () => clearTimeout(t);
  }, [highlightedCardId]);

  const mapStyle = isDarkMode
    ? "mapbox://styles/mapbox/dark-v11"
    : "mapbox://styles/mapbox/light-v11";

  const drawerBg = isDarkMode ? "bg-slate-900" : "bg-white";
  const drawerText = isDarkMode ? "text-slate-100" : "text-slate-900";
  const drawerMuted = isDarkMode ? "text-slate-400" : "text-slate-500";
  const drawerBorder = isDarkMode ? "border-slate-700" : "border-slate-100";
  const inputBg = isDarkMode ? "bg-slate-800" : "bg-slate-100";
  const cardBg = isDarkMode
    ? "bg-slate-800 border-slate-700"
    : "bg-white border-slate-100";

  // Show login-style loading until we know auth (avoids flashing map then redirect)
  if (!authChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-bg">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-full border-2 border-visa-blue border-t-transparent animate-spin" />
          <p className="text-sm text-slate-muted font-sans">Loading…</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`fixed inset-0 w-full h-[100dvh] min-h-[100dvh] max-h-[100dvh] overflow-hidden font-sans ${
        isDarkMode ? "bg-slate-950" : "bg-slate-100"
      }`}
    >
      {/* Map layer: always full viewport */}
      <div className="absolute inset-0 w-full h-[100dvh] min-h-[100dvh]">
        {hasMapboxToken ? (
          <MapGL
            ref={mapRef}
            mapboxAccessToken={MAPBOX_ACCESS_TOKEN}
            initialViewState={BROWN_VIEWPORT}
            mapStyle={mapStyle}
            style={{ width: "100%", height: "100%" }}
            reuseMaps
          >
            {viewState === "RESULTS" && selectionPathGeoJSON && (
              <Source
                id="selection-path"
                type="geojson"
                data={selectionPathGeoJSON}
              >
                <Layer
                  id="selection-path-line"
                  type="line"
                  paint={{
                    "line-color": "#F7B600",
                    "line-width": 4,
                    "line-dasharray": [2, 2],
                  }}
                />
              </Source>
            )}
            {viewState === "RESULTS" &&
              itemsForView.map((rec) => {
                const coords = getCoords(rec);
                if (!coords) return null;
                const [longitude, latitude] = coords;
                const isSelected = selectedIds.includes(rec.id);
                return (
                  <Marker
                    key={rec.id}
                    longitude={longitude}
                    latitude={latitude}
                    anchor="bottom"
                    onClick={() => scrollToCard(rec.id)}
                  >
                    <div className="flex flex-col items-center cursor-pointer">
                      <button
                        type="button"
                        className="w-8 h-8 rounded-full border-2 border-white shadow-lg flex items-center justify-center hover:scale-110 active:scale-95 transition-transform focus:outline-none focus:ring-2 focus:ring-visa-gold focus:ring-offset-2"
                        style={{
                          backgroundColor: isSelected ? "#F7B600" : "#003399",
                        }}
                        aria-label={`Go to ${rec.title}`}
                      >
                        <MapPin
                          className={`w-3.5 h-3.5 ${isSelected ? "text-slate-900" : "text-white"}`}
                        />
                      </button>
                      <span
                        className="font-sans text-[10px] font-medium whitespace-nowrap mt-0.5 text-white"
                        style={{
                          textShadow:
                            "0 0 2px #000, 0 0 3px #000, 0 1px 2px #000",
                        }}
                      >
                        {rec.title}
                      </span>
                    </div>
                  </Marker>
                );
              })}
          </MapGL>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-slate-100 to-slate-200">
            <div className="flex flex-col items-center gap-3 text-slate-400">
              <MapPin className="w-10 h-10" strokeWidth={1.5} />
              <span className="text-sm font-medium">Map</span>
              <span className="text-xs">
                Set NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN
              </span>
            </div>
          </div>
        )}

        {/* Dark / Light toggle – top right over map */}
        <button
          type="button"
          onClick={() => setIsDarkMode((d) => !d)}
          className={`absolute top-3 right-3 z-10 p-2 rounded-xl shadow-lg transition-colors ${
            isDarkMode
              ? "bg-slate-700 text-visa-gold"
              : "bg-white text-visa-blue"
          }`}
          aria-label={
            isDarkMode ? "Switch to light mode" : "Switch to dark mode"
          }
        >
          {isDarkMode ? <Sun size={20} /> : <Moon size={20} />}
        </button>
      </div>

      {/* IDLE: Floating input window (top-left, Google Maps style) */}
      <AnimatePresence>
        {viewState === "IDLE" && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={transition}
            className={`absolute top-4 left-4 z-30 w-[calc(100%-2rem)] md:w-[420px] ${drawerBg} rounded-2xl shadow-2xl overflow-hidden`}
          >
            {/* Header */}
            <div
              className={`px-4 py-3 flex items-center gap-3 border-b ${drawerBorder}`}
            >
              <div className="p-1.5 rounded-lg bg-visa-blue">
                <Sparkles className="w-4 h-4 text-white" />
              </div>
              <div>
                <h2 className="font-heading text-sm font-bold leading-none tracking-tight">
                  Helping Hand
                </h2>
                <p
                  className={`font-heading text-[10px] font-bold uppercase tracking-tight ${drawerMuted}`}
                >
                  Helping Hand — Powered by Visa Intelligence
                </p>
              </div>
            </div>

            {/* Form */}
            <div className="p-4 space-y-3">
              <p className={`font-sans text-center text-xs ${drawerMuted}`}>
                Where are you? What's your budget?
              </p>

              {/* Location */}
              <div>
                <label
                  className={`block text-xs font-semibold mb-1.5 ${drawerText}`}
                >
                  Location
                </label>
                <input
                  type="text"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="New York City, NY"
                  className={`font-sans w-full ${inputBg} p-3 rounded-xl text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-visa-blue/20 ${drawerText}`}
                />
              </div>

              {/* Start Time */}
              <div>
                <label
                  className={`block text-xs font-semibold mb-1.5 ${drawerText}`}
                >
                  Start Time
                </label>
                <input
                  type="datetime-local"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  className={`font-sans w-full ${inputBg} p-3 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-visa-blue/20 ${drawerText}`}
                />
              </div>

              {/* End Time */}
              <div>
                <label
                  className={`block text-xs font-semibold mb-1.5 ${drawerText}`}
                >
                  End Time
                </label>
                <input
                  type="datetime-local"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                  className={`font-sans w-full ${inputBg} p-3 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-visa-blue/20 ${drawerText}`}
                />
              </div>

              {/* User Request */}
              <div>
                <label
                  className={`block text-xs font-semibold mb-1.5 ${drawerText}`}
                >
                  Your Request
                </label>
                <div className="relative flex items-center gap-2">
                  <input
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                    placeholder="I want to eat, sightsee, and have fun with $200"
                    className={`font-sans w-full ${inputBg} p-3 pr-12 rounded-xl text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-visa-blue/20 ${drawerText}`}
                  />
                  <button
                    onClick={handleSearch}
                    disabled={isLoading}
                    className={`absolute right-2 p-2 bg-visa-blue text-white rounded-xl active:scale-95 transition-transform ${
                      isLoading ? "opacity-50 cursor-not-allowed" : ""
                    }`}
                  >
                    <ArrowUp className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Error Message */}
              {error && (
                <div
                  className={`p-3 rounded-xl text-sm ${isDarkMode ? "bg-red-500/20 text-red-300" : "bg-red-50 text-red-700"}`}
                >
                  {error}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* THINKING: Full-screen overlay */}
      <AnimatePresence>
        {viewState === "THINKING" && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={`absolute inset-0 z-40 ${drawerBg} flex items-center justify-center`}
          >
            <div className="max-w-md mx-auto px-6 space-y-8">
              <div className="flex items-center gap-4">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{
                    duration: 1.5,
                    repeat: Infinity,
                    ease: "linear",
                  }}
                  className="w-10 h-10 rounded-full border-2 border-visa-blue border-t-transparent shrink-0"
                />
                <div>
                  <h3
                    className={`text-2xl font-bold tracking-tight ${drawerText}`}
                  >
                    Analyzing {location || "vendors"}...
                  </h3>
                  <p className={`text-base ${drawerMuted}`}>
                    Finding places that match your budget and style.
                  </p>
                </div>
              </div>
              <div className="space-y-5">
                {[
                  "Scanning local digital-first merchants",
                  "Matching your budget and preferences",
                  "Checking Visa Secure scores for nearby vendors",
                ].map((text, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.6 }}
                    className={`flex items-center gap-3 text-base ${drawerMuted}`}
                  >
                    <div className="w-6 h-6 rounded-full border-2 border-visa-blue border-t-transparent animate-spin shrink-0" />
                    {text}
                  </motion.div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* RESULTS: Left sidebar panel */}
      <AnimatePresence>
        {viewState === "RESULTS" && (
          <motion.div
            initial={{ x: "-100%" }}
            animate={{ x: 0 }}
            exit={{ x: "-100%" }}
            transition={transition}
            className={`absolute top-0 left-0 bottom-0 z-30 w-full md:w-[480px] lg:w-[520px] ${drawerBg} shadow-2xl flex flex-col`}
          >
            {/* Header */}
            <div
              className={`px-4 py-3 flex items-center justify-between border-b ${drawerBorder} shrink-0`}
            >
              <div className="flex items-center gap-3">
                <div className="p-1.5 rounded-lg bg-visa-blue">
                  <Sparkles className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h2 className="font-heading text-sm font-bold leading-none tracking-tight">
                    Helping Hand
                  </h2>
                  <p
                    className={`font-heading text-[10px] font-bold uppercase tracking-tight ${drawerMuted}`}
                  >
                    Helping Hand — Powered by Visa Intelligence
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setViewState("IDLE");
                  setChatInput("");
                  setSelectedIds([]);
                  setLocation("");
                  setStartTime("");
                  setEndTime("");
                  setApiRecommendations([]);
                  setTransitInfo(new Map());
                  setApiBudget(null);
                  setError(null);
                }}
                className={`p-1.5 rounded-full ${
                  isDarkMode
                    ? "bg-slate-700 text-slate-300 hover:bg-slate-600"
                    : "bg-slate-100 text-slate-400 hover:bg-slate-200"
                }`}
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Mode Toggle */}
            <div
              className={`px-4 py-3 flex items-center justify-between gap-3 border-b ${drawerBorder} shrink-0`}
            >
              <span className="font-heading text-xs font-bold uppercase tracking-tight text-slate-500">
                MODE
              </span>
              <div
                className={`flex rounded-xl p-1 ${isDarkMode ? "bg-slate-800" : "bg-slate-100"}`}
                role="group"
                aria-label="Display mode"
              >
                <button
                  type="button"
                  onClick={() => setDisplayMode("single")}
                  className={`font-heading px-3 py-1.5 rounded-lg text-xs font-bold tracking-tight transition-all ${
                    displayMode === "single"
                      ? "bg-white text-visa-blue shadow-sm"
                      : isDarkMode
                        ? "text-slate-400 hover:text-slate-200"
                        : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  Impromptu
                </button>
                <button
                  type="button"
                  onClick={() => setDisplayMode("itinerary")}
                  className={`font-heading px-3 py-1.5 rounded-lg text-xs font-bold tracking-tight transition-all ${
                    displayMode === "itinerary"
                      ? "bg-white text-visa-blue shadow-sm"
                      : isDarkMode
                        ? "text-slate-400 hover:text-slate-200"
                        : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  Itinerary
                </button>
              </div>
            </div>

            {/* Itinerary Group Tabs */}
            {displayMode === "itinerary" && itineraryGroups.length > 1 && (
              <div className={`px-4 py-2 border-b ${drawerBorder} shrink-0`}>
                <div
                  className={`flex gap-1 p-1 rounded-xl ${isDarkMode ? "bg-slate-800" : "bg-slate-100"}`}
                  role="tablist"
                  aria-label="Itinerary group"
                >
                  {itineraryGroups.map((grp, idx) => (
                    <button
                      key={grp.group_name}
                      type="button"
                      role="tab"
                      aria-selected={activeItineraryIndex === idx}
                      onClick={() => setActiveItineraryIndex(idx)}
                      className={`flex-1 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                        activeItineraryIndex === idx
                          ? "bg-white text-visa-blue shadow-sm"
                          : isDarkMode
                            ? "text-slate-400 hover:text-slate-200"
                            : "text-slate-500 hover:text-slate-800"
                      }`}
                    >
                      {grp.group_name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Results Header */}
            <div
              className={`px-4 py-3 flex items-center justify-between gap-2 border-b ${drawerBorder} shrink-0`}
            >
              <h3
                className={`font-heading font-bold text-xs uppercase tracking-widest ${drawerMuted}`}
              >
                {displayMode === "itinerary"
                  ? (itineraryGroups[activeItineraryIndex]?.group_name ??
                    "Itinerary")
                  : "Recommended for You"}
              </h3>
              <span
                className={`font-price text-xs font-bold px-2 py-1.5 rounded-md tracking-tighter ${
                  isDarkMode
                    ? "bg-visa-gold/25 text-visa-gold border border-visa-gold/50"
                    : "text-visa-blue bg-[#003399]/10"
                }`}
                title={
                  displayMode === "itinerary"
                    ? "Budget after full itinerary"
                    : "Updates in real time as you add/remove items"
                }
              >
                Budget: ${remainingBudget.toFixed(2)}
              </span>
            </div>

            {/* Scrollable Results */}
            <div
              className={`flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 min-h-0 ${
                isDarkMode ? "scrollbar-drawer-dark" : "scrollbar-drawer"
              }`}
            >
              {displayMode === "single" ? (
                <div className="space-y-4">
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
                <div className="w-full pl-2">
                  {activeGroupItems.length === 0 ? (
                    <p
                      className={`font-sans py-8 text-center text-sm ${drawerMuted}`}
                    >
                      No stops in this itinerary.
                    </p>
                  ) : (
                    <>
                      <div className="space-y-6">
                        {activeGroupItems.map((rec, index) => {
                          const transit = transitInfo.get(index);
                          const showTransit = transit && index > 0;

                          return (
                            <React.Fragment key={rec.id}>
                              {showTransit && (
                                <div className="flex items-center justify-center py-2">
                                  <div
                                    className={`flex items-center gap-2 px-4 py-2 rounded-lg ${isDarkMode ? "bg-slate-800" : "bg-slate-100"}`}
                                  >
                                    <ArrowRight
                                      className={`w-4 h-4 ${drawerMuted}`}
                                    />
                                    <span
                                      className={`text-xs font-medium ${drawerMuted}`}
                                    >
                                      {transit.method} • {transit.duration} min
                                      {transit.cost > 0 &&
                                        ` • $${transit.cost.toFixed(2)}`}
                                    </span>
                                  </div>
                                </div>
                              )}
                              <ItineraryCard
                                rec={rec}
                                isSelected={selectedIds.includes(rec.id)}
                                isHighlighted={highlightedCardId === rec.id}
                                cardBg={cardBg}
                                drawerText={drawerText}
                                drawerMuted={drawerMuted}
                                isDarkMode={isDarkMode}
                                onAuthorize={handleAuthorize}
                              />
                            </React.Fragment>
                          );
                        })}
                      </div>
                      <div className={`mt-6 pt-6 border-t ${drawerBorder}`}>
                        <button
                          type="button"
                          onClick={handleAuthorizeFullItinerary}
                          className={`font-heading w-full py-4 rounded-xl font-bold text-sm tracking-tight transition-all ${
                            activeGroupItems.every((r) =>
                              selectedIds.includes(r.id),
                            )
                              ? "bg-visa-gold text-slate-900 hover:bg-visa-gold/90"
                              : "bg-visa-blue text-white hover:bg-visa-blue-dark"
                          }`}
                        >
                          {activeGroupItems.every((r) =>
                            selectedIds.includes(r.id),
                          ) ? (
                            "✓ Full itinerary in plan — tap to remove"
                          ) : (
                            <>
                              Authorize Full Itinerary —{" "}
                              <span className="font-price">
                                ${itineraryTotalCost.toFixed(2)}
                              </span>
                            </>
                          )}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>

            {/* Refine Search Input */}
            <div
              className={`p-4 border-t ${drawerBorder} ${drawerBg} shrink-0`}
            >
              <div className="relative flex items-center gap-2">
                <input
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  placeholder="Refine search — e.g. add more budget..."
                  className={`font-sans flex-1 ${inputBg} p-3 pr-12 rounded-xl text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-visa-blue/20 ${drawerText}`}
                />
                <button
                  onClick={handleSearch}
                  className="absolute right-2 p-2 bg-visa-blue text-white rounded-xl active:scale-95 transition-transform"
                >
                  <ArrowUp className="w-5 h-5" />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
