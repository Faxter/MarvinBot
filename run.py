#!/usr/bin/env python3

import asyncio
from marvin.discordgw import bot as discord_bot


@asyncio.coroutine
async def main_task():
    await discord_bot.login('MzY1OTczNzgyMDUxMTYwMDY2.DLmHLA.EHKi1gfJTdS8UAGYeak26J4TryU')
    await discord_bot.connect()


loop = asyncio.get_event_loop()
try:
    loop.run_until_complete(main_task())
except (Exception, KeyboardInterrupt) as e:
    print('Ich glaube, ich schalte mich ab.')
    print(str(e))
    loop.run_until_complete(discord_bot.sane_logout())
finally:
    loop.close()
