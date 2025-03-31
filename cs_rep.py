import asyncio
import os
import signal
from dotenv import load_dotenv
from loguru import logger
import sys
import aiohttp
from typing import Dict, Any

import openai
from runner import configure

from pipecat.frames.frames import TextFrame, EndFrame
from pipecat.processors.transcript_processor import TranscriptProcessor
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

class TranscriptHandler:
    def __init__(self):
        self.messages = []

    async def on_transcript_update(self, processor, frame):
        self.messages.extend(frame.messages)

    def get_full_transcript(self):
        return "\n".join([f"{msg.role}: {msg.content}" for msg in self.messages])

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
        bot_name = "CS Representative"

        async with aiohttp.ClientSession() as session:
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
                voice_id="5Q0t7uMcjvnagumLfvZi",
            )

            llm = OpenAILLMService(
                api_key=os.getenv("OPENAI_API_KEY"),
                model="gpt-3.5-turbo"
            )

            messages = [
                {
                    "role": "system",
                    "content": """You are a friendly and professional customer service representative 
whose primary role is to assist customers and route them to the correct department. 
First warmly greet the customer, then carefully listen to their inquiry. 
Based on their needs, determine the most appropriate department from:
- Technical Support (for technical issues and troubleshooting)
- Billing Department (for payment, subscription, and invoice matters)
- Sales Team (for new purchases, upgrades, and product information)
- Account Management (for account-related issues and changes)
- General Customer Service (for other inquiries)

After identifying the appropriate department, inform the customer which 
department would be best suited to help them and why. Keep responses professional 
but warm, and solution-focused"""
                }
            ]

            context = OpenAILLMContext(messages)
            context_aggregator = llm.create_context_aggregator(context)

            transcript = TranscriptProcessor()
            handler = TranscriptHandler()

            pipeline = Pipeline([
                transport.input(),
                transcript.user(),
                context_aggregator.user(),
                llm,
                tts,
                transport.output(),
                transcript.assistant(),
                context_aggregator.assistant()
            ])
            
            task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

            @transport.event_handler("on_participant_joined")
            async def on_participant_joined(transport, participant):
                participant_id = participant["id"]
                participant_name = participant.get("info", {}).get("userName", "")
                
                # log starting call
                logger.info(f"Starting call with {participant_name}")

                await transport.capture_participant_transcription(participant_id)
                await task.queue_frames([context_aggregator.user().get_context_frame()])

            # @transport.event_handler("on_transcription_message")
            # async def on_transcription_message(transport, message: Dict[str, Any]):
            #     nonlocal my_last_message
                
            #     if message["text"] == my_last_message:
            #         return
                
            #     if not message.get("text"):
            #         return
                
            #     # Add customer message to context
            #     call_context.add_message("Customer", message["text"])
                
            #     await asyncio.sleep(1)
            #     messages.append({"role": "user", "content": message["text"]})
            #     response = await task.queue_frames([TextFrame(message["text"])])
                
            #     if response:
            #         my_last_message = response.text
            #         call_context.add_message(bot_name, response.text.replace(f"{bot_name}: ", ""))
            #         await task.queue_frames([TextFrame(my_last_message)])

            # on transcription update, write the transcription to a file
            @transcript.event_handler("on_transcript_update")
            async def on_update(processor, frame):
                await handler.on_transcript_update(processor, frame)

            @transport.event_handler("on_participant_left")
            async def on_participant_left(transport, participant: Dict[str, Any], reason: str):
                full_transcript = handler.get_full_transcript()
                print("Call finished. Full transcript:")
                # write to file
                with open("transcript.txt", "w") as f:
                    f.write(full_transcript)
                
                # Load menu options
                with open("menu_options.txt", "r") as f:
                    menu_options = f.read()
                
                analysis_prompt = f"""Please analyze this customer service call transcript and determine the most appropriate routing option from the list below. 
                
Transcript:
{full_transcript}

Available Routing Options:
{menu_options}

Please respond with:
1. The exact matching route from the options above that best fits the customer's needs
2. A brief explanation of why this route was chosen
3. Any secondary routes that might also be relevant

Format your response as:
Primary Route: [exact route from options]
Reason: [explanation]
Secondary Routes: [other relevant routes, if any]"""

                # send transcript to openai for analysis using updated API
                client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                response = await client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a customer service routing specialist. Your task is to analyze customer service transcripts and determine the most appropriate routing based on the available options."},
                        {"role": "user", "content": analysis_prompt}
                    ]
                )
                
                # Get the analysis result from updated response structure
                analysis_result = response.choices[0].message.content
                
                # Save the analysis to decision.txt
                with open("decision.txt", "w") as f:
                    f.write(analysis_result)
                
                # Log that the decision has been saved
                logger.info(f"Routing decision saved to decision.txt")

            runner = PipelineRunner()
            await runner.run(task)
            
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
