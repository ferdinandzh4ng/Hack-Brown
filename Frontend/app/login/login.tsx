'use client';

import React, { useEffect } from 'react';
import Link from 'next/link';
import { UserPlus, Sparkles } from 'lucide-react';
import LoginForm from '@/components/LoginForm';
import { googleSignIn } from '@/lib/auth';

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (config: { client_id: string; callback: (response: { credential?: string }) => void }) => void;
          renderButton: (el: HTMLElement | null, options: { theme: string; size: string; type: string }) => void;
        };
      };
    };
  }
}

export default function LoginPage() {
  useEffect(() => {
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!clientId) return;

    const existing = document.getElementById('google-js');
    if (existing) return;

    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.id = 'google-js';
    script.async = true;
    script.defer = true;
    document.head.appendChild(script);

    script.onload = () => {
      if (window.google?.accounts?.id) {
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: async (response: { credential?: string }) => {
            const idToken = response?.credential;
            if (idToken) {
              try {
                const data = await googleSignIn(idToken);
                if (data?.token) {
                  if (typeof localStorage !== 'undefined') {
                    localStorage.setItem('session_token', data.token);
                  }
                  // Redirect to onboarding if required, otherwise to home
                  if (data?.onboarding_required) {
                    window.location.href = '/onboarding';
                  } else {
                    window.location.href = '/';
                  }
                } else {
                  console.error('Google sign-in failed', data);
                }
              } catch (err) {
                console.error('Google sign-in network error', err);
              }
            }
          },
        });
        const btnEl = document.getElementById('gsi-button');
        if (btnEl) {
          window.google.accounts.id.renderButton(btnEl, {
            theme: 'filled_blue',
            size: 'large',
            type: 'standard',
          });
        }
      }
    };
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-bg safe-area-padding px-4 py-12">
      <div className="max-w-md w-full bg-white rounded-3xl shadow-visa-card p-8 border border-slate-border">
        <div className="flex flex-col items-center gap-3 mb-6">
          <div className="p-2.5 rounded-xl bg-visa-blue">
            <Sparkles className="w-6 h-6 text-white" />
          </div>
          <h1 className="font-heading text-2xl font-bold text-visa-blue">
            Sign in to Hack-Brown
          </h1>
          <p className="text-sm text-slate-muted text-center">
            Plan trips and get personalized recommendations.
          </p>
        </div>

        <div className="space-y-4">
          <LoginForm
            onSuccess={(token) => {
              if (typeof localStorage !== 'undefined') {
                localStorage.setItem('session_token', token);
              }
              // Check onboarding status - LoginForm will handle redirect if needed
              window.location.href = '/';
            }}
          />

          <div className="flex items-center gap-3">
            <hr className="flex-1 border-slate-border" />
            <span className="text-sm text-slate-muted">or</span>
            <hr className="flex-1 border-slate-border" />
          </div>

          <div id="gsi-button" className="w-full flex justify-center min-h-[44px]" />

          <Link
            href="/register"
            className="font-heading w-full py-3 md:py-4 rounded-xl font-bold text-sm md:text-base border-2 border-visa-blue text-visa-blue bg-transparent hover:bg-visa-blue/5 transition-colors inline-flex items-center justify-center gap-2"
          >
            <UserPlus className="w-4 h-4" />
            Sign up
          </Link>

          <p className="text-center text-sm text-slate-muted">
            Already have an account? You&apos;re on the sign-in page.
          </p>
        </div>
      </div>
    </div>
  );
}
