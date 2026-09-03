# Technical Plan: Convert Social Listening to RecruitmentOS Lead Engine

**Author:** OpenCode
**Date:** 2026-09-02
**Version:** 1.0

## 1. Goal

To transform the generic `social_listening/listening-loop` codebase into a specialized intelligence and lead generation engine for RecruitmentOS. The new engine will monitor Reddit and X (formerly Twitter) for conversations indicating hiring pain, buying intent for recruiting services/tools, and general recruitment trends. It will classify posts, score leads, and generate daily/weekly intelligence briefs tailored to the recruitment industry.

## 2. Assumptions

- The existing codebase has a functional loop for fetching data from sources (Reddit, X), processing it, and generating outputs.
- An LLM (Large Language Model) is integrated and used for data interpretation, likely within `digest.py` or `daily.py`.
- The `telegram.py` script is for sending notifications and will require minimal changes beyond adapting to new output formats.
- The environment is set up with necessary API keys for Reddit, X, and the LLM provider.

## 3. Affected Components & Files

- `listening-loop/config.py`: Will be heavily modified with recruitment-specific data sources, keywords, and scoring logic.
- `listening-loop/digest.py`: Core logic will be rewritten to classify, score, and qualify recruitment leads based on a new schema.
- `listening-loop/daily.py`: Will be adapted to generate a daily brief on recruitment-related posts and trends.
- `listening-loop/weekly.py`: Will be adapted to summarize weekly recruitment pain points and themes.
- `listening-loop/data/leads.csv`: The schema will be updated to reflect the new lead qualification criteria.
- A new file, `listening-loop/prompts.py`, will be created to house the detailed LLM prompts and JSON schema definitions for better maintainability.

## 4. Technical Contracts

### 4.1. LLM Intent & Classification Contract (`prompts.py`)

The LLM will be prompted to return a JSON object for each relevant post, adhering to the following schema. This ensures structured, predictable data for downstream processing.

**JSON Schema Definition:**
```json
{
  "is_lead": "boolean",
  "rejection_reason": "string (null if is_lead is true, otherwise explains why it's not a lead, e.g., 'Is a candidate looking for a job.')",
  "author_role": "enum('Founder', 'TA Manager', 'Hiring Manager', 'Agency Owner', 'Candidate', 'Other')",
  "intent": "enum('Buying Intent', 'Pain Point', 'Vendor Seeking', 'General Discussion', 'Other')",
  "urgency": "enum('High', 'Medium', 'Low')",
  "company_context": "string (Company name, industry, or other context if available, otherwise null)",
  "actionable_angle": "string (A brief, actionable sales or engagement angle for RecruitmentOS, e.g., 'Author is struggling with candidate ghosting; suggest our automated communication workflows.')",
  "summary": "string (A concise one-sentence summary of the post.)"
}
```

### 4.2. Database Contract (`data/leads.csv`)

The `leads.csv` file will be the primary output for qualified leads.

**CSV Schema:**
`timestamp,source,url,author,author_role,intent,urgency,score,company_context,summary,actionable_angle,original_text`

## 5. Implementation Sequence

This plan is designed to be executed sequentially by a coding agent.

### Step 1: Create `prompts.py` for Centralized Prompt Management

1.  **Action:** Create a new file named `listening-loop/prompts.py`.
2.  **Content:** Add the LLM JSON schema and the main classification prompt to this file.

    ```python
    # listening-loop/prompts.py

    LEAD_SCHEMA = {
      "is_lead": "boolean",
      "rejection_reason": "string (null if is_lead is true, otherwise explains why it's not a lead, e.g., 'Is a candidate looking for a job.')",
      "author_role": "enum('Founder', 'TA Manager', 'Hiring Manager', 'Agency Owner', 'Candidate', 'Other')",
      "intent": "enum('Buying Intent', 'Pain Point', 'Vendor Seeking', 'General Discussion', 'Other')",
      "urgency": "enum('High', 'Medium', 'Low')",
      "company_context": "string (Company name, industry, or other context if available, otherwise null)",
      "actionable_angle": "string (A brief, actionable sales or engagement angle for RecruitmentOS, e.g., 'Author is struggling with candidate ghosting; suggest our automated communication workflows.')",
      "summary": "string (A concise one-sentence summary of the post.)"
    }

    CLASSIFICATION_PROMPT = f"""
    You are a lead qualification expert for RecruitmentOS, a company that sells recruiting software and services.
    Your task is to analyze the following social media post and classify it according to the provided JSON schema.

    Your primary goal is to identify potential leads for RecruitmentOS. A lead is someone expressing pain with their current hiring process, actively looking for recruiting solutions, or a key decision-maker (Founder, Hiring Manager, Head of Talent) discussing recruitment challenges.

    **CRITICAL RULE:** You MUST strictly reject any post where the author is clearly a candidate or individual looking for a job. Do not classify them as a lead. Use the 'rejection_reason' field to explain why.

    Post Content:
    "{{post_text}}"

    Author Profile/Bio (if available):
    "{{author_bio}}"

    Analyze the post and return a single, valid JSON object matching this schema. Do not include any other text or explanations outside the JSON object.

    JSON Schema:
    {str(LEAD_SCHEMA)}
    """
    ```

