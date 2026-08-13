# AI Credentials Configuration

## Overview
All credentials for the AI backend have been centralized in `AI.env` for easier handover and configuration management.

## Quick Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Credentials**
   Edit `AI.env` and update the following values with your own credentials:

   - **MONGO_URI**: Your MongoDB Atlas connection string
     - Get from: MongoDB Atlas Dashboard > Connect > Connect your application
     - Format: `mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority`

   - **GROQ_API_KEY**: Your Groq API key for LLM inference
     - Get from: https://console.groq.com/
     - Format: `gsk_xxxxxxxxxxxxxxxxxxxxx`

3. **NLP enrichment models / knobs**
   Edit `enrichment/settings.py` (not `AI.env`) to switch models or tune:
   - `NLP_BACKUP_MODEL` / `NLP_OPENAI_ONLY` / `NLP_PRIMARY_MODEL`
   - `NLP_TIMEOUT_MS`, `NLP_SUMMARY_MIN_CHARS`, `NLP_LONG_CHARS`
   API keys stay in `AI.env`.

4. **Verify Configuration**
   The code will automatically load credentials from `AI.env` when running any AI module.
   If credentials are missing, you'll see a clear error message indicating which credential is not found.

## Files Modified

All Python files in the AI directory now load credentials from `AI.env` using:
```python
from dotenv import load_dotenv
from pathlib import Path
import os

env_path = Path(__file__).parent.parent / "AI.env"
load_dotenv(env_path)

MONGO_URI = os.getenv("MONGO_URI")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
```

## Security Notes

- **NEVER** commit `AI.env` with real credentials to version control
- The `.gitignore` should include `*.env` to prevent accidental commits
- During handover, provide credentials separately (e.g., via secure channel)
- Consider using different credentials for development, staging, and production environments

## Troubleshooting

**Error: "MONGO_URI not found in AI.env"**
- Ensure `AI.env` exists in the `code/Backend/ai/` directory
- Check that the `MONGO_URI` line is uncommented and has a valid value

**Error: "GROQ_API_KEY not found in AI.env"**
- Ensure `AI.env` exists in the `code/Backend/ai/` directory
- Check that the `GROQ_API_KEY` line is uncommented and has a valid value

**Connection errors**
- Verify your MongoDB URI is correct and the cluster is accessible
- Check that your Groq API key is valid and has sufficient quota
- Ensure your IP address is whitelisted in MongoDB Atlas (or set to 0.0.0.0/0 for development)
