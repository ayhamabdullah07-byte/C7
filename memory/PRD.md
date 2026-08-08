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
- Barcode scanner, ~~meal recommendations~~ ✅ done, personalized meal plans (weekly), progress photos, weight/measurement charts, notifications, Google / Apple Sign-In, real IAP + PayPal/Stripe web checkout.

## Feature: Complete My Day (Premium) – added
- `POST /api/ai/recommend` — Gemini 3 Flash returns 3 meal + 3 snack ideas that fit the user's remaining daily budget. Focus filters: any / high_protein / low_calorie / vegetarian / vegan / quick.
- `POST /api/ai/recommend/refine` — Takes a single item + natural-language request ("under 500 cal", "replace chicken with beef", "vegetarian", "faster to prepare"). Returns the same item with updated ingredients and recalculated macros. Same `id` preserved.
- Screen `/app/frontend/app/recommend.tsx` — Premium-gated. Remaining-budget card, filter chip row, meal + snack sections, per-card "Talk to C1" bottom sheet with quick-ask chips and live macro updates, one-tap "Add to diary".
- Dashboard entry: `home-complete-day` card routes premium → `/recommend`, free → `/paywall`.

## Feature: Forgot Password – added
- `POST /api/auth/forgot-password` — generic 200 for any email (no user enumeration). If registered, mints a 6-digit code, stores SHA-256 hash in `password_resets` collection with 15-min TTL, sends a branded HTML email via Emergent-managed Resend integration (`EMERGENT_EMAIL_KEY` + `EMAIL_FROM_NAME=C1`).
- `POST /api/auth/reset-password` — accepts email + code + new_password. Constant-time hmac compare on hash; caps at 5 attempts per code; bcrypt-updates the user password; invalidates the code on use. Requesting a new code invalidates prior unused codes for that email.
- Login screen now shows "Forgot Password?" link (`testID='login-forgot-password'`) directly below the password input.
- New screen `/(auth)/forgot-password.tsx` with two stages: request-code and verify (code + new password) + resend option.

## Plans, Scan Quotas & Notifications (this iteration)
- **Plan field** on user (`free` / `premium` / `plus`). Legacy `premium` bool derived (`true` iff plan is premium or plus).
- **Scan-limit enforcement** – server-side via `scan_logs` collection with 24h rolling window per user. Free = 4, Premium = 20, Plus = unlimited (fair-use cap 60). Failed/invalid scans do NOT count. `GET /api/scan-quota` returns `{plan, limit, used, remaining, fair_use_limit, blocked, reset_at}`. Scan endpoint returns HTTP 429 with structured detail when blocked.
- **Plus-only gate** on `/api/ai/recommend` and `/api/ai/recommend/refine` (HTTP 402 `plus_required` for free/premium).
- **Plan setter** `POST /api/auth/plan {plan}` (stub; real Apple IAP + Google Play Billing at native build). Legacy `/auth/premium-toggle` now cycles free → premium → plus → free.
- **Paywall** rebuilt with 3 tier cards: Free €0, Premium €1.99/mo, Plus €4.99/mo (highlighted).
- **Profile** shows current plan badge, live 24h scan-quota card, and a **Daily Reminders** switch that appears only for Plus users. Enabling schedules 2 local daily reminders (11:00 lunch nudge, 19:00 evening remaining-calories) via `expo-notifications`. Requests OS permission on enable; safe no-op on web preview.
- **Multilingual login tagline** – new i18n key `loginTagline` in EN/AR/DE/ES/FR ("C1 is with you every step to your goal" / "C1 معك لتصل إلى هدفك" / German / Spanish / French translations).
- **Scan FAB** moved to bottom-left, slightly higher (left:20, bottom:124).

## Testing accounts
See `/app/memory/test_credentials.md`.
