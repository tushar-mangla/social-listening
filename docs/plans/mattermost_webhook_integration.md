
# Plan: Mattermost Webhook Integration for Social Listening Loop

## 1. Goal

The goal of this project is to integrate Mattermost webhook notifications into the RecruitmentOS Social Listening loop. This will enable real-time alerting for new, qualified recruitment leads, sending a richly formatted message to a specified Mattermost channel.

## 2. Assumptions

- The user has a valid Mattermost webhook URL.
- The Mattermost instance can receive incoming webhooks from the environment where the script is running.
- The `requests` library is the standard for making HTTP calls in this project.
- The core logic for lead identification and scoring in `digest.py` is stable and provides the necessary data points for the alert payload.
- A basic implementation of `send_mattermost_alert` already exists in `digest.py` and can be refactored and enhanced.

## 3. User Journeys

**As a Recruiter/Salesperson:**
1. I have set up the `MATTERMOST_WEBHOOK_URL` in my environment.
2. The social listening loop runs and identifies a new, qualified lead.
3. Within moments, a new message appears in our designated Mattermost channel.
4. The message is clearly formatted with a header, the company's name, an urgency badge, the detected intent, a link to the original post, a 1-click LinkedIn search link for decision-makers, and a pre-drafted InMail message.
5. I can quickly assess the lead's quality and take immediate action.
6. If the webhook URL is missing or invalid, the listening loop does not crash and logs a warning.

## 4. Acceptance Criteria

- **Configuration:** The `MATTERMOST_WEBHOOK_URL` must be configurable via an environment variable or a `.env` file, loaded in `config.py`.
- **Notification Trigger:** A Mattermost notification is sent for every qualified lead processed by `digest.py`.
- **Payload Content:** The Mattermost message must contain:
    - A clear header (e.g., "New Recruitment Lead").
    - Company Name.
    - Urgency Badge (e.g., 🔴 High, 🟡 Medium, 🟢 Low).
    - Detected Intent (e.g., "Agency Seeking", "Hiring Pain").
    - A direct link to the source post.
    - A dynamically generated LinkedIn boolean search URL for finding decision-makers.
    - A pre-drafted cold InMail/DM template.
- **Formatting:** The message must be well-formatted using Mattermost-compatible Markdown (e.g., tables, bolding, links).
- **Error Handling:** The application must handle failures (e.g., invalid URL, network issues, timeouts) gracefully by logging an error and continuing execution without crashing.
- **Modularity:** The Mattermost notification logic should be encapsulated in its own module.
- **Documentation:** The `.env.example` file must be updated to include `MATTERMOST_WEBHOOK_URL`.

## 5. Affected Components/Files

- **`listening-loop/digest.py`**: Will be modified to import the new notifier module and call it. The existing `send_mattermost_alert` function will be removed.
- **`listening-loop/notifier.py`** (New File): Will be created to house the Mattermost notification logic, including payload formatting and the webhook sending function.
- **`listening-loop/.env.example`**: Will be updated to include the `MATTERMOST_WEBHOOK_URL` variable.
- **`listening-loop/config.py`**: No changes needed, as it already loads the `MATTERMOST_WEBHOOK_URL` variable.
- **`docs/plans/mattermost_webhook_integration.md`**: This plan.

## 6. Frontend/API/Database Contract

This is a backend integration. The contract is with the Mattermost Incoming Webhook API.

**Mattermost Webhook Payload (JSON):**
```json
{
  "username": "RecruitmentOS Lead Bot",
  "icon_url": "https://raw.githubusercontent.com/tandpfun/skill-icons/main/icons/Rocket.svg",
  "text": "Markdown-formatted message string"
}
```

**Markdown `text` field structure:**
```markdown
### 🔥 **NEW RECRUITMENT LEAD** 🔥
| Field | Detail |
| :--- | :--- |
| **Urgency** | 🔴 High |
| **Company** | Innovate Inc. |
| **Author** | SalesLeader123 (Director of Sales) |
| **Intent** | Agency_Seeking |
| **Summary** | The author... is actively looking for solutions. |
| **Source** | [View Original Post](https://example.com/post) |
| **LinkedIn** | [1-Click Decision-Maker Search](https://linkedin.com/search/...) |

**Cold Outreach Draft:**
> "Hi [Name], saw your post about hiring challenges at Innovate Inc. ..."
```

