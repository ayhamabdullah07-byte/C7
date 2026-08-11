#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  Turn A — Backend AdMob SSV & Scan Limits for C1 nutrition app (com.ayhamabdullah.c1).
  Required:
   - Split scan quota into base + rewarded buckets per plan
       Free:    3 base + 2 rewarded (5/day)
       Premium: 20 base + 3 rewarded (23/day)
       Plus:    99 total, no ads (fair-use cap)
   - Backend enforces limits authoritatively (24h rolling window)
   - New endpoint /api/ai/rewarded/token issues short-lived JWT for AdMob customData
   - New endpoint /api/ai/rewarded/redeem receives AdMob SSV callback,
     dedupes on transaction_id, enforces per-plan rewarded cap, inserts credit
   - /api/ai/scan-meal consumes base first, then one rewarded credit if base exhausted
   - Refund credit on invalid image / AI failure
   - Update bundle IDs to com.ayhamabdullah.c1
   - Update product map: Premium Monthly, Plus Monthly, Plus Annual
   - Add i18n keys for limit dialogs across 5 languages (EN/AR/DE/ES/FR)
   - AdMob IDs used EXACTLY as provided (Interstitial has an apparent typo — do not correct)

backend:
  - task: "AdMob SSV endpoints + rewarded credit flow"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: |
          Implemented /api/ai/rewarded/token (JWT auth, issues c1_rw typed token)
          and /api/ai/rewarded/redeem (GET/POST, public, decodes custom_data,
          enforces per-plan rewarded cap, idempotent on transaction_id).
          Full ECDSA signature verify gated behind ADMOB_SSV_ENFORCE env
          (default off in dev; ADMOB signature keys wiring deferred to Turn B).
          11 dedicated SSV tests pass locally.

  - task: "Base + Rewarded scan-limit split"
    implemented: true
    working: true
    file: "/app/backend/server.py, /app/backend/iap/common.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: |
          SCAN_LIMITS restructured: {base, rewarded, total_cap} per plan.
          Free 3+2, Premium 20+3, Plus 99 total (no ads). scan_logs
          gained a `kind` field (base|rewarded); rewarded_credits collection
          gates unlocks. /api/ai/scan-meal atomically consumes credit via
          find_one_and_update, refunds on failure. /api/scan-quota returns
          full breakdown + legacy fields for compat. 17 tests pass.

  - task: "IAP product map — com.ayhamabdullah.c1"
    implemented: true
    working: true
    file: "/app/backend/iap/common.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: |
          APPLE_PRODUCTS and GOOGLE_PRODUCTS remapped to bundle
          com.ayhamabdullah.c1 with SKUs: premium.monthly, plus.monthly,
          plus.annual. Google keys c1_premium/monthly, c1_plus/monthly,
          c1_plus/annual. Period type extended P1M | P1Y. 12 unit tests pass.

  - task: "DB indexes for rewarded_credits"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: |
          New indexes at startup: unique on transaction_id (partial),
          consume-lookup (user_id, consumed_at, granted_at),
          history (user_id, granted_at desc). Verified created on boot.

frontend:
  - task: "app.json bundle ID + AdMob config"
    implemented: true
    working: "NA"
    file: "/app/frontend/app.json"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          iOS bundleIdentifier + Android package set to com.ayhamabdullah.c1.
          Added SKAdNetworkItems (AdMob) and AD_ID permission on Android.
          AdMob IDs placed under expo.extra.admob EXACTLY as user provided
          (Interstitial ID kept with the missing digit per user request).
          iOS AdMob App ID marked PENDING_USER_TO_CREATE_IOS_ADMOB_APP.
          No RN AdMob SDK wired yet — that lands in Turn B.

  - task: "i18n keys for limit dialogs"
    implemented: true
    working: "NA"
    file: "/app/frontend/src/i18n.ts"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Added scanLimitTitle, scanLimitFreeMsg/PremiumMsg/PlusMsg,
          scanCapAllReachedMsg, watchAdEarnScan, watchingAd, adFailed,
          scansToday, baseScansLabel, rewardedScansLabel, upgradeForMore,
          resetsIn, planFree/Premium/Plus — all translated in EN/AR/DE/ES/FR.

