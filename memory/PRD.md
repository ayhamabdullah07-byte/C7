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
- **Plan field** on user (`free` / `premium` / `plus`). **Derived** from verified `subscriptions` — never client-set. Legacy `premium` bool derived (`true` iff plan is premium or plus).
- **Scan-limit enforcement** – server-side via `scan_logs` collection with 24h rolling window per user. Free = 4, Premium = 20, Plus = unlimited (fair-use cap 60). Failed/invalid scans do NOT count. `GET /api/scan-quota` returns `{plan, limit, used, remaining, fair_use_limit, blocked, reset_at}`. Scan endpoint returns HTTP 429 with structured detail when blocked.
- **Plus-only gate** on `/api/ai/recommend` and `/api/ai/recommend/refine` (HTTP 402 `plus_required` for free/premium).
- ~~`POST /api/auth/plan {plan}`~~ / ~~`/auth/premium-toggle`~~ — **REMOVED in Phase 1**. Both return HTTP 410 Gone. Plan changes only via verified IAP receipts (Phase 2/3).
- **Paywall** rebuilt with 3 tier cards: Free $0, Premium $1.99/mo, Plus $4.99/mo (highlighted). Prices are preview only — actual charge is the store's localized price.
- **Profile** shows current plan badge, live 24h scan-quota card, and a **Daily Reminders** switch that appears only for Plus users.
- **Multilingual login tagline** – i18n key `loginTagline` in EN/AR/DE/ES/FR.
- **Scan FAB** at bottom-left (left:20, bottom:124).

## Phase 1 – IAP foundation (this iteration)
- New `/app/backend/iap/` package with skeletons: `common.py` (product map, models, scan-limit tiers), `effective_plan.py` (derives plan from `subscriptions`), `apple.py` and `google.py` (NotImplementedError skeletons — real integration in Phase 2/3), `routes.py` (all IAP routes return 501 in Phase 1).
- New collections: `subscriptions` and `iap_events` with partial-unique indexes on Apple `original_transaction_id` and Google `purchase_token` to prevent transaction reuse.
- New endpoint `GET /api/entitlement` — canonical derived entitlement snapshot with expiry / grace / auto-renew / manage_url.
- New stub endpoints (501): `POST /api/iap/apple/verify`, `POST /api/iap/google/verify`, `POST /api/iap/restore`, `POST /api/iap/apple/webhook`, `POST /api/iap/google/webhook`.
- Migration `001_reset_dev_plans` — resets every user's cached plan to `free` since no verified store subscriptions exist yet.

## Testing accounts
See `/app/memory/test_credentials.md`.

## Turn A — AdMob SSV & Granular Scan Limits (this iteration)
- **Bundle ID unified** — iOS + Android → `com.ayhamabdullah.c1` (user-owned).
- **Product map** (real IDs, USD base prices — store returns localized prices):
  - Apple: `com.ayhamabdullah.c1.premium.monthly` ($1.99/mo),
           `com.ayhamabdullah.c1.plus.monthly` ($4.99/mo),
           `com.ayhamabdullah.c1.plus.annual` ($34.99/yr)
  - Google: `c1_premium/monthly`, `c1_plus/monthly`, `c1_plus/annual`
- **Scan limits** — split into BASE + REWARDED buckets (24h rolling):
  - Free:    3 base + 2 rewarded  = 5 max/day (ads unlock rewarded)
  - Premium: 20 base + 3 rewarded = 23 max/day
  - Plus:    99 total (no ads), hard fair-use cap
