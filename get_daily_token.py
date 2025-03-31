#!/usr/bin/env python
#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import argparse
import asyncio
import os
import sys

import aiohttp

from pipecat.transports.services.helpers.daily_rest import DailyRESTHelper


async def get_token():
    async with aiohttp.ClientSession() as session:
        try:
            # Parse command line arguments
            parser = argparse.ArgumentParser(description="Get Daily REST Token")
            parser.add_argument(
                "-u", "--url", type=str, required=False, help="URL of the Daily room to join"
            )
            parser.add_argument(
                "-k",
                "--apikey",
                type=str,
                required=False,
                help="Daily API Key (needed to create an owner token for the room)",
            )
            parser.add_argument(
                "-e",
                "--expiry",
                type=int,
                default=60 * 60,
                help="Token expiry time in seconds (default: 3600)",
            )

            args = parser.parse_args()

            url = args.url or os.getenv("DAILY_SAMPLE_ROOM_URL")
            key = args.apikey or os.getenv("DAILY_API_KEY")
            expiry_time = args.expiry

            if not url:
                print("Error: No Daily room specified. Use -u/--url option or set DAILY_SAMPLE_ROOM_URL environment variable.")
                sys.exit(1)

            if not key:
                print("Error: No Daily API key specified. Use -k/--apikey option or set DAILY_API_KEY environment variable.")
                print("API keys are available from https://dashboard.daily.co/developers")
                sys.exit(1)

            daily_rest_helper = DailyRESTHelper(
                daily_api_key=key,
                daily_api_url=os.getenv("DAILY_API_URL", "https://api.daily.co/v1"),
                aiohttp_session=session,
            )

            # Get the token
            token = await daily_rest_helper.get_token(url, expiry_time)
            
            # Print the token to console
            print(f"Daily REST Token: {token}")
            print(f"Token will expire in: {expiry_time} seconds")
            
            return token
        
        except Exception as e:
            print(f"Error retrieving token: {e}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(get_token()) 