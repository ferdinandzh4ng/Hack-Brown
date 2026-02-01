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
  const [activeTab, setActiveTab] = useState<"preferences" | "payment">("preferences");
  const [showAddPayment, setShowAddPayment] = useState(false);
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
    <div className={`min-h-screen ${isDarkMode ? "bg-slate-950" : "bg-slate-100"}`}>
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
      </div>
    </div>
  );
}