### Step 2: Overhaul `config.py` for Recruitment Focus

1.  **Action:** Modify `listening-loop/config.py`.
2.  **Changes:**
    - Replace existing subreddit lists with recruitment-focused ones.
    - Replace existing X search queries.
    - Define a new keyword scoring matrix.
    - Add negative keywords to filter out job seekers.

    ```python
    # listening-loop/config.py

    # 1. Data Sources
    REDDIT_SOURCES = {
        "subreddits": [
            "recruiting",
            "humanresources",
            "talentacquisition",
            "recruitinghell", # Good for pain points
            "experienceddevs",
            "sysadmin",
            "sales"
        ]
    }

    X_SOURCES = {
        "queries": [
            # Pain/Frustration
            '"hiring is so hard" OR "struggling to hire" OR "candidate ghosting" OR "bad candidates"',
            # Buying/Seeking Intent
            '"recommend a good ATS" OR "recruiting agency recommendations" OR "best recruitment software"',
            # General Hiring Talk from relevant roles
            'from:hiringmanager ("we are hiring" OR "looking for" OR "join our team") -(job OR apply OR #job)',
            'from:founder ("we are hiring" OR "building our team") -(job OR apply OR #job)'
        ]
    }

    # 2. Lead Scoring Matrix
    # Base score is 0. Add points based on keywords found in the post.
    LEAD_SCORING = {
        "intent_keywords": {
            "ATS": 20,
            "CRM": 20,
            "sourcing tool": 25,
            "recruitment marketing": 15,
            "recommendation": 15,
            "help": 10
        },
        "pain_keywords": {
            "ghosting": 20,
            "can't find": 15,
            "struggling": 15,
            "too slow": 15,
            "bad fit": 10,
            "no-show": 20
        },
        "role_keywords": {
            "founder": 10,
            "hiring manager": 10,
            "head of talent": 15,
            "recruiter": 5
        }
    }

    # 3. Negative Keywords
    # If any of these are present, the post is likely not a lead.
    # This serves as a pre-filter before the LLM classification.
    NEGATIVE_KEYWORDS = [
        "looking for a job", "seeking new opportunities", "#opentowork",
        "my resume", "job application", "applying for", "cv", "portfolio"
    ]

    # 4. Lead Qualification Threshold
    MIN_LEAD_SCORE = 25
    ```

### Step 3: Refactor `digest.py` for Lead Generation

1.  **Action:** Modify `listening-loop/digest.py`.
2.  **Changes:**
    - Import the new prompt and schema from `prompts.py`.
    - Update the main processing loop to use the new LLM prompt.
    - Implement the lead scoring logic based on `config.py`.
    - Implement the lead qualification logic (score threshold and `is_lead` flag from LLM).
    - Write qualified leads to `leads.csv` using the new schema.

    ```python
    # listening-loop/digest.py (Conceptual Changes)
    import csv
    import json
    from config import LEAD_SCORING, MIN_LEAD_SCORE, NEGATIVE_KEYWORDS
    from prompts import CLASSIFICATION_PROMPT, LEAD_SCHEMA
    # ... other imports

    def score_post(text):
        score = 0
        text_lower = text.lower()
        for category, keywords in LEAD_SCORING.items():
            for keyword, points in keywords.items():
                if keyword in text_lower:
                    score += points
        return score

    def pre_filter(text):
        text_lower = text.lower()
        for keyword in NEGATIVE_KEYWORDS:
            if keyword in text_lower:
                return False # Fails pre-filter
        return True # Passes pre-filter

    def process_posts():
        # Load captured posts from capture.jsonl
        # ...

        qualified_leads = []
        for post in all_posts:
            if not pre_filter(post['text']):
                continue

            # 1. Call LLM for classification
            # prompt = CLASSIFICATION_PROMPT.format(post_text=post['text'], author_bio=post.get('author_bio', ''))
            # llm_response_json = call_llm(prompt) # Assume this function exists
            # classification = json.loads(llm_response_json)

            # For testing, use a mock response
            classification = {
              "is_lead": True, "rejection_reason": None, "author_role": "Hiring Manager",
              "intent": "Pain Point", "urgency": "Medium", "company_context": "Acme Corp",
              "actionable_angle": "They are struggling with technical assessments.",
              "summary": "Hiring manager at Acme Corp is frustrated with the quality of technical candidates."
            }


            # 2. Check LLM classification
            if not classification.get('is_lead'):
                continue

            # 3. Score the post
            score = score_post(post['text'])

            # 4. Qualify the lead
            if score >= MIN_LEAD_SCORE:
                lead_data = {
                    "timestamp": post['timestamp'],
                    "source": post['source'],
                    "url": post['url'],
                    "author": post['author'],
                    "author_role": classification['author_role'],
                    "intent": classification['intent'],
                    "urgency": classification['urgency'],
                    "score": score,
                    "company_context": classification['company_context'],
                    "summary": classification['summary'],
                    "actionable_angle": classification['actionable_angle'],
                    "original_text": post['text']
                }
                qualified_leads.append(lead_data)

        # 5. Write to CSV
        # ... (code to write qualified_leads to data/leads.csv using the new header)
    ```

