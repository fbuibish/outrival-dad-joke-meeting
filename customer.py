import asyncio
import os
import signal
from dotenv import load_dotenv
from loguru import logger
import sys
import aiohttp
from typing import Dict, Any
from runner import configure

from pipecat.frames.frames import TextFrame, EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.openai import OpenAILLMService, OpenAILLMContext
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.transports.services.daily import DailyParams, DailyTransport
from pipecat.audio.vad.silero import SileroVADAnalyzer

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

async def cleanup(transport, runner, task):
    """Cleanup function to handle graceful shutdown"""
    logger.info("Cleaning up and exiting room...")
    try:
        if task:
            await task.queue_frame(EndFrame())
            logger.info("Pipeline task cancelled")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
    finally:
        logger.info("Cleanup completed")

async def main():
    transport = None
    runner = None
    task = None
    
    try:
        bot_name = "Angry Customer Bot"

        async with aiohttp.ClientSession() as session:
            # Configure room and get URL + token
            (room_url, token) = await configure(session)

            transport = DailyTransport(
                room_url,
                token,
                bot_name,
                DailyParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                    camera_out_enabled=False,
                    vad_enabled=True,
                    vad_analyzer=SileroVADAnalyzer(),
                    transcription_enabled=True,
                ),
            )

            tts = ElevenLabsTTSService(
                api_key=os.getenv("ELEVENLABS_API_KEY"),
                voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
            )

            llm = OpenAILLMService(
                api_key=os.getenv("OPENAI_API_KEY"),
                model="gpt-3.5-turbo"
            )

            messages = [
                {
                    "role": "system",
                    "content": "You are a frustrated customer calling about a broken laptop from TechMart. " +
                              "Key points: " +
                              "- Laptop screen is completely black after 2 days of use " +
                              "- You paid $800 last week " +
                              "- You need it for work tomorrow " +
                              "\n" +
                              "Instructions: " +
                              "- Ask maximum 2 questions during the entire conversation " +
                              "- Accept and agree to any solution the customer service rep suggests " +
                              "- Stay in character as the customer (never provide advice or help) " +
                              "- Keep responses under 2 sentences."
                }
            ]

            context = OpenAILLMContext(messages)
            context_aggregator = llm.create_context_aggregator(context)

            pipeline = Pipeline([
                transport.input(),
                context_aggregator.user(),
                llm,
                tts,
                transport.output(),
                context_aggregator.assistant()
            ])
            
            task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=False))

            @transport.event_handler("on_participant_joined")
            async def on_participant_joined(transport, participant):
                participant_id = participant["id"]
                participant_name = participant.get("info", {}).get("userName", "")

                if participant_name == 'frank':
                    return
                
                # log starting call
                logger.info(f"Starting call with {participant_name}")
                
                # Add to human participants and enable transcription
                await transport.capture_participant_transcription(participant_id)
                
                await task.queue_frames([context_aggregator.user().get_context_frame()])

            # @transport.event_handler("on_transcription_message")
            # async def on_transcription_message(transport, message: Dict[str, Any]):
            #     nonlocal my_last_message

            #     # add logging
            #     logger.info(f"Received message: {message}")
            #     # Skip our own messages
            #     if message["text"] == my_last_message:
            #         return
                
            #     # Skip messages from non-humans or empty messages
            #     if not message.get("text"):
            #         return
                
            #     # Add a small delay before responding
            #     await asyncio.sleep(1)
                
            #     # Process the message
            #     messages.append({"role": "user", "content": message["text"]})
            #     response = await task.queue_frames([TextFrame(message["text"])])
                
            #     if response:
            #         my_last_message = response.text
            #         await task.queue_frames([TextFrame(my_last_message)])

            @transport.event_handler("on_participant_left")
            async def on_participant_left(transport, participant):
                await task.cancel()

            # Setup signal handlers for graceful shutdown
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(
                    sig,
                    lambda: asyncio.create_task(cleanup(transport, runner, task))
                )

            try:
                runner = PipelineRunner()

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