metadata:
  created_by: "main_agent"
  version: "1.2"
  test_sequence: 7
  run_ui: false

test_plan:
  current_focus:
    - "AdMob SSV endpoints + rewarded credit flow"
    - "Base + Rewarded scan-limit split"
    - "IAP product map — com.ayhamabdullah.c1"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      Turn A complete. Backend fully implements the new limits (3+2 free /
      20+3 premium / 99 plus), AdMob SSV endpoints with idempotent credits,
      per-plan rewarded caps, and refund-on-failure. Bundle ID renamed
      com.ayhamabdullah.c1 everywhere (product map + app.json). i18n keys
      added across all 5 languages. 91 existing/new pytest tests pass
      (1 legacy fixture error in test_c1_api.py pre-existed Turn A).
      Please run comprehensive backend verification of:
        1. GET /api/scan-quota — response shape + Free/Premium/Plus limits
        2. POST /api/ai/scan-meal — enforces base vs rewarded split correctly
        3. POST /api/ai/rewarded/token — auth + JWT shape
        4. GET/POST /api/ai/rewarded/redeem — token validation, dedupe, per-plan cap
        5. Rewarded credit consumed only after base exhausted; not Plus
        6. Idempotency on repeated SSV transaction_id
        7. IAP product map resolves correctly

# ------------------------------------------------------------------------------
# Iteration 7 — Turn A independent backend verification (T1)
# ------------------------------------------------------------------------------
# Result: 101 passed / 1 pre-existing legacy fixture error (unrelated).
#
# Suites executed against EXPO_PUBLIC_BACKEND_URL:
#   - tests/test_iap_products.py            12/12 PASS
#   - tests/test_admob_ssv.py               11/11 PASS
#   - tests/test_plans_scans.py             17/17 PASS
#   - tests/test_turn_a_verification.py     10/10 PASS  (new, added by T1)
#   - Full backend regression               101 passed, 1 error
#
# The single error is test_c1_api.py::test_scan_meal_happy_path — missing
# `real_food_b64` fixture. Pre-existing per E1's note; NOT a Turn A regression.
#
# Turn A checklist:
#   1. Scan-quota shape (new + legacy fields) ..................... VERIFIED
#   2. Free plan 3-base + 2-rewarded 429 semantics ................ VERIFIED
#   3. POST /api/ai/rewarded/token JWT (typ=c1_rw, correct sub) ... VERIFIED
#   4. SSV redeem — all failure modes + idempotency ............... VERIFIED
#   5. End-to-end rewarded flow (exhaust→429→SSV→200) ............. VERIFIED
#   6. Premium 20+3 enforcement ................................... VERIFIED
#   7. Plus 99 cap, rewarded=0, SSV rejected ...................... VERIFIED
#   8. IAP product resolvers (Apple + Google + unknowns) .......... VERIFIED
#   9. Refund of rewarded credit on invalid image ................. VERIFIED
#  10. Existing regressions (auth/meals/dashboard/recommend/etc.) . VERIFIED
#
# Reports:
#   /app/test_reports/pytest/pytest_iteration7.xml
#   /app/test_reports/pytest/pytest_turn_a_verification.xml
#   /app/test_reports/pytest/pytest_full_iteration7.xml
#   /app/test_reports/iteration_7.json
#
# No blocking issues found. Turn A ready to hand off to Turn B (frontend AdMob SDK).

      Do NOT test Turn B frontend AdMob SDK — that comes next.
