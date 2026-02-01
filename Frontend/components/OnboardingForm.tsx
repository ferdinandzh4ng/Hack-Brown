'use client';

import React, { useState } from 'react';
import { Check, Sparkles, ArrowRight } from 'lucide-react';

interface OnboardingFormProps {
  onComplete: () => void;
  token: string;
}

const ACTIVITIES = [
  { id: 'dining', label: 'Dining & Restaurants', icon: '🍽️' },
  { id: 'sightseeing', label: 'Sightseeing & Tours', icon: '🏛️' },
  { id: 'shopping', label: 'Shopping', icon: '🛍️' },
  { id: 'entertainment', label: 'Entertainment & Shows', icon: '🎭' },
  { id: 'nightlife', label: 'Nightlife & Bars', icon: '🍸' },
  { id: 'outdoor', label: 'Outdoor Activities', icon: '🏞️' },
  { id: 'museums', label: 'Museums & Galleries', icon: '🎨' },
  { id: 'sports', label: 'Sports & Recreation', icon: '⚽' },
  { id: 'wellness', label: 'Wellness & Spa', icon: '🧘' },
  { id: 'events', label: 'Events & Festivals', icon: '🎪' },
];

const STORES = [
  { id: 'target', label: 'Target', icon: '🎯' },
  { id: 'walmart', label: 'Walmart', icon: '🏪' },
  { id: 'amazon', label: 'Amazon', icon: '📦' },
  { id: 'apple', label: 'Apple Store', icon: '🍎' },
  { id: 'nike', label: 'Nike', icon: '✓' },
  { id: 'starbucks', label: 'Starbucks', icon: '☕' },
  { id: 'whole-foods', label: 'Whole Foods', icon: '🥬' },
  { id: 'best-buy', label: 'Best Buy', icon: '📺' },
  { id: 'home-depot', label: 'Home Depot', icon: '🔨' },
  { id: 'costco', label: 'Costco', icon: '🛒' },
  { id: 'macy', label: "Macy's", icon: '👔' },
  { id: 'nordstrom', label: "Nordstrom", icon: '👗' },
];

export default function OnboardingForm({ onComplete, token }: OnboardingFormProps) {
  const [step, setStep] = useState<'activities' | 'stores'>('activities');
  const [selectedActivities, setSelectedActivities] = useState<string[]>([]);
  const [selectedStores, setSelectedStores] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleActivity = (activityId: string) => {
    setSelectedActivities(prev =>
      prev.includes(activityId)
        ? prev.filter(id => id !== activityId)
        : [...prev, activityId]
    );
  };

  const toggleStore = (storeId: string) => {
    setSelectedStores(prev =>
      prev.includes(storeId)
        ? prev.filter(id => id !== storeId)
        : [...prev, storeId]
    );
  };

  const handleNext = () => {
    if (step === 'activities') {
      if (selectedActivities.length === 0) {
        setError('Please select at least one activity');
        return;
      }
      setStep('stores');
      setError(null);
    }
  };

  const handleComplete = async () => {
    if (selectedStores.length === 0) {
      setError('Please select at least one store');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const AUTH_API_URL = process.env.NEXT_PUBLIC_AUTH_API_URL ?? '';
      if (!AUTH_API_URL) {
        throw new Error('Auth API not configured');
      }

      const res = await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/onboarding`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          favorite_activities: selectedActivities,
          favorite_stores: selectedStores,
        }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data?.message ?? 'Failed to complete onboarding');
      }

      onComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-bg safe-area-padding px-4 py-12">
      <div className="max-w-2xl w-full bg-white rounded-3xl shadow-visa-card p-8 border border-slate-border">
        <div className="flex flex-col items-center gap-3 mb-8">
          <div className="p-2.5 rounded-xl bg-visa-blue">
            <Sparkles className="w-6 h-6 text-white" />
          </div>
          <h1 className="font-heading text-2xl font-bold text-visa-blue">
            Welcome! Let's personalize your experience
          </h1>
          <p className="text-sm text-slate-muted text-center">
            Tell us about your preferences to get better recommendations
          </p>
        </div>

        {/* Progress indicator */}
        <div className="mb-8">
          <div className="flex items-center justify-center gap-2">
            <div className={`h-2 w-16 rounded-full ${step === 'activities' ? 'bg-visa-blue' : 'bg-slate-200'}`} />
            <div className={`h-2 w-16 rounded-full ${step === 'stores' ? 'bg-visa-blue' : 'bg-slate-200'}`} />
          </div>
          <div className="flex items-center justify-center gap-16 mt-2">
            <span className={`text-xs font-semibold ${step === 'activities' ? 'text-visa-blue' : 'text-slate-muted'}`}>
              Activities
            </span>
            <span className={`text-xs font-semibold ${step === 'stores' ? 'text-visa-blue' : 'text-slate-muted'}`}>
              Stores
            </span>
          </div>
        </div>

        {error && (
          <div className="mb-6 p-3 rounded-xl text-sm bg-red-50 text-red-700 border border-red-100">
            {error}
          </div>
        )}

        {step === 'activities' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-slate-900 mb-4">
                What activities do you enjoy? (Select all that apply)
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {ACTIVITIES.map(activity => (
                  <button
                    key={activity.id}
                    type="button"
                    onClick={() => toggleActivity(activity.id)}
                    className={`p-4 rounded-xl border-2 transition-all text-left ${
                      selectedActivities.includes(activity.id)
                        ? 'border-visa-blue bg-visa-blue/5'
                        : 'border-slate-border hover:border-slate-300'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl">{activity.icon}</span>
                        <span className="text-sm font-medium text-slate-900">
                          {activity.label}
                        </span>
                      </div>
                      {selectedActivities.includes(activity.id) && (
                        <Check className="w-5 h-5 text-visa-blue" />
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>
            <button
              type="button"
              onClick={handleNext}
              disabled={selectedActivities.length === 0}
              className="font-heading w-full py-3 md:py-4 rounded-xl font-bold text-sm md:text-base bg-visa-blue text-white hover:bg-visa-blue-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              Continue
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {step === 'stores' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-slate-900 mb-4">
                Which stores do you prefer? (Select all that apply)
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {STORES.map(store => (
                  <button
                    key={store.id}
                    type="button"
                    onClick={() => toggleStore(store.id)}
                    className={`p-4 rounded-xl border-2 transition-all text-left ${
                      selectedStores.includes(store.id)
                        ? 'border-visa-blue bg-visa-blue/5'
                        : 'border-slate-border hover:border-slate-300'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl">{store.icon}</span>
                        <span className="text-sm font-medium text-slate-900">
                          {store.label}
                        </span>
                      </div>
                      {selectedStores.includes(store.id) && (
                        <Check className="w-5 h-5 text-visa-blue" />
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => {
                  setStep('activities');
                  setError(null);
                }}
                className="font-heading flex-1 py-3 md:py-4 rounded-xl font-bold text-sm md:text-base bg-slate-100 text-slate-900 hover:bg-slate-200 transition-colors"
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleComplete}
                disabled={loading || selectedStores.length === 0}
                className="font-heading flex-1 py-3 md:py-4 rounded-xl font-bold text-sm md:text-base bg-visa-blue text-white hover:bg-visa-blue-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {loading ? 'Saving...' : 'Complete'}
                {!loading && <ArrowRight className="w-4 h-4" />}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