- **`GET /api/scan-quota`** returns full breakdown: `base_limit`, `base_used`, `base_remaining`, `rewarded_limit`, `rewarded_used`, `rewarded_remaining`, `rewarded_credits_available`, `total_used`, `total_remaining`, `can_watch_ad`, `fair_use_limit`, `blocked`, `reset_at` (legacy `limit`, `used`, `remaining` kept for compat).
- **`POST /api/ai/scan-meal`** — consumes BASE first. When base exhausted, consumes one unconsumed rewarded credit via atomic `find_one_and_update`. Returns `429 base_limit_reached` if base gone and no credits (client watches ad); `429 scan_limit_reached` if fully capped. Refunds credit on invalid image / AI failure.
- **`POST /api/ai/rewarded/token`** — JWT-auth. Issues a short-lived (`typ=c1_rw`, 20-min) signed token; client sets it as `customData` on the AdMob RewardedAd.
- **`GET/POST /api/ai/rewarded/redeem`** — Public AdMob SSV callback. Decodes `custom_data`, enforces per-plan rewarded cap, inserts idempotent credit keyed on `transaction_id`. Signature verification bypassed unless `ADMOB_SSV_ENFORCE=true` (full ECDSA in Turn B).
- **AdMob IDs** stored in `app.json extra.admob` — Android App ID `ca-app-pub-3656632924764645~6219258098`, Rewarded `ca-app-pub-3656632924764645/2694232041`, Interstitial `ca-app-pub-365663292476645/7939533877` (used exactly as provided by user). iOS AdMob App ID **PENDING** until user creates iOS app in AdMob console.
- **i18n** — new keys across EN/AR/DE/ES/FR for limit dialogs, watch-ad CTA, scan-count labels, plan names, reset-in-time.
- **DB indexes** — new `rewarded_credits` collection with unique index on `transaction_id`, plus lookup indexes.

## Turn C — Google Play Billing (real purchase flow)
- **Frontend** — Installed `react-native-iap@16.2.4` + `react-native-nitro-modules` (peer dep). New module `src/google-billing.ts` (native) + `src/google-billing.web.ts` (Metro-safe web stub) exports `billingAvailable`, `initBilling`, `fetchSubscriptions`, `requestSubscriptionPurchase`, and `IAP_PRODUCTS`.
- **Paywall** — `activate()` no longer shows "Coming soon"; it now (a) maps the selected plan to a `{sku, basePlanId}`, (b) checks `billingAvailable()` and — when the SDK isn't loaded (Expo Go, web, iOS) — shows a specific alert with the exact Play Console steps to configure, (c) calls `requestSubscriptionPurchase` which launches the Google Play sheet, (d) on success posts to `/api/iap/google/verify` and refreshes user auth.
- **Backend** — `iap/google.py` now performs real `subscriptionsv2.get` calls against the Google Play Developer API with service-account OAuth (androidpublisher scope). Verifies package name + productId match, requires `subscriptionState ∈ {ACTIVE, IN_GRACE_PERIOD}`, extracts `expiryTime` from `lineItems[]`, upserts the `subscriptions` doc keyed on `purchase_token`, best-effort acknowledges the purchase, refreshes cached plan, and returns `{ok, plan, period, entitlement}`. Requires env `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` (JSON string or file path); when absent, the endpoint returns HTTP 503 `play_api_not_configured` with an actionable message.
- **Auth refactor** — Extracted `get_current_user` to `/app/backend/deps.py` so `iap/routes.py` can depend on it without a circular import. `app.state.db` is set at startup.
- **RTDN webhook** — `/iap/google/webhook` still returns 501; wiring lands in the next follow-up (Pub/Sub push, JWT verify, messageId dedupe, snapshot reconcile).

### What the operator (user) must do BEFORE purchases can be tested
1. **Google Play Console → Monetize → Subscriptions** — create these products in the app `com.ayhamabdullah.c1`:
   - `c1_premium` — base plan id `monthly`, price €1.99 / month, auto-renewing
   - `c1_plus` — two base plans: `monthly` (€4.99/mo) and `annual` (€54.99/yr), both auto-renewing
   - Activate each base plan. Do NOT rename or reuse product IDs after creation.
2. **Publish a build to Internal Testing track** with package `com.ayhamabdullah.c1` (the currently deployed AAB). Products are not purchasable until the app has at least one published track.
3. **Google Cloud Console** — create a service account, enable the Google Play Android Developer API, download the JSON key. In Play Console → Users and permissions, invite the service-account email and grant the "View financial data, orders, and cancellation survey responses" + "Manage orders and subscriptions" permissions.
4. **Backend env** — add `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON=<JSON string OR path to file>` to `/app/backend/.env` and restart the backend.
5. **License testers** — Play Console → Settings → License testing → add tester Gmail accounts and opt them into the internal track. Testers can then purchase with test payment instruments.
6. **(Later) RTDN** — enable Pub/Sub topic `play-rtdn`, grant `google-play-developer-notifications@system.gserviceaccount.com` Publisher, create a push subscription pointing at `/api/iap/google/webhook`.


