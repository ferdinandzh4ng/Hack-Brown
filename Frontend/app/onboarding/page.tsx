'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import OnboardingForm from '@/components/OnboardingForm';

export default function OnboardingPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Get token from localStorage
    if (typeof window !== 'undefined') {
      const storedToken = localStorage.getItem('session_token');
      if (!storedToken) {
        // No token, redirect to login
        router.push('/login');
        return;
      }
      setToken(storedToken);
      setLoading(false);
    }
  }, [router]);

  const handleComplete = () => {
    // Redirect to home page after onboarding
    router.push('/');
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-bg">
        <div className="text-slate-muted">Loading...</div>
      </div>
    );
  }

  if (!token) {
    return null; // Will redirect
  }

  return <OnboardingForm onComplete={handleComplete} token={token} />;
}

