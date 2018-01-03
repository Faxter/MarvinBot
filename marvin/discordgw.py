import asyncio
import discord
from discord.ext import commands
from discord.ext.commands import Bot as BotBase
from discord.enums import Status
from discord.game import Game


DESCRIPTION = '''Marvin ist die künstliche Intelligenz des shockG Discord'''
SAFE_CHANNELS = ['botspam', ]


class MarvinBot(BotBase):
    async def sane_logout(self):
        print('entering sane_logout')
        print(self.user.name, 'out')
        self.change_presence(status=Status.offline)
        self.logout()


bot = MarvinBot(command_prefix='!', description=DESCRIPTION)
botgame = Game(name='Life, the Universe and Everything')


@bot.event
async def on_ready():
    print('Bot logged in as')
    print(bot.user.name)
    print('------')
    await bot.change_presence(status=Status.online, game=botgame)


if not discord.opus.is_loaded():
    # the 'opus' library here is opus.dll on windows
    # or libopus.so on linux in the current directory
    # you should replace this with the location the
    # opus library is located in and with the proper filename.
    # note that on windows this DLL is automatically provided for you
    discord.opus.load_opus('opus')


class VoiceEntry:
    def __init__(self, message, player):
        self.requester = message.author
        self.channel = message.channel
        self.player = player

    def __str__(self):
        fmt = '*{0.title}* Upload von {0.uploader} und vorgeschlagen von {1.display_name}'
        duration = self.player.duration
        if duration:
            fmt = fmt + ' [Länge: {0[0]}m {0[1]}s]'.format(divmod(duration, 60))
        return fmt.format(self.player, self.requester)


class VoiceState:
    def __init__(self, bot):
        self.current = None
        self.voice = None
        self.bot = bot
        self.play_next_song = asyncio.Event()
        self.songs = asyncio.Queue()
        self.skip_votes = set()  # a set of user_ids that voted
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())

    def is_playing(self):
        if self.voice is None or self.current is None:
            return False

        player = self.current.player
        return not player.is_done()

    @property
    def player(self):
        return self.current.player

    def skip(self):
        self.skip_votes.clear()
        if self.is_playing():
            self.player.stop()

    def toggle_next(self):
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)

    async def audio_player_task(self):
        while True:
            self.play_next_song.clear()
            self.current = await self.songs.get()
            await self.bot.send_message(self.current.channel, 'Es spielt ' + str(self.current))
            self.current.player.start()
            await self.play_next_song.wait()


