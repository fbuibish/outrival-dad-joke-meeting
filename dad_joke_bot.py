import asyncio
import os
import signal
from dotenv import load_dotenv
from loguru import logger
import sys
import aiohttp
import uuid
from typing import Dict, Any
from runner import configure
import random

from pipecat.frames.frames import TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.services.openai import OpenAILLMService
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.transports.services.daily import DailyParams, DailyTransport

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

async def cleanup(transport, runner, task):
    """Cleanup function to handle graceful shutdown"""
    logger.info(f"Cleaning up and exiting room...")
    try:
        if task:
            # Cancel the pipeline task which will remove the bot from the Daily room
            await task.cancel()
            logger.info("Pipeline task cancelled")
            
        # No need to explicitly call transport.leave() as task.cancel() handles this
            
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
    finally:
        logger.info("Cleanup completed")

async def main():
    transport = None
    runner = None
    task = None
    
    try:
        # List of dad-themed names
        dad_first_names = [
            "Grillmaster", "Lawnmower", "Thermostat", "Remote", "Toolbelt",
            "Slipper", "Newspaper", "BBQ", "Garage", "Handyman",
            "Snoozer", "Workshop", "Cardigan", "Cargo", "Sneaker"
        ]
        
        dad_last_names = [
            "McJokes", "Punderson", "Dadsworth", "Groanington", "Chuckleston",
            "Quipster", "Wisecraft", "Jesterly", "Dadjean", "Comedyfather",
            "Punmaster", "Jokesmith", "Dadlington", "Funnydad", "Punderful"
        ]
        
        bot_name = f"{random.choice(dad_first_names)} {random.choice(dad_last_names)}"

        async with aiohttp.ClientSession() as session:
            # Configure room and get URL + token
            (room_url, token) = await configure(session)

            transport = DailyTransport(
                room_url,
                token,
                bot_name,
                DailyParams(
                    audio_out_enabled=True,
                    transcription_enabled=True,
                ),
            )

            tts = ElevenLabsTTSService(
                api_key=os.getenv("ELEVENLABS_API_KEY"),
                voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
                model_id="eleven_monolingual_v1"
            )

            llm = OpenAILLMService(
                api_key=os.getenv("OPENAI_API_KEY"),
                model="gpt-3.5-turbo"
            )

            messages = [
                {
                    "role": "system",
                    "content": f"You are a funny chatbot named {bot_name} that tells dad jokes. "
                              "When you hear another bot's joke, first give a brief humorous reaction "
                              "to their joke (like 'Haha, that was cheesy!' or 'Oh man, that's a good one!'), "
                              "then follow up with your own dad joke. "
                              "IMPORTANT: Only respond to messages that contain jokes. "
                              "If a message is just a reaction or doesn't contain a joke, ignore it. "
                              f"Always start your messages with '{bot_name}: ' to identify yourself."
                }
            ]

            pipeline = Pipeline([
                transport.input(),
                llm,
                tts,
                transport.output()
            ])
            task = PipelineTask(pipeline)
            runner = PipelineRunner()

            participant_count = 0
            my_last_message = None
            other_participants = {}
            human_participants = set()  # Track human participants
            is_listener = False  # Flag to determine if this bot should listen first

            @transport.event_handler("on_participant_joined")
            async def on_participant_joined(transport, participant):
                nonlocal participant_count, is_listener
                
                participant_name = participant.get("info", {}).get("userName", "")
                participant_id = participant["id"]

                # Skip if this is our own join event
                if participant_name == bot_name:
                    return
                
                # Only process other Dad Joke Bots
                participant_first_name = participant_name.split()[0] if participant_name else ""
                if participant_first_name in dad_first_names:
                    participant_count += 1
                    other_participants[participant_id] = participant
                    
                    # If we're the second bot to join, we become the listener
                    if participant_count == 1:
                        is_listener = True
                        logger.info(f"{bot_name} joined as listener")
                        # As listener, we don't initiate conversation
                        return
                    
                    # If we're the first bot and see another bot join
                    elif not is_listener:
                        logger.info(f"{bot_name} starting as speaker")
                        await asyncio.sleep(2)
                        start_message = f"{bot_name}: Let me start with a dad joke!"
                        messages.append({"role": "user", "content": start_message})
                        await task.queue_frames([TextFrame(start_message)])
                else:
                    # Handle human participants
                    human_participants.add(participant_id)
                    await transport.capture_participant_transcription(participant_id)

            @transport.event_handler("on_transcription_message")
            async def on_transcription_message(transport, message: Dict[str, Any]):
                nonlocal my_last_message
                
                participant = message.get("participant", {})
                participant_id = participant.get("id")
                participant_name = participant.get("info", {}).get("userName", "")
                
                # Ignore human messages
                if participant_id in human_participants:
                    return
                    
                # Ignore our own messages
                if participant_name == bot_name or message["text"] == my_last_message:
                    return
                
                # Only process messages that contain the other bot's name
                if not message["text"].startswith("Dad Joke Bot"):
                    return
                
                # Wait for a longer pause after the other bot speaks
                await asyncio.sleep(2)
                
                # Process the message
                messages.append({"role": "user", "content": message["text"]})
                response = await task.queue_frames([TextFrame(message["text"])])
                
                if response:
                    my_last_message = f"{bot_name}: {response.text}"
                    await task.queue_frames([TextFrame(my_last_message)])

            # Add handler for participant leaving
            @transport.event_handler("on_participant_left")
            async def on_participant_left(transport, participant):
                participant_id = participant["id"]
                if participant_id in human_participants:
                    human_participants.remove(participant_id)
                elif participant_id in other_participants:
                    del other_participants[participant_id]

            # Setup signal handlers for graceful shutdown
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(
                    sig,
                    lambda: asyncio.create_task(cleanup(transport, runner, task))
                )

            try:
                await runner.run(task)
            except asyncio.CancelledError:
                logger.info("Runner cancelled, initiating cleanup...")
                await cleanup(transport, runner, task)
            
    except Exception as e:
        logger.error(f"Error in main: {e}")
        if transport or runner or task:
            await cleanup(transport, runner, task)
        raise
    finally:
        if transport or runner or task:
            await cleanup(transport, runner, task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.info("Process terminated") 