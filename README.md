# Project Overview
VoiceBot is a scalable and intelligent voicebot system designed to automate outbound voice calls for user engagement campaigns. This solution leverages Google Cloud Text-to-Speech and Speech-to-Text services, multilingual support (English and Hindi), and integrates with Redis, MongoDB, and a dialer API to orchestrate smart conversations based on intent recognition.

# 📂 Project Structure
File/Folder	Description
create_responses.py	Prepares customized responses from responses.json by adjusting names, genders, and translating to target language (e.g., Hindi).
encodings.py	Converts text responses into audio encodings using Google TTS. Supports multilingual and gender-specific voice synthesis.
responses.json	Defines the bot's call flow logic and script, structured as conversational nodes.
transcribe.py	REST API (FastAPI) to receive base64-encoded audio and transcribe it using Google Speech-to-Text, with support for intent classification and translation.
utils.py	Shared utility functions for text-to-speech, translation, audio processing, and next-node logic in conversation.
voicebot.py	Main orchestration server that manages campaign scheduling, API authentication, concurrent call handling, campaign metadata setup, and cleanup.
# 🚀 Key Features
🔊 Text-to-Speech & Speech-to-Text: Uses Google Cloud APIs for realistic voice synthesis and transcription.
🌐 Multilingual Support: Built-in English and Hindi language capabilities, with gender-based voice customization.
⚡ FastAPI Services: Endpoints for transcription, recording, call scheduling, and tracking call status.
📊 Campaign Orchestration: Schedules and manages outbound calls with retry logic and time-window constraints.
📦 Redis Caching: Manages real-time sessions, audio encodings, campaign queues, and intents.
🗃️ MongoDB Storage: Persists campaign details, ongoing calls, and call history.
🔐 API Key Protection: Secure access control for dashboard and dialer integrations.
📈 Scalable Execution: Supports up to 60 parallel outbound calls, with a retry system for unanswered or failed calls.
🧠 How It Works
Campaign Upload: A CSV file with phone numbers and customer names is uploaded via /schedule_calls.
Audio Preparation: Responses from responses.json are translated (if needed), gender-adjusted, and synthesized into audio using Google TTS.
Call Initiation: Call requests are sent to the dialer via the external API (callAPIRequest). Each call is tracked with a UUID.
Real-Time Transcription: During a call, customer responses are transcribed and interpreted for intent. Next steps are dynamically decided based on this input.
Completion & Recording: Upon call conclusion, status and recordings are updated via /status and /recording endpoints.
# 🛠️ Tech Stack
Python 3.9+
FastAPI
MongoDB
Redis
Google Cloud Platform: Text-to-Speech, Speech-to-Text, Translate
pydub, pytz, uuid, base64, tqdm, pandas
📦 Setup Instructions
Before you begin, ensure you have your Google Cloud credentials and MongoDB/Redis set up locally or remotely.

# Install dependencies
bash
Copy
Edit
pip install -r requirements.txt
Add Google Cloud credentials
Store your ailifebot-8fac6d214f8d.json file and set environment variable:
bash
Copy
Edit
export GOOGLE_APPLICATION_CREDENTIALS="ailifebot-8fac6d214f8d.json"
Run the main API servers
bash
Copy
Edit
uvicorn voicebot:app --host 0.0.0.0 --port 8000
uvicorn transcribe:app --host 0.0.0.0 --port 8001
🔒 Authentication
Two types of API keys are used:

Dashboard Key: To schedule campaigns.
Dialer Key: To handle call updates and status changes.
📞 Sample API Usage
bash
Copy
Edit
# Schedule a campaign
POST /schedule_calls
Headers: access_token (Dashboard Key)
Body: CSV file + campaign metadata

# Transcribe audio during call
POST /transcribe
Body: base64 audio + call ID + campaign ID

# Mark call status
POST /status
Body: call_id, campaign_id, call_status
🧑‍💻 Contributions
This project was built as part of an in-house solution for automated customer engagement. If you're interested in contributing or customizing it for another use case, feel free to fork and open a pull request.

📝 License
Internal use only — please seek permission before reusing parts of this implementation.
