//
//  PremiumService.swift
//
//  Single source of truth for the user's premium/subscription state.
//
//  ── How to adapt this template ──────────────────────────────────────────
//  1. Set `entitlementId` to your RevenueCat entitlement identifier. It must
//     match the RC Dashboard EXACTLY, same case, same spaces. A mismatch is
//     the most common "I paid but I'm not premium" bug.
//  2. Replace the example gate methods (`canStartSolo`, `canUseRooms`, …) in
//     the "Free-tier gates" section with the real features of this app.
//  3. Wire or remove the `AnalyticsService.*` calls.
//  4. Configure the SDK once at app launch (see step 2 of SKILL.md):
//         Purchases.logLevel = PremiumService.isDebugBuild ? .debug : .error
//         Purchases.configure(withAPIKey: "appl_YOUR_KEY")
//
//  Design rule: NOTHING outside this file should import RevenueCat or read
//  `customerInfo`. Gates everywhere else are just `premium.isPremium` (plus
//  free-allowance logic that also lives here). One file to reason about, one
//  file to log, one file to debug.
//

import Foundation
import RevenueCat
import RevenueCatUI
import SwiftUI
import UIKit

@MainActor
final class PremiumService: ObservableObject {

    static let shared = PremiumService()

    /// The only entitlement signal the rest of the app should read.
    @Published var isPremium = false

    /// RevenueCat entitlement identifier. MUST match the dashboard exactly.
    private static let entitlementId = "premium"

    /// Reference to a currently-presented paywall, used to prevent stacking
    /// and to dismiss it imperatively after a purchase.
    private weak var presentedPaywallVC: UIViewController?

    private static let devOverrideKey = "premium.devOverride"
    private static let devOverrideInitializedKey = "premium.devOverrideInitialized"

    /// True only for local Debug builds. TestFlight and App Store both count
    /// as production, the dev override below is inert in both.
    static let isDebugBuild: Bool = {
        #if DEBUG
        return true
        #else
        return false
        #endif
    }()

    /// Mock-premium toggle for the simulator. Lets you exercise premium gates
    /// without a sandbox purchase. Persisted across launches, but ignored
    /// entirely outside Debug builds so it can never grant a free Pro tier to
    /// real users.
    @Published var devOverride: Bool {
        didSet {
            UserDefaults.standard.set(devOverride, forKey: Self.devOverrideKey)
            if Self.isDebugBuild { isPremium = devOverride }
        }
    }

    private init() {
        let defaults = UserDefaults.standard
        if !defaults.bool(forKey: Self.devOverrideInitializedKey) {
            defaults.set(true, forKey: Self.devOverrideInitializedKey)
            defaults.set(Self.isDebugBuild, forKey: Self.devOverrideKey)
        }
        self.devOverride = defaults.bool(forKey: Self.devOverrideKey)
        if Self.isDebugBuild { self.isPremium = self.devOverride }
    }

    // MARK: - Free-tier gates
    //
    // EXAMPLE gates, replace with this app's real features. The point of
    // putting allowance logic here is that the rules live in one place and
    // read clearly at the call site: `if premium.canUseRooms { … }`.

    static let freeWarmupAllowance = 3

    /// Example: a feature with a per-user free allowance.
    func canStartSolo(completedCount: Int) -> Bool {
        if isPremium { return true }
        return completedCount < Self.freeWarmupAllowance
    }

    /// Example: a fully paid feature.
    var canUseRooms: Bool { isPremium }

    // MARK: - Status

