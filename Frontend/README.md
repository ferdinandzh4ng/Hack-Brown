# Visa Intelligent Commerce (VIC)

Mobile-first React/Next.js demo showing how AI helps users spend money in their community **without using cash**. Secure, premium, agentic UI.

## Design

- **Visa Blue** `#003399`, **Visa Gold** `#F7B600`, clean slate grays
- Mobile-first, touch-friendly, safe-area aware
- “Agentic” feel: AI reasoning visible per recommendation, agent banner, trust badges

## Data (no backend)

- **`data/community-insights.json`** — Community trends, digital adoption, merchant highlights
- **`data/user-history.json`** — User profile, recent activity, agent reasoning inputs
- **`data/insights.json`** — AI-style recommendations (simulated from the above)

Edit these JSON files to change recommendations and copy.

## Run

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Build: `npm run build`.

## Stack

- Next.js 14 (App Router), React 18, TypeScript
- Tailwind CSS (Visa design tokens in `tailwind.config.ts`)
- Lucide React icons
- No backend; all data from static JSON