class Music:
    """Voice related commands.
    Works in multiple servers at once."""

    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, server):
        state = self.voice_states.get(server.id)
        if state is None:
            state = VoiceState(self.bot)
            self.voice_states[server.id] = state

        return state

    async def create_voice_client(self, channel):
        voice = await self.bot.join_voice_channel(channel)
        state = self.get_voice_state(channel.server)
        state.voice = voice

    def __unload(self):
        for state in self.voice_states.values():
            try:
                state.audio_player.cancel()
                if state.voice:
                    self.bot.loop.create_task(state.voice.disconnect())
            except:
                pass

    @commands.command(pass_context=True, no_pm=True)
    async def join(self, ctx, *, channel: discord.Channel):
        """Bewegt Marvin in den angegebenen Voice Channel"""
        if ctx.message.channel.name not in SAFE_CHANNELS:
            return

        try:
            await self.create_voice_client(channel)
        except discord.ClientException:
            await self.bot.say('Bin schon in einem Voice Channel...')
        except discord.InvalidArgument:
            await self.bot.say('Das ist kein Voice Channel...')
        else:
            await self.bot.say('Bereit zum Audio abspielen in ' + channel.name)

    @commands.command(pass_context=True, no_pm=True)
    async def summon(self, ctx):
        """Bewegt Marvin in deinen aktuellen Voice Channel"""
        if ctx.message.channel.name not in SAFE_CHANNELS:
            return

        summoned_channel = ctx.message.author.voice_channel
        if summoned_channel is None:
            await self.bot.say('Du bist in keinem Voice Channel.')
            return False

        state = self.get_voice_state(ctx.message.server)
        if state.voice is None:
            state.voice = await self.bot.join_voice_channel(summoned_channel)
        else:
            await state.voice.move_to(summoned_channel)

        return True

    @commands.command(pass_context=True, no_pm=True)
    async def play(self, ctx, *, song: str):
        """Such nach dem angegebenen Song und spielt ihn ab
        If there is a song currently in the queue, then it is
        queued until the next song is done playing.
        This command automatically searches as well from YouTube.
        The list of supported sites can be found here:
        https://rg3.github.io/youtube-dl/supportedsites.html
        """
        if ctx.message.channel.name not in SAFE_CHANNELS:
            return

        state = self.get_voice_state(ctx.message.server)
        opts = {
            'default_search': 'auto',
            'quiet': True,
        }

        if state.voice is None:
            success = await ctx.invoke(self.summon)
            if not success:
                return

        try:
            player = await state.voice.create_ytdl_player(song, ytdl_options=opts, after=state.toggle_next)
        except Exception as e:
            fmt = 'An error occurred while processing this request: ```py\n{}: {}\n```'
            await self.bot.send_message(ctx.message.channel, fmt.format(type(e).__name__, e))
        else:
            player.volume = 0.6
            entry = VoiceEntry(ctx.message, player)
            await self.bot.say('An die Warteschlange gehängt: ' + str(entry))
            await state.songs.put(entry)

    @commands.command(pass_context=True, no_pm=True)
    async def volume(self, ctx, value: int):
        """Setzt die Lautstärke auf den angegebenen Wert (0..100)"""
        if ctx.message.channel.name not in SAFE_CHANNELS:
            return

        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.volume = value / 100
            await self.bot.say('Lautstärke gesetzt auf {:.0%}'.format(player.volume))

    @commands.command(pass_context=True, no_pm=True)
    async def pause(self, ctx):
        """Pausiert Wiedergabe"""
        if ctx.message.channel.name not in SAFE_CHANNELS:
            return

        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.pause()

    @commands.command(pass_context=True, no_pm=True)
    async def resume(self, ctx):
        """Lässt den pausierten Song weiterlaufen"""
        if ctx.message.channel.name not in SAFE_CHANNELS:
            return

        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.resume()

    @commands.command(pass_context=True, no_pm=True)
    async def stop(self, ctx):
        """Stoppt das Abspielen und bewegt Marvin aus dem Voice Channel
        Löscht außerdem die Queue
        """
        if ctx.message.channel.name not in SAFE_CHANNELS:
            return

        server = ctx.message.server
        state = self.get_voice_state(server)

        if state.is_playing():
            player = state.player
            player.stop()

        try:
            state.audio_player.cancel()
            del self.voice_states[server.id]
            await state.voice.disconnect()
        except:
            pass

    @commands.command(pass_context=True, no_pm=True)
    async def skip(self, ctx):
        """Skip Vote für aktuellen Song - Requester kann sofort skippen
        Es werden 3 Skip Votes benötigt
        """
        if ctx.message.channel.name not in SAFE_CHANNELS:
            return

        state = self.get_voice_state(ctx.message.server)
        if not state.is_playing():
            await self.bot.say('Ich spiele gerade keine Musik...')
            return

        voter = ctx.message.author
        if voter == state.current.requester:
            await self.bot.say('Nutzer hat angefragt, seinen Song zu skippen...')
            state.skip()
        elif voter.id not in state.skip_votes:
            state.skip_votes.add(voter.id)
            total_votes = len(state.skip_votes)
            if total_votes >= 3:
                await self.bot.say('Skip Vote ging durch, überspringe Song...')
                state.skip()
            else:
                await self.bot.say('Skip Vote gestartet, Stand [{}/3]'.format(total_votes))
        else:
            await self.bot.say('Du hast in diesem Skip Vote schon abgestimmt.')

    @commands.command(pass_context=True, no_pm=True)
    async def playing(self, ctx):
        """Zeigt Info des aktuellen Songs"""
        if ctx.message.channel.name not in SAFE_CHANNELS:
            return

        state = self.get_voice_state(ctx.message.server)
        if state.current is None:
            await self.bot.say('Ich spiele gerade nichts ab.')
        else:
            skip_count = len(state.skip_votes)
            await self.bot.say('Spiele jetzt {} [Skip Votes: {}/3]'.format(state.current, skip_count))


bot.add_cog(Music(bot))

# -------------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------


@bot.command(pass_context=True)
async def add(ctx, left: int, right: int):
    """Addiert 2 Zahlen"""
    if ctx.message.channel.name not in SAFE_CHANNELS:
        return

    await bot.say(left + right)


@bot.command(pass_context=True)
async def game_on(ctx):
    """Marvin kommt online und spielt ein Spiel"""
    if ctx.message.channel.name not in SAFE_CHANNELS:
        return

    await bot.change_presence(status=Status.online, game=botgame)


@bot.command(pass_context=True)
async def game_off(ctx):
    """Marvin ist abwesend"""
    if ctx.message.channel.name not in SAFE_CHANNELS:
        return

    await bot.change_presence(status=Status.idle, game=None)


@bot.command(pass_context=True)
async def stirb(ctx):
    """Marvin geht offline"""
    if ctx.message.channel.name not in SAFE_CHANNELS:
        return

    await bot.change_presence(status=Status.offline)
    await bot.logout()


@bot.command(pass_context=True)
async def set_avatar(ctx, filename: str):
    """Setzt Avatar von Marvin"""
    if ctx.message.channel.name not in SAFE_CHANNELS:
        return

    file = open(filename, 'rb')
    avatar = file.read()
    await bot.edit_profile(avatar=avatar)
