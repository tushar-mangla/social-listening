# Plan: Notion CRM Sync

## 1. Goal

Implement a robust system to automatically save qualified leads, identified by the social listening loop, directly into the "RecruitmentOS Leads CRM" Notion database. This will streamline the lead management process by creating a centralized and structured repository of potential clients.

## 2. Assumptions

- The Notion REST API is available and its endpoint (`https://api.notion.com/v1/pages`) is accessible from the application's deployment environment.
- A valid `NOTION_API_KEY` with permissions to create pages in the target database will be provided via environment variables.
- The schema of the target Notion database (`c465f467-5f37-4be4-8308-b0527202b5fb`) is stable and matches the provided specification.
- The data structure of a "qualified lead" from the listening loop is well-defined and contains the necessary fields for the Notion database.

## 3. User Journeys

**Journey 1: Developer Setup**
1. A developer clones the repository.
2. They create a `.env` file based on `.env.example`.
3. They populate `NOTION_API_KEY` and optionally `NOTION_DATABASE_ID` in the `.env` file.
4. They install the required dependencies, including the new `notion-client`.
5. The application is now configured to sync with Notion.

**Journey 2: Automated Lead Syncing**
1. The social listening application is running.
2. It identifies a new, qualified lead from a social media post.
3. The application internally transforms the lead data into the format required by the Notion API.
4. It calls the Notion API to create a new page in the "RecruitmentOS Leads CRM" database.
5. The application logs a success message. If the API call fails, it logs a detailed error but continues its listening loop without crashing.

**Journey 3: Recruiter/Salesperson Workflow**
1. A recruiter opens the "RecruitmentOS Leads CRM" database in Notion.
2. They see a new entry (a new page) for the lead that was just processed.
3. They can view all the details of the lead, such as "Lead Name," "Company," "Post URL," and the generated "Cold Outreach Draft," all correctly populated in the respective properties.
4. They can then update the "Status" of the lead and begin their outreach process directly from Notion.

## 4. Acceptance Criteria

- **AC1:** When a qualified lead is detected, a new page is successfully created in the Notion database with ID `c465f467-5f37-4be4-8308-b0527202b5fb`.
- **AC2:** All lead data fields (`Lead Name`, `Company`, `Summary`, etc.) are correctly mapped and populated into their corresponding properties in the Notion page.
- **AC3:** Rich text properties (`Summary`, `Cold Outreach Draft`) longer than 2000 characters are truncated to 2000 characters before being sent to the Notion API.
- **AC4:** The application correctly loads `NOTION_API_KEY` and `NOTION_DATABASE_ID` from environment variables. If `NOTION_DATABASE_ID` is not set, it defaults to `c465f4675f374be48308b0527202b5fb`.
- **AC5:** The application includes graceful error handling for Notion API interactions. Network errors (e.g., timeouts) or API errors (e.g., 401 Unauthorized, 400 Bad Request) are logged, and the main listening loop continues to run.
- **AC6:** A comprehensive test suite for the Notion sync module exists, with unit tests for payload construction and mocked API interactions for both success and error scenarios.

## 5. Affected Components/Files

- **`listening-loop/notion_sync.py`** (New File): A dedicated module to encapsulate all logic for interacting with the Notion API. This includes payload construction, API calls, and error handling.
- **`listening-loop/test_notion_sync.py`** (New File): A new test suite containing unit tests for the `notion_sync.py` module.
- **`listening-loop/config.py`**: To be updated to load `NOTION_API_KEY` and `NOTION_DATABASE_ID` from environment variables using `python-dotenv`.
- **`listening-loop/digest.py`** (or main loop file): To be updated to import and call the new Notion sync function when a qualified lead is processed.
- **`requirements.txt`**: To be updated to add `notion-client` (or `requests`) and `python-dotenv`.
- **`.env.example`**: To be updated with `NOTION_API_KEY` and `NOTION_DATABASE_ID` placeholders.

## 6. Frontend/API/Database Contract

### Notion API Contract

- **Endpoint:** `POST https://api.notion.com/v1/pages`
- **Headers:**
  - `Authorization`: `Bearer <NOTION_API_KEY>`
  - `Content-Type`: `application/json`
  - `Notion-Version`: `2022-06-28`
