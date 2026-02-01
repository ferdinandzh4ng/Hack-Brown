# Helping Hand / Visa Intelligent Commerce — Style Guide

## Typography

All UI text must use one of three font families. Use the Tailwind utility classes so fonts stay consistent.

| Use case | Tailwind class | Font | When to use |
|----------|----------------|------|-------------|
| **Body** | `font-sans` | Inter | Body copy, descriptions, form labels, inputs, placeholders, small labels, badges, error messages. |
| **Headings & UI** | `font-heading` | Plus Jakarta Sans | App title, section headers, card titles, buttons, mode toggles, tab labels, any bold UI label. |
| **Numbers / prices** | `font-price` | JetBrains Mono | Costs, budget amounts, prices, any numeric display. |

### Rules

- **Headings and buttons**: Always use `font-heading` (Plus Jakarta Sans) for titles, CTAs, and primary UI labels.
- **Body and forms**: Use `font-sans` (Inter) for paragraphs, labels, inputs, and secondary text.
- **Money and numbers**: Use `font-price` (JetBrains Mono) for dollar amounts and numeric data.

Fonts are loaded in `app/layout.tsx` and defined in `tailwind.config.ts` under `theme.extend.fontFamily`.
