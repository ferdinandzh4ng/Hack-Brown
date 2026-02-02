"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  User,
  CreditCard,
  Settings,
  ArrowLeft,
  Plus,
  Trash2,
  Check,
  X,
  MapPin,
  Calendar,
  Clock,
  DollarSign,
} from "lucide-react";

const AUTH_API_URL = process.env.NEXT_PUBLIC_AUTH_API_URL ?? "";

interface PaymentMethod {
  id: string;
  last_4: string;
  expiry_date: string;
  cardholder_name: string;
  is_default: boolean;
  billing_address?: any;
}

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"preferences" | "payment" | "itineraries">("preferences");
  const [showAddPayment, setShowAddPayment] = useState(false);
  const [trips, setTrips] = useState<any[]>([]);
  const [loadingTrips, setLoadingTrips] = useState(false);
  const [expandedTrips, setExpandedTrips] = useState<Set<string>>(new Set());
  const [isDarkMode, setIsDarkMode] = useState(false);
  
  // Payment form state
  const [cardNumber, setCardNumber] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [cardholderName, setCardholderName] = useState("");
  const [cvv, setCvv] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Preferences state
  const [favoriteActivities, setFavoriteActivities] = useState<string[]>([]);
  const [favoriteStores, setFavoriteStores] = useState<string[]>([]);
  const [budgetRange, setBudgetRange] = useState({ min: 0, max: 1000 });
  const [savingPrefs, setSavingPrefs] = useState(false);

  useEffect(() => {
    const token = typeof localStorage !== "undefined"
      ? localStorage.getItem("session_token")
      : null;
    
    if (!token) {
      router.replace("/login");
      return;
    }

    loadUserData(token);
    loadPaymentMethods(token);
    loadTrips(token);
  }, [router]);

  const loadUserData = async (token: string) => {
    try {
      const { verifySession } = await import("@/lib/auth");
      const result = await verifySession(token);
      if (result.success && result.user) {
        setUser(result.user);
        const prefs = result.user.preferences || {};
        setFavoriteActivities(prefs.activity_categories || []);
        setFavoriteStores(prefs.favorite_stores || []);
        setBudgetRange(prefs.budget_range || { min: 0, max: 1000 });
      }
    } catch (err) {
      console.error("Failed to load user data:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadPaymentMethods = async (token: string) => {
    if (!AUTH_API_URL) return;
    
    try {
      const response = await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/payment-methods`, {
        method: "GET",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      
      if (response.ok) {
        const result = await response.json();
        setPaymentMethods(result.payment_methods || []);
      }
    } catch (err) {
      console.error("Failed to load payment methods:", err);
    }
  };

  const handleAddPaymentMethod = async () => {
    const token = typeof localStorage !== "undefined"
      ? localStorage.getItem("session_token")
      : null;
    
    if (!token || !AUTH_API_URL) {
      setError("Authentication required");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const response = await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/payment-methods`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          card_number: cardNumber.replace(/\s/g, ""),
          expiry_date: expiryDate,
          cardholder_name: cardholderName,
          cvv: cvv,
          is_default: isDefault,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to add payment method");
      }

      // Reset form
      setCardNumber("");
      setExpiryDate("");
      setCardholderName("");
      setCvv("");
      setIsDefault(false);
      setShowAddPayment(false);
      
      // Reload payment methods
      await loadPaymentMethods(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add payment method");
    } finally {
      setSaving(false);
    }
  };

  const handleDeletePaymentMethod = async (id: string) => {
    const token = typeof localStorage !== "undefined"
      ? localStorage.getItem("session_token")
      : null;
    
    if (!token || !AUTH_API_URL) return;

    if (!confirm("Are you sure you want to delete this payment method?")) return;

    try {
      const response = await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/payment-methods/${id}`, {
        method: "DELETE",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        await loadPaymentMethods(token);
      }
    } catch (err) {
      console.error("Failed to delete payment method:", err);
    }
  };

  const handleSetDefault = async (id: string) => {
    const token = typeof localStorage !== "undefined"
      ? localStorage.getItem("session_token")
      : null;
    
    if (!token || !AUTH_API_URL) return;

    try {
      const response = await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/payment-methods/default`, {
        method: "PUT",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ payment_method_id: id }),
      });

      if (response.ok) {
        await loadPaymentMethods(token);
      }
    } catch (err) {
      console.error("Failed to set default payment method:", err);
    }
  };

  const loadTrips = async (token: string) => {
    if (!AUTH_API_URL) return;
    
    setLoadingTrips(true);
    try {
      const response = await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/trips`, {
        method: "GET",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      
      if (response.ok) {
        const result = await response.json();
        setTrips(result.trips || []);
      }
    } catch (err) {
      console.error("Failed to load trips:", err);
    } finally {
      setLoadingTrips(false);
    }
  };

  const handleDeleteTrip = async (tripId: string) => {
    const token = typeof localStorage !== "undefined"
      ? localStorage.getItem("session_token")
      : null;
    
    if (!token || !AUTH_API_URL) return;

    if (!confirm("Are you sure you want to delete this trip?")) return;

    try {
      const response = await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/trips/${tripId}`, {
        method: "DELETE",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        await loadTrips(token);
      }
    } catch (err) {
      console.error("Failed to delete trip:", err);
    }
  };

  const handleSavePreferences = async () => {
    const token = typeof localStorage !== "undefined"
      ? localStorage.getItem("session_token")
      : null;
    
    if (!token || !AUTH_API_URL) {
      setError("Authentication required");
      return;
    }

    setSavingPrefs(true);
    setError(null);

    try {
      const response = await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/preferences`, {
        method: "PUT",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          favorite_activities: favoriteActivities,
          favorite_stores: favoriteStores,
          budget_range: budgetRange,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to update preferences");
      }

      alert("Preferences saved successfully!");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update preferences");
    } finally {
      setSavingPrefs(false);
    }
  };

  const formatCardNumber = (value: string) => {
    const v = value.replace(/\s+/g, "").replace(/[^0-9]/gi, "");
    const matches = v.match(/\d{4,16}/g);
    const match = (matches && matches[0]) || "";
    const parts = [];
    for (let i = 0, len = match.length; i < len; i += 4) {
      parts.push(match.substring(i, i + 4));
    }
    if (parts.length) {
      return parts.join(" ");
    } else {
      return v;
    }
  };

  const formatExpiry = (value: string) => {
    const v = value.replace(/\s+/g, "").replace(/[^0-9]/gi, "");
    if (v.length >= 2) {
      return v.substring(0, 2) + "/" + v.substring(2, 4);
    }
    return v;
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-full border-2 border-visa-blue border-t-transparent animate-spin" />
          <p className="text-sm text-slate-600 font-sans">Loading...</p>
        </div>
      </div>
    );
  }

  const drawerBg = isDarkMode ? "bg-slate-900" : "bg-white";
  const drawerText = isDarkMode ? "text-slate-100" : "text-slate-900";
  const drawerMuted = isDarkMode ? "text-slate-400" : "text-slate-500";
  const drawerBorder = isDarkMode ? "border-slate-700" : "border-slate-100";
  const inputBg = isDarkMode ? "bg-slate-800" : "bg-slate-100";

  return (
    <div className={`min-h-screen overflow-y-auto ${isDarkMode ? "bg-slate-950" : "bg-slate-100"}`}>
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <button
            type="button"
            onClick={() => router.back()}
            className={`p-2 rounded-xl ${isDarkMode ? "bg-slate-800 hover:bg-slate-700" : "bg-white hover:bg-slate-50"} transition-colors`}
          >
            <ArrowLeft size={20} className={drawerText} />
          </button>
          <h1 className={`text-2xl font-bold ${drawerText}`}>Profile & Settings</h1>
        </div>

        {/* Tabs */}
        <div className={`flex gap-2 mb-6 p-1 rounded-xl ${isDarkMode ? "bg-slate-800" : "bg-white"}`}>
          <button
            type="button"
            onClick={() => setActiveTab("preferences")}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg font-medium transition-all ${
              activeTab === "preferences"
                ? "bg-visa-blue text-white"
                : isDarkMode
                  ? "text-slate-400 hover:text-slate-200"
                  : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Settings size={18} />
            Preferences
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("payment")}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg font-medium transition-all ${
              activeTab === "payment"
                ? "bg-visa-blue text-white"
                : isDarkMode
                  ? "text-slate-400 hover:text-slate-200"
                  : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <CreditCard size={18} />
            Payment Methods
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("itineraries")}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg font-medium transition-all ${
              activeTab === "itineraries"
                ? "bg-visa-blue text-white"
                : isDarkMode
                  ? "text-slate-400 hover:text-slate-200"
                  : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <MapPin size={18} />
            Itineraries
          </button>
        </div>

        {/* Preferences Tab */}
        {activeTab === "preferences" && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className={`${drawerBg} rounded-2xl p-6 shadow-lg`}
          >
            <h2 className={`text-lg font-bold mb-4 ${drawerText}`}>Activity Preferences</h2>
            
            <div className="space-y-4 mb-6">
              <div>
                <label className={`block text-sm font-medium mb-2 ${drawerText}`}>
                  Favorite Activities
                </label>
                <input
                  type="text"
                  value={favoriteActivities.join(", ")}
                  onChange={(e) => setFavoriteActivities(e.target.value.split(",").map(s => s.trim()).filter(Boolean))}
                  placeholder="e.g., dining, sightseeing, entertainment"
                  className={`w-full ${inputBg} p-3 rounded-xl text-sm ${drawerText} focus:outline-none focus:ring-2 focus:ring-visa-blue/20`}
                />
              </div>

              <div>
                <label className={`block text-sm font-medium mb-2 ${drawerText}`}>
                  Favorite Stores
                </label>
                <input
                  type="text"
                  value={favoriteStores.join(", ")}
                  onChange={(e) => setFavoriteStores(e.target.value.split(",").map(s => s.trim()).filter(Boolean))}
                  placeholder="e.g., Starbucks, Target, Apple Store"
                  className={`w-full ${inputBg} p-3 rounded-xl text-sm ${drawerText} focus:outline-none focus:ring-2 focus:ring-visa-blue/20`}
                />
              </div>

              <div>
                <label className={`block text-sm font-medium mb-2 ${drawerText}`}>
                  Budget Range
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    value={budgetRange.min}
                    onChange={(e) => setBudgetRange({ ...budgetRange, min: parseInt(e.target.value) || 0 })}
                    placeholder="Min"
                    className={`flex-1 ${inputBg} p-3 rounded-xl text-sm ${drawerText} focus:outline-none focus:ring-2 focus:ring-visa-blue/20`}
                  />
                  <span className={drawerMuted}>to</span>
                  <input
                    type="number"
                    value={budgetRange.max}
                    onChange={(e) => setBudgetRange({ ...budgetRange, max: parseInt(e.target.value) || 1000 })}
                    placeholder="Max"
                    className={`flex-1 ${inputBg} p-3 rounded-xl text-sm ${drawerText} focus:outline-none focus:ring-2 focus:ring-visa-blue/20`}
                  />
                </div>
              </div>
            </div>

            {error && (
              <div className={`p-3 rounded-xl text-sm mb-4 ${isDarkMode ? "bg-red-500/20 text-red-300" : "bg-red-50 text-red-700"}`}>
                {error}
              </div>
            )}

            <button
              type="button"
              onClick={handleSavePreferences}
              disabled={savingPrefs}
              className="w-full py-3 px-4 rounded-xl font-medium bg-visa-blue text-white hover:bg-visa-blue-dark transition-colors disabled:opacity-50"
            >
              {savingPrefs ? "Saving..." : "Save Preferences"}
            </button>
          </motion.div>
        )}

        {/* Payment Methods Tab */}
        {activeTab === "payment" && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className={`${drawerBg} rounded-2xl p-6 shadow-lg`}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className={`text-lg font-bold ${drawerText}`}>Payment Methods</h2>
              <button
                type="button"
                onClick={() => setShowAddPayment(!showAddPayment)}
                className="flex items-center gap-2 px-4 py-2 rounded-xl font-medium bg-visa-blue text-white hover:bg-visa-blue-dark transition-colors"
              >
                <Plus size={18} />
                Add Payment Method
              </button>
            </div>

            {/* Add Payment Form */}
            {showAddPayment && (
              <div className={`mb-6 p-4 rounded-xl border ${drawerBorder}`}>
                <h3 className={`font-medium mb-4 ${drawerText}`}>Add New Payment Method</h3>
                <div className="space-y-3">
                  <input
                    type="text"
                    value={cardNumber}
                    onChange={(e) => setCardNumber(formatCardNumber(e.target.value))}
                    placeholder="Card Number"
                    maxLength={19}
                    className={`w-full ${inputBg} p-3 rounded-xl text-sm ${drawerText} focus:outline-none focus:ring-2 focus:ring-visa-blue/20`}
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <input
                      type="text"
                      value={expiryDate}
                      onChange={(e) => setExpiryDate(formatExpiry(e.target.value))}
                      placeholder="MM/YY"
                      maxLength={5}
                      className={`w-full ${inputBg} p-3 rounded-xl text-sm ${drawerText} focus:outline-none focus:ring-2 focus:ring-visa-blue/20`}
                    />
                    <input
                      type="text"
                      value={cvv}
                      onChange={(e) => setCvv(e.target.value.replace(/\D/g, "").slice(0, 4))}
                      placeholder="CVV"
                      maxLength={4}
                      className={`w-full ${inputBg} p-3 rounded-xl text-sm ${drawerText} focus:outline-none focus:ring-2 focus:ring-visa-blue/20`}
                    />
                  </div>
                  <input
                    type="text"
                    value={cardholderName}
                    onChange={(e) => setCardholderName(e.target.value)}
                    placeholder="Cardholder Name"
                    className={`w-full ${inputBg} p-3 rounded-xl text-sm ${drawerText} focus:outline-none focus:ring-2 focus:ring-visa-blue/20`}
                  />
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={isDefault}
                      onChange={(e) => setIsDefault(e.target.checked)}
                      className="w-4 h-4 rounded"
                    />
                    <span className={`text-sm ${drawerText}`}>Set as default payment method</span>
                  </label>
                  {error && (
                    <div className={`p-2 rounded text-xs ${isDarkMode ? "bg-red-500/20 text-red-300" : "bg-red-50 text-red-700"}`}>
                      {error}
                    </div>
                  )}
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setShowAddPayment(false);
                        setCardNumber("");
                        setExpiryDate("");
                        setCardholderName("");
                        setCvv("");
                        setIsDefault(false);
                        setError(null);
                      }}
                      className="flex-1 py-2 px-4 rounded-xl font-medium bg-slate-200 text-slate-700 hover:bg-slate-300 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleAddPaymentMethod}
                      disabled={saving || !cardNumber || !expiryDate || !cardholderName || !cvv}
                      className="flex-1 py-2 px-4 rounded-xl font-medium bg-visa-blue text-white hover:bg-visa-blue-dark transition-colors disabled:opacity-50"
                    >
                      {saving ? "Adding..." : "Add"}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Payment Methods List */}
            <div className="space-y-3">
              {paymentMethods.length === 0 ? (
                <p className={`text-center py-8 ${drawerMuted}`}>
                  No payment methods added yet. Click "Add Payment Method" to get started.
                </p>
              ) : (
                paymentMethods.map((method) => (
                  <div
                    key={method.id}
                    className={`flex items-center justify-between p-4 rounded-xl border ${drawerBorder} ${
                      method.is_default ? "ring-2 ring-visa-blue" : ""
                    }`}
                  >
                    <div className="flex items-center gap-4">
                      <CreditCard size={24} className={drawerMuted} />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className={`font-medium ${drawerText}`}>
                            •••• •••• •••• {method.last_4}
                          </span>
                          {method.is_default && (
                            <span className="text-xs px-2 py-0.5 rounded bg-visa-blue text-white">
                              Default
                            </span>
                          )}
                        </div>
                        <div className={`text-sm ${drawerMuted}`}>
                          {method.cardholder_name} • Expires {method.expiry_date}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {!method.is_default && (
                        <button
                          type="button"
                          onClick={() => handleSetDefault(method.id)}
                          className="p-2 rounded-lg hover:bg-slate-100 transition-colors"
                          title="Set as default"
                        >
                          <Check size={18} className={drawerMuted} />
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleDeletePaymentMethod(method.id)}
                        className="p-2 rounded-lg hover:bg-red-50 transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={18} className="text-red-500" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}

        {/* Itineraries Tab */}
        {activeTab === "itineraries" && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className={`${drawerBg} rounded-2xl p-6 shadow-lg max-h-[calc(100vh-200px)] overflow-y-auto`}
          >
            <h2 className={`text-lg font-bold mb-4 ${drawerText}`}>Saved Itineraries</h2>
            
            {loadingTrips ? (
              <div className="flex items-center justify-center py-8">
                <div className="w-8 h-8 rounded-full border-2 border-visa-blue border-t-transparent animate-spin" />
              </div>
            ) : trips.length === 0 ? (
              <p className={`text-center py-8 ${drawerMuted}`}>
                No saved itineraries yet. Create a trip to see it here.
              </p>
            ) : (
              <div className="space-y-4">
                {trips.map((trip) => (
                  <div
                    key={trip.trip_id}
                    className={`p-4 rounded-xl border ${drawerBorder} ${
                      isDarkMode ? "bg-slate-800" : "bg-slate-50"
                    }`}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <MapPin size={18} className={drawerMuted} />
                          <h3 className={`font-semibold ${drawerText}`}>{trip.location}</h3>
                        </div>
                        <div className={`flex items-center gap-4 text-sm ${drawerMuted}`}>
                          <div className="flex items-center gap-1">
                            <Calendar size={14} className={drawerMuted} />
                            <span className={drawerMuted}>
                              {trip.start_time ? new Date(trip.start_time).toLocaleDateString() : "N/A"} - {trip.end_time ? new Date(trip.end_time).toLocaleDateString() : "N/A"}
                            </span>
                          </div>
                          {trip.budget && (
                            <span className={drawerMuted}>
                              Budget: ${trip.budget.toFixed(2)}
                            </span>
                          )}
                        </div>
                        {trip.user_request && (
                          <p className={`text-sm mt-2 ${drawerMuted} line-clamp-2`}>
                            {trip.user_request}
                          </p>
                        )}
                        {trip.itinerary && trip.itinerary.length > 0 && (
                          <button
                            type="button"
                            onClick={() => {
                              const newExpanded = new Set(expandedTrips);
                              if (newExpanded.has(trip.trip_id)) {
                                newExpanded.delete(trip.trip_id);
                              } else {
                                newExpanded.add(trip.trip_id);
                              }
                              setExpandedTrips(newExpanded);
                            }}
                            className={`text-xs mt-2 ${drawerMuted} hover:underline flex items-center gap-1`}
                          >
                            {trip.itinerary.length} activity{trip.itinerary.length !== 1 ? 'ies' : 'y'}
                            <span className="text-[10px]">
                              {expandedTrips.has(trip.trip_id) ? '▼' : '▶'}
                            </span>
                          </button>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => handleDeleteTrip(trip.trip_id)}
                        className="p-2 rounded-lg hover:bg-red-50 transition-colors ml-2"
                        title="Delete"
                      >
                        <Trash2 size={18} className="text-red-500" />
                      </button>
                    </div>
                    
                    {/* Expanded Activities List */}
                    {expandedTrips.has(trip.trip_id) && trip.itinerary && trip.itinerary.length > 0 && (
                      <div className={`mt-4 pt-4 border-t ${drawerBorder} space-y-3`}>
                        {trip.itinerary
                          .sort((a: any, b: any) => {
                            // Sort by start_time if available
                            if (a.start_time && b.start_time) {
                              return new Date(a.start_time).getTime() - new Date(b.start_time).getTime();
                            }
                            return 0;
                          })
                          .map((activity: any, idx: number) => (
                            <div
                              key={activity.id || idx}
                              className={`p-3 rounded-lg ${
                                isDarkMode ? "bg-slate-700/50" : "bg-white"
                              } border ${drawerBorder}`}
                            >
                              <div className="flex items-start justify-between mb-2">
                                <h4 className={`font-semibold text-sm ${drawerText}`}>
                                  {activity.title || activity.venue || `Activity ${idx + 1}`}
                                </h4>
                                {activity.cost !== undefined && (
                                  <span className={`text-sm font-medium ${drawerText} flex items-center gap-1`}>
                                    <DollarSign size={14} />
                                    {typeof activity.cost === 'number' ? activity.cost.toFixed(2) : activity.cost}
                                  </span>
                                )}
                              </div>
                              
                              {(activity.start_time || activity.end_time) && (
                                <div className={`flex items-center gap-2 text-xs ${drawerMuted} mb-2`}>
                                  <Clock size={12} />
                                  <span>
                                    {(() => {
                                      const formatTime = (timeStr: string) => {
                                        if (!timeStr) return '';
                                        
                                        // If it's already a time string like "09:00" or "9:00 AM"
                                        if (typeof timeStr === 'string' && timeStr.match(/^\d{1,2}:\d{2}/)) {
                                          const [hours, minutes] = timeStr.split(':');
                                          const hour = parseInt(hours, 10);
                                          const min = minutes.split(' ')[0];
                                          const period = hour >= 12 ? 'PM' : 'AM';
                                          const displayHour = hour % 12 || 12;
                                          return `${displayHour}:${min.padStart(2, '0')} ${period}`;
                                        }
                                        
                                        // Try to parse as date
                                        try {
                                          const date = new Date(timeStr);
                                          if (!isNaN(date.getTime())) {
                                            return date.toLocaleTimeString('en-US', { 
                                              hour: 'numeric', 
                                              minute: '2-digit',
                                              hour12: true 
                                            });
                                          }
                                        } catch (e) {
                                          // If parsing fails, return the string as-is
                                          return timeStr;
                                        }
                                        
                                        return timeStr;
                                      };
                                      
                                      const start = formatTime(activity.start_time);
                                      const end = formatTime(activity.end_time);
                                      
                                      if (start && end) {
                                        return `${start} - ${end}`;
                                      } else if (start) {
                                        return start;
                                      } else if (end) {
                                        return end;
                                      }
                                      return 'TBD';
                                    })()}
                                  </span>
                                </div>
                              )}
                              
                              {activity.description && (
                                <p className={`text-xs ${drawerMuted} line-clamp-2`}>
                                  {activity.description}
                                </p>
                              )}
                              
                              {activity.address && (
                                <div className={`flex items-center gap-1 text-xs ${drawerMuted} mt-2`}>
                                  <MapPin size={10} />
                                  <span className="line-clamp-1">{activity.address}</span>
                                </div>
                              )}
                            </div>
                          ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </div>
    </div>
  );
}