- **Request Body (Payload):**
  A JSON object representing the new page. The `parent` will be the database ID, and the `properties` object will contain the lead data mapped to Notion's specific property object formats.

  *Example Payload Snippet:*
  ```json
  {
    "parent": { "database_id": "c465f467-5f37-4be4-8308-b0527202b5fb" },
    "properties": {
      "Lead Name": {
        "title": [{ "text": { "content": "John Doe" } }]
      },
      "Company": {
        "rich_text": [{ "text": { "content": "Acme Corp" } }]
      },
      "Post URL": {
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:12345/"
      },
      "Score": {
        "number": 85
      },
      "Intent Type": {
        "select": { "name": "Hiring_Surge" }
      },
      "Urgency": {
        "select": { "name": "High" }
      },
      "Status": {
        "status": { "name": "Not started" }
      }
    }
  }
  ```

## 7. Schema or Migration Approach

No database schema migration is required. The application will conform to the existing, predefined schema of the Notion "RecruitmentOS Leads CRM" database.

## 8. Implementation Sequence

1.  **Setup & Configuration:**
    - Create a new feature branch (e.g., `feature/notion-crm-sync`).
    - Add `notion-client` and `python-dotenv` to `requirements.txt`.
    - Update `listening-loop/config.py` to load `NOTION_API_KEY` and `NOTION_DATABASE_ID` from a `.env` file. Provide the specified default for the database ID.
    - Update `.env.example`.

2.  **Develop Notion Sync Module:**
    - Create `listening-loop/notion_sync.py`.
    - Implement a function `save_lead_to_notion(lead_data: dict)`.
    - Inside this function, write the logic to transform the input `lead_data` dictionary into the structured Notion API payload.
    - Ensure each property type is handled correctly (e.g., `title`, `rich_text`, `url`, `number`, `select`, `status`).
    - Implement the 2000-character truncation for `rich_text` fields.
    - Use the `notion-client` library to make the API call to create the page.
    - Wrap the API call in a `try...except` block to catch and log potential `APIResponseError` from the client, as well as network exceptions like `requests.exceptions.Timeout`.

3.  **Develop Test Suite:**
    - Create `listening-loop/test_notion_sync.py`.
    - Write a test case to verify that the payload is constructed correctly for a sample lead object.
    - Using `unittest.mock`, patch the `notion-client`'s `pages.create` method.
    - Write a test for a successful API call (mock returns a 200 OK response).
    - Write tests for failed API calls (mock raises `APIResponseError` with status codes 400, 401, and 500) and assert that the errors are handled gracefully.

4.  **Integration:**
    - In `listening-loop/digest.py` (or the main application file), import `save_lead_to_notion`.
    - At the point where a qualified lead is ready to be saved, call the function with the lead data.

5.  **Review and Merge:**
    - Run all tests and linting to ensure code quality.
    - Create a pull request, detailing the changes and linking to this plan.
    - After approval, merge into the main branch.

## 9. Test Plan

- **Unit Testing:**
  - **Payload Construction:** Verify that the function in `notion_sync.py` correctly converts a lead dictionary into the complex nested JSON structure required by Notion. Test all property types.
  - **API Mocking (Success):** Mock a successful `200 OK` response from the Notion API and ensure the function completes without raising exceptions.
  - **API Mocking (Failure):** Mock failure responses (`400`, `401`, `503`) and verify that the function catches these errors, logs them, and does not crash.
  - **Edge Cases:** Test the text truncation logic to ensure it activates only when necessary and truncates to the correct length.

- **Integration Testing:**
  - A temporary, separate Notion database will be created for testing purposes.
  - The application will be run locally with credentials for the test database.
  - A sample lead will be processed to confirm that it appears correctly in the test Notion database.

## 10. Risks

- **Notion API Rate Limiting:** If the application generates leads at a very high rate, it may exceed the Notion API's rate limit (average of 3 requests per second).
  - **Mitigation:** The current expected volume is low. If volume increases, implement a queueing system with exponential backoff for retries on rate limit errors.
- **Schema Changes in Notion:** A user could manually alter the properties of the Notion database, causing the integration to fail.
  - **Mitigation:** The error handling will catch errors related to missing or mismatched properties. Clear logging will be implemented to make debugging these issues straightforward.
- **Sensitive Key Management:** The `NOTION_API_KEY` is a sensitive credential.
  - **Mitigation:** Strictly enforce the use of environment variables. The key will never be hardcoded in the source code.

## 11. Rollback Notes

- The feature can be disabled by commenting out the call to `save_lead_to_notion()` in the main application loop.
- For a full rollback, the feature branch can be reverted from the `main` branch. Since the changes are modular (contained in `notion_sync.py`), the risk of impacting other parts of the application is low.

## 12. Definition of Done

- All code for the feature is implemented on a feature branch.
- The unit test suite is implemented with sufficient coverage and all tests are passing.
- The feature has been successfully tested via integration testing against a real Notion database.
- The code has been reviewed, approved, and merged into the `main` branch.
- The `.env.example` and `requirements.txt` files are updated.
