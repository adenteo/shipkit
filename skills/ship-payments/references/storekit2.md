# StoreKit 2 without a third party

Good for one or two products, or when the user does not want another service.
You give up RevenueCat's remote paywall, cross-platform state and dashboards.

## The Store

```swift
import StoreKit

@MainActor
final class Store: ObservableObject {
    static let shared = Store()
    static let productIDs = ["com.example.app.pro.yearly", "com.example.app.pro.monthly"]

    @Published private(set) var products: [Product] = []
    @Published private(set) var isPremium = false
    private var updates: Task<Void, Never>?

    init() {
        updates = Task { [weak self] in
            for await result in Transaction.updates {
                if case .verified(let t) = result { await t.finish() }
                await self?.refresh()
            }
        }
        Task { await load(); await refresh() }
    }

    func load() async {
        products = (try? await Product.products(for: Self.productIDs))?
            .sorted { $0.price > $1.price } ?? []   // yearly first
    }

    func buy(_ product: Product) async throws -> Bool {
        let result = try await product.purchase()
        guard case .success(let verification) = result,
              case .verified(let t) = verification else { return false }
        await t.finish()
        await refresh()
        return true
    }

    func restore() async {
        try? await AppStore.sync()
        await refresh()
    }

    func refresh() async {
        var active = false
        for await result in Transaction.currentEntitlements {
            if case .verified(let t) = result, t.revocationDate == nil,
               Self.productIDs.contains(t.productID) { active = true }
        }
        isPremium = active
    }
}
```

Every gate reads `Store.shared.isPremium`. Nothing else calls StoreKit.

## Paywall

- Subscriptions: `SubscriptionStoreView(productIDs: Store.productIDs)` gives an
  Apple-built paywall that already shows price, period and renewal terms. Add
  `.subscriptionStorePolicyDestination` for Terms and Privacy links, and
  `.storeButton(.visible, for: .restorePurchases)`.
- One-time unlock: a custom SwiftUI view with `product.displayPrice`, what it
  unlocks, Buy, Restore, Terms and Privacy links.

## Testing

Add a StoreKit configuration file (File, New, StoreKit Configuration File; choose
"synced" to pull products from App Store Connect, or define them locally) and set
it in the scheme's Run options. The simulator can then buy, refund and expire
subscriptions from Debug, StoreKit, Manage Transactions.
