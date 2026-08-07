# C1 – Product Requirements (v1 MVP)

## Vision
C1 is a premium, AI-powered mobile nutrition, calorie tracking, and weight-management app for iOS + Android. Main "wow" moment: photograph a meal → Gemini 3 Flash vision identifies foods, portions, and full macro breakdown → user confirms → meal is logged in the diary.

## Brand
- Name: **C1** ("C" + "1" mark; gold circle logo on obsidian background)
- Palette: Obsidian dark surfaces + Antique Gold (`#D4AF37`) accent
- Fonts: Outfit (display) + IBM Plex Sans (body); RTL-ready
- Tagline: "Your AI nutrition coach"

## v1 Scope (this build)
1. **Auth** – Email/password registration + login (JWT), logout, account deletion
2. **Onboarding** – 5-step flow: gender/age → height → weight/target → activity → goal
3. **Calorie engine** – Mifflin-St Jeor BMR → activity-adjusted TDEE → goal-adjusted daily calories; protein/carbs/fat + water targets computed live
4. **Dashboard** – Calorie ring, macro bars, water tracker with quick add, weight snapshot, streak, prominent Scan CTA
5. **AI Meal Scanner** – Camera OR gallery → base64 → Gemini 3 Flash vision → structured `{items:[{name, portion_g, calories, protein_g, carbs_g, fat_g, fiber_g, sugar_g}]}` → confirmation screen with per-item editable fields + meal-type selector → log to diary
6. **Food Diary** – Day view grouped by Breakfast/Lunch/Dinner/Snack, per-group totals, delete meals
7. **AI Coach Chat** – Gemini 3 Flash with user profile & targets injected as context; persisted chat history; 3 suggested prompts
8. **Water / Weight logs** – Quick-add water in 250 ml increments; weight logs synced to profile
9. **Profile & settings** – Targets summary, language switcher (EN/AR/DE/ES/FR + RTL), Premium toggle (stub), logout, delete account
10. **Premium paywall** – Cinematic paywall with intro €4.99/3mo + monthly €1.99/mo plans; MOCKED subscription (real Apple/Google IAP added at native build time)

## Architecture / Ownership
- Backend: FastAPI + MongoDB (all data in Mongo the user owns)
- AI: Gemini 3 Flash via `emergentintegrations` — provider is modular (single `AI_TEXT_MODEL` / `AI_VISION_MODEL` const in `server.py`) and easily swappable
- Auth: JWT (HS256), bcrypt password hashing
- Frontend: Expo SDK 54 + expo-router file-based routing
- Languages: 5 languages with in-app switcher, `I18nManager.forceRTL` for Arabic
- Payments (v1): stubbed toggle. Real Apple IAP + Google Play Billing to be wired when user builds native binaries through Emergent publish flow, using the user's own Apple Developer + Google Play Console accounts.

## Deferred (post-MVP)
- Barcode scanner, meal recommendations, personalized meal plans, progress photos, weight/measurement charts, notifications, Google / Apple Sign-In, real IAP + PayPal/Stripe web checkout.

## Testing accounts
See `/app/memory/test_credentials.md`.
