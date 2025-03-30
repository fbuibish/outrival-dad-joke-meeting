## Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
# Daily.co Configuration
DAILY_SAMPLE_ROOM_URL=your_sample_room_url
DAILY_API_KEY=your_daily_api_key

# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key

# Cartesia TTS Configuration
CARTESIA_API_KEY=your_cartesia_api_key
CARTESIA_VOICE_ID=your_cartesia_voice_id
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

## Running the Dad Joke Bot

1. Make sure you've set up your environment variables in the `.env` file as shown above.

2. Run the bot:
```bash
python dad_joke_bot.py
```

The bot will:
- Connect to the Daily.co room specified in your environment variables
- Generate a unique name for itself (e.g., "Dad Joke Bot abc123")
- Tell dad jokes and respond to other Dad Joke Bots in the room
- Use text-to-speech to speak the jokes out loud
- Automatically clean up and exit when you press Ctrl+C

To stop the bot, press Ctrl+C in your terminal. 