"use client";

import React, {
  useState,
  useMemo,
  useCallback,
  useRef,
  useEffect,
} from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence, Reorder } from "framer-motion";
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
  ArrowRight,
  User,
  Trash2,
  LogOut,
  Settings,
  ChevronDown,
  Info,
} from "lucide-react";
import insightsData from "@/data/insights.json";
import { City } from "country-state-city";
import "mapbox-gl/dist/mapbox-gl.css";

type ViewState = "IDLE" | "THINKING" | "RESULTS";

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
};

function parseCost(costStr: string): number {
  return parseFloat(costStr.replace(/[^0-9.]/g, "")) || 0;
}

/** "09:00" -> minutes since midnight for comparison */
function parseTimeToMinutes(t: string): number {
  const [h, m] = t.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

/** Minutes since midnight -> "09:00" */
function minutesToTimeStr(minutes: number): string {
  const h = Math.floor(minutes / 60) % 24;
  const m = Math.round(minutes % 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
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

/** Flat list of all items (dedupe by id) for static fallback data */
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

/** Memoized Itinerary card — builder mode: remove button, no authorize button; all items active */
const ItineraryCard = React.memo(function ItineraryCard_({
  rec,
  isHighlighted,
  cardBg,
  drawerText,
  drawerMuted,
  isDarkMode,
  builderMode,
  onRemove,
  displayStartTime,
  displayEndTime,
}: {
  rec: Recommendation;
  isHighlighted: boolean;
  cardBg: string;
  drawerText: string;
  drawerMuted: string;
  isDarkMode: boolean;
  builderMode: boolean;
  onRemove?: (id: string) => void;
  displayStartTime?: string;
  displayEndTime?: string;
}) {
  const text = rec.agent_reasoning ?? "Part of this itinerary.";
  const showReadMore = text.length > READ_MORE_THRESHOLD;
  const [expanded, setExpanded] = React.useState(false);
  const startTime = displayStartTime ?? rec.startTime;
  const endTime = displayEndTime ?? rec.endTime;

  return (
    <article
      id={`card-${rec.id}`}
      className={`flex flex-col h-full min-h-0 border rounded-2xl p-6 shadow-sm scroll-mt-4 transition-shadow min-w-0 ${cardBg} ${
        isHighlighted
          ? "card-highlight-pulse ring-2 ring-visa-blue ring-offset-2"
          : ""
      }`}
    >
      <div className="flex items-center gap-2 mb-3 shrink-0">
        <div className="flex-1 min-w-0">
          <span className={`font-sans text-xs font-bold ${drawerText}`}>
            {startTime && formatTimeLabel(startTime)} –{" "}
            {endTime ? formatTimeLabel(endTime) : "—"}
          </span>
        </div>
        <span className={`font-price font-bold text-sm shrink-0 ${drawerText}`}>
          {rec.cost}
        </span>
        {builderMode && onRemove && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onRemove(rec.id);
            }}
            className={`p-1.5 rounded-lg shrink-0 ${
              isDarkMode
                ? "hover:bg-slate-700 text-slate-300"
                : "hover:bg-slate-200 text-slate-500"
            }`}
            aria-label={`Remove ${rec.title}`}
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>
      <div className="flex flex-col flex-grow min-h-0 overflow-hidden">
        <div className="flex flex-col gap-0.5 mb-1">
          <span
            className={`trust-badge text-[10px] md:text-xs font-bold px-2 py-0.5 rounded border flex items-center gap-1 w-fit uppercase ${
              isDarkMode
                ? "bg-emerald-500/25 text-emerald-300 border-emerald-500/50"
                : "bg-emerald-50 text-emerald-700 border-emerald-100"
            }`}
          >
            <ShieldCheck className="w-3 h-3 shrink-0" />{" "}
            Verified Vendor
          </span>
          <span
            className={`font-sans text-[10px] flex items-center gap-0.5 ${drawerMuted}`}
            title="Verified via Google Maps (10+ reviews)"
          >
            <Info className="w-3 h-3 shrink-0" aria-hidden />
            Verified via Google Maps (10+ reviews)
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
  const [activeItineraryIndex, setActiveItineraryIndex] = useState(0);
  const mapRef = useRef<MapRef | null>(null);

  // Redirect to login if no session, or to onboarding if not completed
  useEffect(() => {
    const token =
      typeof localStorage !== "undefined"
        ? localStorage.getItem("session_token")
        : null;
    if (!token) {
      router.replace("/login");
      return;
    }
    
    // Check onboarding status and load user data
    const checkOnboarding = async () => {
      try {
        const { verifySession } = await import("@/lib/auth");
        const result = await verifySession(token);
        if (result.success && result.onboarding_required) {
          router.replace("/onboarding");
          return;
        }
        if (result.success && result.user) {
          setUser(result.user);
        }
        setAuthChecked(true);
      } catch (err) {
        console.error("Failed to verify session:", err);
        // If verification fails, still allow access (might be dev mode)
        setAuthChecked(true);
      }
    };
    
    checkOnboarding();
  }, [router]);

  const handleLogout = useCallback(async () => {
    const token = typeof localStorage !== "undefined"
      ? localStorage.getItem("session_token")
      : null;
    
    if (token) {
      try {
        const AUTH_API_URL = process.env.NEXT_PUBLIC_AUTH_API_URL ?? '';
        if (AUTH_API_URL) {
          await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/logout`, {
            method: "POST",
            headers: {
              "Authorization": `Bearer ${token}`,
              "Content-Type": "application/json",
            },
          });
        }
      } catch (err) {
        console.error("Logout error:", err);
      }
    }
    
    localStorage.removeItem("session_token");
    router.replace("/login");
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
  const [itineraryOrder, setItineraryOrder] = useState<string[]>([]);
  const [timeOverrides, setTimeOverrides] = useState<
    Record<string, { startTime: string; endTime: string }>
  >({});
  const [isBooking, setIsBooking] = useState(false);
  const [bookingResult, setBookingResult] = useState<any>(null);
  const [user, setUser] = useState<any>(null);
  const [showUserMenu, setShowUserMenu] = useState(false);

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

  // Use API recommendations if available, otherwise fall back to static data.
  const recommendations = useMemo(() => {
    return apiRecommendations.length > 0
      ? apiRecommendations
      : flattenRecommendations(itinerariesData);
  }, [apiRecommendations]);

  // Create itinerary groups from API data or static data.
  const itineraryGroups = useMemo(() => {
    if (apiRecommendations.length > 0) {
      return [
        {
          group_name: `${location} Itinerary`,
          items: [...apiRecommendations],
        },
      ];
    }
    return itinerariesData;
  }, [apiRecommendations, location]);

  // Sync itinerary order when API results change: time-sorted ids
  useEffect(() => {
    if (apiRecommendations.length === 0) {
      setItineraryOrder([]);
      setTimeOverrides({});
      return;
    }
    const items = [...apiRecommendations];
    items.sort((a, b) => {
      const sa = a.startTime ? parseTimeToMinutes(a.startTime) : 0;
      const sb = b.startTime ? parseTimeToMinutes(b.startTime) : 0;
      return sa - sb;
    });
    setItineraryOrder(items.map((r) => r.id));
    setTimeOverrides({});
  }, [apiRecommendations]);

  const activeGroupItems = useMemo(() => {
    if (!itineraryGroups[activeItineraryIndex]) return [];
    const items = itineraryGroups[activeItineraryIndex].items.slice();
    if (itineraryOrder.length > 0) {
      const orderMap = new Map(itineraryOrder.map((id, i) => [id, i]));
      items.sort((a, b) => (orderMap.get(a.id) ?? 999) - (orderMap.get(b.id) ?? 999));
    } else {
      items.sort((a, b) => {
        const sa = a.startTime ? parseTimeToMinutes(a.startTime) : 0;
        const sb = b.startTime ? parseTimeToMinutes(b.startTime) : 0;
        return sa - sb;
      });
    }
    return items;
  }, [activeItineraryIndex, itineraryGroups, itineraryOrder]);

  const itemsForView = activeGroupItems;

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
  }, [activeItineraryIndex]);

  const coordsForFitBounds = useMemo(() => {
    return activeGroupItems
      .map((r) => getCoords(r))
      .filter((c): c is [number, number] => c !== null);
  }, [activeGroupItems]);

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
      { padding: { top: 80, bottom: 80, left: 80, right: 80 }, duration: 800 },
    );
  }, [viewState, activeItineraryIndex, coordsForFitBounds, hasMapboxToken]);

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
      backendError?: string;
    }> => {
      if (!backendData)
        return { recommendations: [], transitInfo: new Map() };

      // Backend may return error payload (orchestrator / intent dispatcher / agents)
      if (backendData.type === "error") {
        const d = backendData.data;
        let msg: string | null =
          typeof backendData.message === "string" ? backendData.message : null;
        if (!msg && typeof d === "object" && d !== null) {
          const raw = d.error ?? d.message;
          msg = typeof raw === "string" ? raw : null;
        }
        if (!msg) msg = typeof backendData.error === "string" ? backendData.error : null;
        if (!msg && typeof d === "string") msg = d;
        return {
          recommendations: [],
          transitInfo: new Map(),
          backendError: msg || "Request failed",
        };
      }
      // Top-level "error" (e.g. bridge/Gemini fallback)
      if (backendData.error) {
        return {
          recommendations: [],
          transitInfo: new Map(),
          backendError: String(backendData.error),
        };
      }

      // Activities can be at top level or under .data (nested response)
      let activities =
        backendData.activities ??
        backendData.data?.activities ??
        null;
      if (!activities || (typeof activities === "object" && !Object.keys(activities).length))
        return { recommendations: [], transitInfo: new Map() };

      // Normalize: backend may return array (e.g. some fallbacks)
      if (Array.isArray(activities)) {
        activities = Object.fromEntries(
          activities.map((a: any, i: number) => [`Activity ${i + 1}`, a])
        );
      }
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

    const controller = new AbortController();
    let timeoutId: NodeJS.Timeout | null = null;
    let isTimeout = false;

    try {
      const startTimeISO = new Date(startTime).toISOString();
      const endTimeISO = new Date(endTime).toISOString();
      
      // Set timeout to abort after 60 seconds (backend can take up to 30s for orchestrator + startup time)
      timeoutId = setTimeout(() => {
        isTimeout = true;
        controller.abort();
      }, 600000);

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

      // Clear timeout if request completed successfully
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }

      if (!response.ok) throw new Error(`API error: ${response.statusText}`);
      const result = await response.json();
      if (!result.success) throw new Error(result.error || "Unknown error");
      const { recommendations, transitInfo, backendError } =
        await transformBackendResponse(result.data);
      setApiRecommendations(recommendations);
      setTransitInfo(transitInfo);
      setApiBudget(result.data?.budget ?? null);
      setError(null);
      if (backendError) {
        setError(backendError);
        setViewState("IDLE");
      } else if (recommendations.length > 0) {
        setViewState("RESULTS");
      } else {
        setError("No activities found. Try a different location or request.");
        setViewState("IDLE");
      }
    } catch (err) {
      // Clear timeout in case of error
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }

      // Handle AbortError specifically
      if (err instanceof Error && err.name === "AbortError") {
        if (isTimeout) {
          setError("Request timed out. Please try again or check your connection.");
        } else {
          setError("Request was cancelled.");
        }
      } else {
        console.error("Search error:", err);
        setError(
          err instanceof Error ? err.message : "Failed to create schedule",
        );
      }
      setViewState("IDLE");
    } finally {
      // Ensure timeout is always cleared
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      setIsLoading(false);
    }
  }, [chatInput, location, startTime, endTime, transformBackendResponse]);

  const handleAuthorize = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }, []);

  const handleRemoveItineraryItem = useCallback((id: string) => {
    setApiRecommendations((prev) => prev.filter((r) => r.id !== id));
    setItineraryOrder((prev) => prev.filter((x) => x !== id));
    setSelectedIds((prev) => prev.filter((x) => x !== id));
    setTimeOverrides((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  const handleReorder = useCallback((newOrder: Recommendation[]) => {
    setItineraryOrder(newOrder.map((r) => r.id));
    const overrides: Record<string, { startTime: string; endTime: string }> = {};
    let runningMinutes =
      newOrder.length > 0
        ? (() => {
            const first = newOrder[0];
            const start = timeOverrides[first.id]?.startTime ?? first.startTime;
            return start ? parseTimeToMinutes(start) : 9 * 60;
          })()
        : 9 * 60;
    for (const rec of newOrder) {
      const override = timeOverrides[rec.id];
      const start = override?.startTime ?? rec.startTime;
      const end = override?.endTime ?? rec.endTime;
      const durationMinutes =
        start && end
          ? Math.max(1, parseTimeToMinutes(end) - parseTimeToMinutes(start))
          : 60;
      overrides[rec.id] = {
        startTime: minutesToTimeStr(runningMinutes),
        endTime: minutesToTimeStr(runningMinutes + durationMinutes),
      };
      runningMinutes += durationMinutes;
    }
    setTimeOverrides(overrides);
  }, [timeOverrides]);

  const [showPaymentModal, setShowPaymentModal] = useState(false);

  const checkPaymentMethod = useCallback(async (): Promise<boolean> => {
    const token = typeof localStorage !== "undefined"
      ? localStorage.getItem("session_token")
      : null;
    
    if (!token) return false;
    
    try {
      const AUTH_API_URL = process.env.NEXT_PUBLIC_AUTH_API_URL ?? '';
      if (!AUTH_API_URL) return true; // Skip check if no auth API
      
      const response = await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/payment-methods/check`, {
        method: "GET",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      
      if (!response.ok) return false;
      const result = await response.json();
      return result.has_payment_methods === true;
    } catch (err) {
      console.error("Payment method check error:", err);
      return false;
    }
  }, []);

  const handleConfirmAndBook = useCallback(async () => {
    const itemsToBook = activeGroupItems;
    if (itemsToBook.length === 0) {
      setError("Please select at least one activity to book");
      return;
    }

    const hasPaymentMethod = await checkPaymentMethod();
    if (!hasPaymentMethod) {
      setShowPaymentModal(true);
      return;
    }

    setIsBooking(true);
    setError(null);
    setBookingResult(null);

    try {
      const selectedItems = itemsToBook.map((r) => ({
          id: r.id,
          title: r.title,
          cost: r.cost,
          startTime: timeOverrides[r.id]?.startTime ?? r.startTime,
          endTime: timeOverrides[r.id]?.endTime ?? r.endTime,
          address: r.address,
          coordinates: r.coordinates,
          agent_reasoning: r.agent_reasoning,
        }));

      const response = await fetch("http://localhost:8005/api/booking", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          items: selectedItems,
          location: location || "Unknown",
        }),
      });

      if (!response.ok) throw new Error(`API error: ${response.statusText}`);
      const result = await response.json();
      
      if (!result.success) {
        throw new Error(result.error || "Unknown error");
      }

      setBookingResult(result.data);
      setError(null);
    } catch (err) {
      console.error("Booking error:", err);
      setError(
        err instanceof Error ? err.message : "Failed to process booking",
      );
      setBookingResult(null);
    } finally {
      setIsBooking(false);
    }
  }, [activeGroupItems, location, checkPaymentMethod, timeOverrides]);

  // Dashed gold path: only when 2+ items, redraws on reorder/remove
  const selectionPathGeoJSON = useMemo(() => {
    if (activeGroupItems.length < 2) return null;
    const coords = activeGroupItems
      .map((r) => getCoords(r))
      .filter((c): c is [number, number] => c !== null);
    if (coords.length < 2) return null;
    return {
      type: "Feature" as const,
      properties: {},
      geometry: { type: "LineString" as const, coordinates: coords },
    };
  }, [activeGroupItems]);

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
              activeGroupItems.map((rec) => {
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
                    <div className="flex flex-col items-center cursor-pointer">
                      <button
                        type="button"
                        className="w-8 h-8 rounded-full border-2 border-white shadow-lg flex items-center justify-center hover:scale-110 active:scale-95 transition-transform focus:outline-none focus:ring-2 focus:ring-visa-gold focus:ring-offset-2"
                        style={{ backgroundColor: "#F7B600" }}
                        aria-label={`Go to ${rec.title}`}
                      >
                        <MapPin className="w-3.5 h-3.5 text-slate-900" />
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

        {/* User menu and Dark / Light toggle – top right over map */}
        <div className="absolute top-3 right-3 z-10 flex items-center gap-2">
          {/* Dark / Light toggle */}
          <button
            type="button"
            onClick={() => setIsDarkMode((d) => !d)}
            className={`p-2 rounded-xl shadow-lg transition-colors ${
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
          
          {/* User menu */}
          {user && (
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowUserMenu(!showUserMenu)}
                className={`flex items-center gap-2 px-3 py-2 rounded-xl shadow-lg transition-colors ${
                  isDarkMode
                    ? "bg-slate-700 text-slate-100 hover:bg-slate-600"
                    : "bg-white text-slate-900 hover:bg-slate-50"
                }`}
                aria-label="User menu"
              >
                <User size={18} />
                <span className="text-sm font-medium hidden sm:inline">
                  {user.username || user.email?.split("@")[0] || "User"}
                </span>
                <ChevronDown size={16} className={showUserMenu ? "rotate-180" : ""} />
              </button>
              
              {showUserMenu && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowUserMenu(false)}
                  />
                  <div
                    className={`absolute right-0 mt-2 w-48 rounded-xl shadow-xl z-20 ${
                      isDarkMode ? "bg-slate-800" : "bg-white"
                    } border ${isDarkMode ? "border-slate-700" : "border-slate-200"}`}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        setShowUserMenu(false);
                        router.push("/profile");
                      }}
                      className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-100 transition-colors first:rounded-t-xl ${
                        isDarkMode
                          ? "hover:bg-slate-700 text-slate-100"
                          : "text-slate-900"
                      }`}
                    >
                      <Settings size={18} />
                      <span className="text-sm font-medium">Profile & Settings</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleLogout}
                      className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-100 transition-colors last:rounded-b-xl ${
                        isDarkMode
                          ? "hover:bg-slate-700 text-slate-100"
                          : "text-slate-900"
                      }`}
                    >
                      <LogOut size={18} />
                      <span className="text-sm font-medium">Logout</span>
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
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
                  setItineraryOrder([]);
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

            {/* Itinerary Group Tabs */}
            {itineraryGroups.length > 1 && (
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
                {itineraryGroups[activeItineraryIndex]?.group_name ?? "Itinerary"}
              </h3>
              <span
                className={`font-price text-xs font-bold px-2 py-1.5 rounded-md tracking-tighter ${
                  isDarkMode
                    ? "bg-visa-gold/25 text-visa-gold border border-visa-gold/50"
                    : "text-visa-blue bg-[#003399]/10"
                }`}
                title="Budget after full itinerary"
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
              <div className="w-full pl-2">
                {activeGroupItems.length === 0 ? (
                    <p
                      className={`font-sans py-8 text-center text-sm ${drawerMuted}`}
                    >
                      No stops in this itinerary.
                    </p>
                  ) : (
                    <>
                      <Reorder.Group
                        as="div"
                        axis="y"
                        values={activeGroupItems}
                        onReorder={handleReorder}
                        className="flex flex-col gap-6 list-none p-0 m-0"
                      >
                        {activeGroupItems.map((rec) => (
                          <Reorder.Item
                            key={rec.id}
                            value={rec}
                            className="relative cursor-grab active:cursor-grabbing touch-none"
                            style={{ listStyle: "none" }}
                          >
                            <ItineraryCard
                              rec={rec}
                              isHighlighted={highlightedCardId === rec.id}
                              cardBg={cardBg}
                              drawerText={drawerText}
                              drawerMuted={drawerMuted}
                              isDarkMode={isDarkMode}
                              builderMode
                              onRemove={handleRemoveItineraryItem}
                              displayStartTime={timeOverrides[rec.id]?.startTime}
                              displayEndTime={timeOverrides[rec.id]?.endTime}
                            />
                          </Reorder.Item>
                        ))}
                      </Reorder.Group>
                      <div className={`mt-6 pt-6 border-t ${drawerBorder}`}>
                        <button
                          type="button"
                          onClick={handleConfirmAndBook}
                          disabled={isBooking || activeGroupItems.length === 0}
                          className={`font-heading w-full py-4 rounded-xl font-bold text-sm tracking-tight transition-all ${
                            isBooking || activeGroupItems.length === 0
                              ? "bg-slate-400 text-white cursor-not-allowed"
                              : "bg-visa-gold text-slate-900 hover:bg-visa-gold/90 shadow-lg"
                          }`}
                        >
                          {isBooking ? (
                            <>
                              <span className="inline-block animate-spin mr-2">⏳</span>
                              Processing…
                            </>
                          ) : (
                            <>
                              Confirm and Pay —{" "}
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
            </div>

            {/* Booking Results */}
            {bookingResult && (
              <div
                className={`p-4 border-t ${drawerBorder} ${drawerBg} shrink-0 max-h-64 overflow-y-auto ${
                  isDarkMode ? "scrollbar-drawer-dark" : "scrollbar-drawer"
                }`}
              >
                <h4 className={`font-heading font-bold text-sm mb-2 ${drawerText}`}>
                  Booking Results
                </h4>
                <div className="space-y-2">
                  {bookingResult.bookings?.map((booking: any, idx: number) => (
                    <div
                      key={idx}
                      className={`p-2 rounded-lg text-xs ${
                        booking.booking_status === "success"
                          ? isDarkMode
                            ? "bg-emerald-500/20 text-emerald-300"
                            : "bg-emerald-50 text-emerald-700"
                          : booking.booking_status === "payment_required"
                            ? isDarkMode
                              ? "bg-yellow-500/20 text-yellow-300"
                              : "bg-yellow-50 text-yellow-700"
                            : isDarkMode
                              ? "bg-slate-700 text-slate-300"
                              : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      <div className="font-semibold">{booking.item_title}</div>
                      <div className="text-[10px] mt-0.5">
                        {booking.booking_status === "success" && (
                          <>
                            ✓ Booked
                            {booking.confirmation_code && (
                              <> • Code: {booking.confirmation_code}</>
                            )}
                            {booking.payment_status === "paid" && (
                              <> • Paid: ${booking.payment_amount?.toFixed(2)}</>
                            )}
                          </>
                        )}
                        {booking.booking_status === "payment_required" && (
                          <>⚠ Payment required at venue</>
                        )}
                        {booking.booking_status === "not_required" && (
                          <>ℹ No booking required</>
                        )}
                        {booking.error_message && (
                          <div className="mt-1 text-red-400">
                            {booking.error_message}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                {bookingResult.summary && (
                  <div className={`mt-3 pt-3 border-t ${drawerBorder} text-xs ${drawerMuted}`}>
                    <div>
                      Total Paid: ${bookingResult.total_paid?.toFixed(2) || "0.00"}
                    </div>
                    <div>
                      Items Booked: {bookingResult.summary.items_booked_successfully || 0}
                    </div>
                  </div>
                )}
              </div>
            )}

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

      {/* Payment Method Required Modal */}
      <AnimatePresence>
        {showPaymentModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
            onClick={() => setShowPaymentModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className={`w-full max-w-md ${drawerBg} rounded-2xl shadow-2xl p-6`}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className={`font-heading text-lg font-bold ${drawerText}`}>
                  Payment Method Required
                </h3>
                <button
                  type="button"
                  onClick={() => setShowPaymentModal(false)}
                  className={`p-1 rounded-lg ${isDarkMode ? "hover:bg-slate-700" : "hover:bg-slate-100"}`}
                >
                  <X size={20} className={drawerMuted} />
                </button>
              </div>
              
              <p className={`font-sans text-sm mb-6 ${drawerMuted}`}>
                You need to add a payment method before booking activities. Please set up a payment method in your profile.
              </p>
              
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setShowPaymentModal(false)}
                  className={`flex-1 py-2.5 px-4 rounded-xl font-medium text-sm transition-colors ${
                    isDarkMode
                      ? "bg-slate-700 text-slate-200 hover:bg-slate-600"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  }`}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowPaymentModal(false);
                    router.push("/profile");
                  }}
                  className="flex-1 py-2.5 px-4 rounded-xl font-medium text-sm bg-visa-blue text-white hover:bg-visa-blue-dark transition-colors"
                >
                  Go to Profile
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
