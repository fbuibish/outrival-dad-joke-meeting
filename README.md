## Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
# Daily.co Configuration
DAILY_SAMPLE_ROOM_URL=your_sample_room_url
DAILY_API_KEY=your_daily_api_key

# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key

# ElevenLabs TTS Configuration
ELEVENLABS_API_KEY=your_elevenlabs_api_key
ELEVENLABS_VOICE_ID=your_elevenlabs_voice_id
```

Note: Never commit your actual API keys to version control. The values shown above are just examples.

## Installation

1. Clone the repository:
```bash
git clone [your-repository-url]
```

2. Navigate to the project directory:
```bash
cd [project-name]
```

3. Create and activate a virtual environment (recommended):
```bash
# On Windows
python -m venv venv
.\venv\Scripts\activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Application

1. Make sure you've set up your environment variables in the `.env` file as shown above.

2. Start the customer service representative script:
```bash
python cs_rep.py
```

3. Quickly start the customer script (within 15 seconds):
```bash
python customer.py
```

To stop the application, press Ctrl+C in your terminal. 