# ============================================================================
# Turn B (main agent, iteration 8) — Frontend LimitDialog + AdMob SDK + Paywall
# ============================================================================
#
# USER-REPORTED BUG (Turn A follow-up):
#   Free user hits 3-scan limit → dialog appears but shows only a retry arrow;
#   NO "Watch Ad" or "View Subscription Plans" buttons rendered.
#
# ROOT CAUSE:
#   /app/frontend/app/scan.tsx caught the 429 as a plain error string and rendered
#   the generic s.errorCard which contained ONLY a "Try again" retry button.
#   The backend's detail (with `can_watch_ad`, `base_limit_reached`, plan, reset)
#   was discarded. There was no LimitDialog component at all.
#
# CHANGES:
#   1. yarn expo install react-native-google-mobile-ads@16.4.0 + plugin config
#      in app.json (androidAppId=real, iosAppId=Google test until user creates one).
#   2. NEW /app/frontend/src/ads.ts + ads.web.ts — SDK wrapper with graceful
#      Expo Go / web fallback (adsAvailable(), showRewardedAd, showInterstitialAd).
#      Prevents Metro from crashing on native-only components.
#   3. NEW /app/frontend/src/limit-dialog.tsx — full-screen Modal with:
#        • Plan-specific localized title + body (EN/AR/DE/ES/FR)
#        • Reset countdown pill
#        • VISIBLE "Watch Ad — earn 1 scan" (Pressable, testID limit-watch-ad)
#        • VISIBLE "Upgrade for more" (Pressable, testID limit-view-plans, hidden for Plus)
#        • Close ghost button
#        • Preview-build hint when SDK unavailable
#        • Handles: watching state, ad-failed error, dev SSV fallback
#   4. REFACTORED scan.tsx — single Fragment return renders LimitDialog on top.
#      429 detail populates LimitDialogState. onSubscribe → router.push('/paywall').
#      onRewardGranted → auto-retry analyze(photoUri).
#   5. UPDATED paywall.tsx — 4 tiers:
#        Free — €0, features list updated (3+2 scans)
#        Premium — €1.99/mo (20+3)
#        Plus — €4.99/mo (MOST POPULAR, 99 scans, zero ads)
#        Plus Annual — €54.99/year (BEST VALUE — save ~8%)
#   6. api.rewardedToken + api.rewardedRedeemDev added in src/api.ts.
#
# VERIFICATION (web preview, real backend):
#   • Seeded a fresh Free user with 3 base scans, attempted 4th scan via gallery.
#   • Backend returned 429 base_limit_reached, can_watch_ad=true.
#   • LimitDialog rendered with title "Daily scan limit reached", body
#     "You've used all 3 free scans today. Watch a short ad to earn 1 more,
#     or upgrade for higher limits.", countdown pill "Resets in 23h 55m",
#     and 3 fully-clickable buttons (Watch Ad, Upgrade for more, Close).
#   • Clicked Watch Ad → SDK reported unavailable → dev SSV fallback called
#     /api/ai/rewarded/token + /api/ai/rewarded/redeem → credit granted →
#     dialog closed → scan retried → AI returned "No food detected" (correct
#     behavior for the 1x1 test JPEG).
#   • Post-flow quota: base_used=3, rewarded_used=1, rewarded_remaining=1,
#     rewarded_credits_available=0, can_watch_ad=true.
#   • Clicked Upgrade for more → navigated to /paywall showing all 4 tiers
#     with correct pricing (€0, €1.99/mo, €4.99/mo, €54.99/yr) and the
#     current-user badge on Free.
#
# NATIVE-BUILD REQUIREMENTS (unchanged from Turn A note):
#   • Real AdMob ad rendering requires a native/production build. In Expo Go
#     and web preview the SDK returns { status: 'sdk_unavailable' } and the
#     LimitDialog uses the dev SSV path so end-to-end flow remains testable.
#   • iOS AdMob App ID still Google's test ID — swap when user creates their
#     iOS AdMob app in the console.
#   • ADMOB_SSV_ENFORCE stays false in dev; full ECDSA signature verification
#     lands before production launch.
#
# No blocking issues. Ready for user acceptance testing.