### Step 4: Adapt `daily.py` and `weekly.py` for Recruitment Briefs

1.  **Action:** Modify `listening-loop/daily.py` and `listening-loop/weekly.py`.
2.  **Changes:**
    - **`daily.py`**: Instead of a generic digest, it should create a "Recruitment Daily Brief". This involves summarizing the *qualified leads* from `leads.csv` and highlighting any high-urgency items.
    - **`weekly.py`**: This script should analyze the `summary` and `intent` columns in `leads.csv` over the past week to identify recurring themes. The output should be a "Weekly Recruitment Pain Point Report" that summarizes the top 3-5 challenges discussed in the community (e.g., "Increased candidate ghosting," "Difficulty hiring senior engineers").

## 6. Test Plan & Verification

The following steps should be taken to verify the implementation.

### 6.1. Unit & Component Testing

- **Test `config.py`:** Manually inspect the file to ensure all new lists, dictionaries, and variables are present and correctly formatted.
- **Test `prompts.py`:** Manually inspect the prompt for clarity and ensure the schema is valid JSON.
- **Test Scoring Logic:** Create a test function for `score_post` in `digest.py` with sample text and assert the expected score.
- **Test Pre-filter Logic:** Create a test function for `pre_filter` with sample text containing negative keywords and assert it returns `False`.

### 6.2. Integration & Dry-Run Testing

1.  **Create Sample Data:** Create a file `data/test_posts.jsonl` with 5-10 sample posts. Include at least:
    - 2 clear job-seeker posts (should be rejected).
    - 1 post expressing hiring pain.
    - 1 post asking for ATS recommendations.
    - 1 generic post from a founder about company growth.

2.  **Digest Dry-Run:**
    - **Command:** `python digest.py --source data/test_posts.jsonl --output data/test_leads.csv --no-api-calls`
    - **Verification:**
        - Inspect `data/test_leads.csv`.
        - The file should exist and have the correct header.
        - It should contain rows only for the qualified leads from the test data.
        - The `author_role`, `intent`, `score`, etc., should be plausible based on the test data.
        - The job-seeker posts should NOT be in the CSV.

3.  **Daily/Weekly Dry-Run:**
    - **Command:** `python daily.py --source data/test_leads.csv` and `python weekly.py --source data/test_leads.csv`
    - **Verification:**
        - Check the generated markdown files (`daily.md`, `weekly.md`).
        - The daily brief should correctly summarize the test leads.
        - The weekly report should identify a mock "theme" from the test leads.

## 7. Acceptance Criteria

- **AC-1:** `config.py` contains recruitment-specific subreddits, X queries, a keyword scoring matrix, and negative keywords.
- **AC-2:** A new `prompts.py` file exists containing the specified LLM prompt and JSON schema for lead classification.
- **AC-3:** `digest.py` correctly uses the LLM prompt, rejects job-seeker posts, scores potential leads, and writes only qualified leads to `data/leads.csv` with the correct schema.
- **AC-4:** `daily.py` generates a markdown brief summarizing the day's qualified leads.
- **AC-5:** `weekly.py` generates a markdown report identifying recurring pain points from the week's leads.
- **AC-6:** All verification commands run successfully and produce the expected outputs based on test data.

## 8. Risks & Mitigation

- **Risk:** LLM prompt is not consistently accurate in classifying roles or rejecting candidates.
    - **Mitigation:** The prompt is designed to be very explicit. If issues arise, it will require prompt tuning and potentially few-shot examples. The `rejection_reason` field will help debug misclassifications.
- **Risk:** Data sources (subreddits, X) are too noisy, leading to low-quality captures.
    - **Mitigation:** The keyword pre-filtering and negative keyword checks are designed to reduce noise. The `config.py` file can be easily tweaked to refine sources and queries.

## 9. Rollback Notes

- Revert the changes by checking out the previous commit hash using `git checkout <commit_hash> .`.
- The primary files to revert are `config.py`, `digest.py`, `daily.py`, `weekly.py`, and deleting `prompts.py`.

## 10. Definition of Done

- All code changes outlined in the "Implementation Sequence" are complete and committed.
- All "Acceptance Criteria" are met.
- The "Test Plan" has been executed, and all verification steps pass successfully.
- The `README.md` (if it exists) is updated to reflect the new purpose and operation of the script.