## 7. Schema or Migration Approach

Not applicable. No database schema changes are required.

## 8. Implementation Sequence

1.  **Create `listening-loop/notifier.py`**:
    - Create a new file named `notifier.py`.
    - Move the `send_mattermost_alert` function from `digest.py` into `notifier.py`.
    - Add necessary imports (`os`, `requests`, `sys`, `urllib.parse`, `config as C`).

2.  **Refactor and Enhance `notifier.py`**:
    - In `send_mattermost_alert`, add a mapping for urgency levels to emoji badges.
    - Update the payload formatting (`text_card`) to use the emoji badge and improve overall readability.
    - Enhance the `try...except` block to catch more specific `requests.exceptions` (e.g., `Timeout`, `ConnectionError`) and log detailed error messages to `sys.stderr`.

3.  **Update `listening-loop/digest.py`**:
    - Add `from notifier import send_mattermost_alert` at the top.
    - Remove the now-redundant `send_mattermost_alert` function definition from this file.
    - The existing call to `send_mattermost_alert(lead)` in the `main()` function will now correctly point to the imported function.

4.  **Update `listening-loop/.env.example`**:
    - Add a new section for the Mattermost webhook.
    - Add the line `MATTERMOST_WEBHOOK_URL=` with a comment explaining its purpose.

5.  **Verification**:
    - Create a temporary test script or add a `if __name__ == "__main__"` block to `notifier.py` for testing.
    - This test harness will:
        - Import `config` and sample data.
        - Call `send_mattermost_alert` with a sample lead object from `config.SAMPLE_POSTS`.
        - Allow developers to manually run `python listening-loop/notifier.py` to send a test alert to a real webhook URL for verification.

## 9. Test Plan

- **Unit Testing**:
    - A unit test will be created for the payload formatting logic within `send_mattermost_alert`.
    - It will assert that given a sample lead dictionary, the function produces the expected Markdown string, correctly formatting all fields and selecting the right urgency emoji.
- **Integration Testing**:
    - The test harness described in the implementation sequence will serve as the integration test.
    - A developer will provide a live Mattermost webhook URL in their local `.env` file.
    - Running the test script will post a message to the channel, verifying the connection, authentication, and message rendering.
- **Manual Testing**:
    - Run the full `digest.py --dry-run` script with a valid `MATTERMOST_WEBHOOK_URL` set.
    - Verify that a notification is sent for each of the sample posts and that they render correctly in Mattermost.

## 10. Risks

- **Network Instability**: The script runs in an environment that might have intermittent network issues. The enhanced error handling will mitigate this by preventing crashes.
- **Mattermost API Changes**: The incoming webhook API is stable, but future changes could break the integration. This is a low risk.
- **Incorrect Webhook URL**: An incorrect or revoked URL will cause failures. The logging will make this easy to diagnose.

## 11. Rollback Notes

- The changes are modular and well-contained.
- To roll back, revert the changes in `digest.py` by restoring the original `send_mattermost_alert` function.
- Delete the new `listening-loop/notifier.py` file.
- The changes are additive, so simply commenting out the `send_mattermost_alert(lead)` call in `digest.py` would effectively disable the feature without a full rollback.

## 12. Definition of Done

- The `send_mattermost_alert` function is moved from `digest.py` to a new `notifier.py` module.
- The function is enhanced with urgency badges and improved error handling.
- `digest.py` is updated to use the new module.
- `.env.example` is updated with `MATTERMOST_WEBHOOK_URL`.
- A developer can successfully run the digest and receive a correctly formatted Mattermost alert for each qualified lead.
- The listening loop continues to run without crashing if Mattermost notifications fail.
- The plan is approved and the implementation is merged.
