# Common rejections and the usual fix

| Guideline | What the message says (roughly) | Usual fix |
|---|---|---|
| 2.1 Performance: App Completeness | Crash, bug, or something did not work during review | Reproduce on the same iOS version and device class named in the message; fix; new build; reply with what changed |
| 2.1 Information Needed | Reviewer could not find a feature or needs a demo account | Reply with exact steps, screenshots or a short screen recording; no new build |
| 2.3.3 Accurate Metadata | Screenshots do not show the app in use, or show device frames incorrectly | Re-render screenshots from real screens; metadata-only resubmit |
| 2.3.10 | Mentions other platforms or irrelevant info in metadata | Remove the mention from description, screenshots, what's new |
| 3.1.1 In-App Purchase | Digital content unlocked another way, or link to external purchase | Route through in-app purchase; remove external purchase prompts |
| 3.1.2 Subscriptions | Missing renewal terms, price, or Terms/Privacy links on the paywall or in metadata | Add them next to the buy button and to the description; often a new build |
| 4.0 Design | Interface hard to use, cut-off text, iPad layout broken | Fix layout on the device named; test smallest iPhone and iPad |
| 4.2 Minimum Functionality | App is too simple or a web view wrapper | Add native value; explain in notes what the app does that the web cannot |
| 4.3 Spam | Similar to many apps, or to the developer's own other app | Explain originality in detail in a reply; if it really is a template, change it substantially |
| 4.8 Login Services | Third-party login without Sign in with Apple | Add Sign in with Apple with equal prominence |
| 5.1.1(i) Privacy Policy | Policy missing, broken, or does not cover data the app collects | Fix the page; update App Privacy answers to match |
| 5.1.1(iv) Permissions | Purpose string vague, or permission required to use the app | Specific purpose strings; let the user continue without it |
| 5.1.1(v) Account Deletion | No way to delete an account in the app | Add an in-app delete account flow that deletes the data |
| 5.1.2 Data Use and Sharing | Tracking without ATT, or App Privacy says tracking but no prompt | Add the ATT prompt before tracking, or stop tracking and fix the answers |
| Missing IAP | In-app purchase products not submitted with the version | Attach the products on the version page and resubmit |

Reply template:

> Hello, thank you for the review. [One sentence on what we changed, or where to find
> the feature.] [Exact steps: Open the app, tap X, then Y.] [Attached: screenshot or
> recording.] Please let us know if anything else is needed.