    /// Refreshes `isPremium` from RevenueCat. Call on app launch and on
    /// foreground so subscription changes made elsewhere are picked up.
    func checkPremiumStatus() async {
        if Self.isDebugBuild && devOverride {
            isPremium = true
            return
        }
        do {
            let customerInfo = try await Purchases.shared.customerInfo()
            Self.dumpCustomerInfo(customerInfo, label: "checkPremiumStatus")
            let wasPremium = isPremium
            let nowPremium = customerInfo.entitlements[Self.entitlementId]?.isActive == true
            isPremium = nowPremium
            if !wasPremium && nowPremium {
                AnalyticsService.subscriptionActive()   // adapt or remove
            }
        } catch {
            print("[RC] ❌ checkPremiumStatus failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Identity

    /// Links the RevenueCat session to your auth user's stable ID. Call right
    /// after sign-in (and on launch when a session is restored).
    ///
    /// Without this, purchases stay on an anonymous RC ID: they won't follow
    /// the user to a new device, and the webhook can't tell which DB row an
    /// event belongs to (the app user ID is the only identifier it receives).
    func identify(userId: String) async {
        do {
            let (customerInfo, _) = try await Purchases.shared.logIn(userId)
            Self.dumpCustomerInfo(customerInfo, label: "identify")
            isPremium = customerInfo.entitlements[Self.entitlementId]?.isActive == true
        } catch {
            print("[RC] ❌ identify failed for \(userId): \(error.localizedDescription)")
        }
    }

    /// Reverts RevenueCat to an anonymous identity. Call on sign-out.
    func unidentify() async {
        do {
            _ = try await Purchases.shared.logOut()
        } catch {
            // logOut throws if already anonymous, safe to ignore.
            print("[RC] logOut: \(error.localizedDescription)")
        }
    }

    // MARK: - Paywall

    /// Presents the RevenueCatUI paywall imperatively via UIKit on the
    /// top-most view controller.
    ///
    /// We deliberately do NOT bind a `@Published` flag to a SwiftUI
    /// `.sheet`/`.fullScreenCover`. Doing so attaches the cover at multiple
    /// levels of the view hierarchy at once; when the flag flips back to
    /// false, every copy dismisses and the dismissal propagates up through
    /// any presenting sheet, collapsing the whole stack and sometimes
    /// re-triggering presentation. Imperative UIKit presentation sidesteps
    /// SwiftUI's presentation hierarchy entirely.
    func showPaywall(trigger: String) {
        AnalyticsService.paywallViewed(trigger: trigger)   // adapt or remove

        // Don't stack paywalls if one is already on screen.
        if let existing = presentedPaywallVC, existing.presentingViewController != nil {
            return
        }

        let paywall = PaywallView()
            .onRestoreCompleted { [weak self] customerInfo in
                guard let self else { return }
                self.isPremium = customerInfo.entitlements[Self.entitlementId]?.isActive == true
                if self.isPremium { self.dismissPaywall() }
            }
            .onPurchaseCompleted { [weak self] customerInfo in
                guard let self else { return }
                self.isPremium = customerInfo.entitlements[Self.entitlementId]?.isActive == true
                self.dismissPaywall()
            }

        let hosting = UIHostingController(rootView: paywall)
        hosting.modalPresentationStyle = .fullScreen

        guard let topVC = Self.topMostViewController() else {
            print("[RC] No top view controller to present paywall")
            return
        }
        presentedPaywallVC = hosting
        topVC.present(hosting, animated: true)
    }

    private func dismissPaywall() {
        presentedPaywallVC?.dismiss(animated: true)
        presentedPaywallVC = nil
    }

    private static func topMostViewController() -> UIViewController? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let scene = scenes.first(where: { $0.activationState == .foregroundActive }) ?? scenes.first
        var top = scene?.keyWindow?.rootViewController
            ?? scene?.windows.first(where: \.isKeyWindow)?.rootViewController
            ?? scene?.windows.first?.rootViewController
        while let presented = top?.presentedViewController { top = presented }
        return top
    }

    // MARK: - Restore

    /// App Review requires a visible "Restore Purchases" control. Wire a
    /// Settings button to this.
    func restorePurchases() async throws {
        let customerInfo = try await Purchases.shared.restorePurchases()
        Self.dumpCustomerInfo(customerInfo, label: "restorePurchases")
        isPremium = customerInfo.entitlements[Self.entitlementId]?.isActive == true
    }

    // MARK: - Diagnostics

    /// Prints which user the SDK is authenticated as and every entitlement
    /// key it sees, which exist, which are active, expirations, products.
    /// When an entitlement mismatch happens, this log is the fastest path to
    /// the answer. Call after any `customerInfo` fetch.
    private static func dumpCustomerInfo(_ info: CustomerInfo, label: String) {
        let allKeys = info.entitlements.all.keys.sorted()
        let activeKeys = info.entitlements.active.keys.sorted()
        print("[RC][\(label)] currentAppUserId=\(Purchases.shared.appUserID)")
        print("[RC][\(label)] all entitlements (\(allKeys.count)): \(allKeys)")
        print("[RC][\(label)] active entitlements (\(activeKeys.count)): \(activeKeys)")
        for (key, ent) in info.entitlements.all {
            print("[RC][\(label)]   • \"\(key)\" isActive=\(ent.isActive) willRenew=\(ent.willRenew) productId=\(ent.productIdentifier) expires=\(String(describing: ent.expirationDate))")
        }
    }
}
