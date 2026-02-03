"""Class that holds dozercontext. """
import discord
from discord.ext import commands

from dozer import utils


class DozerContext(commands.Context):
    """Cleans all messages before sending"""

    async def send(self, content=None, **kwargs):  # pylint: disable=arguments-differ
        """Make it so you cannot ping @.everyone when sending a message"""
        if content is not None:
            content = utils.clean(self, content, mass=True, member=False, role=False, channel=False)
        
        # Add branding footer to all embeds
        if 'embed' in kwargs and kwargs['embed'] is not None:
            embed = kwargs['embed']
            if not embed.footer or not embed.footer.text:
                embed.set_footer(text="Powered by Orihost (tm) · Based off FTC Dozer")
            elif "Powered by Orihost" not in embed.footer.text:
                # Append to existing footer
                embed.set_footer(text=f"{embed.footer.text} · Powered by Orihost (tm) · Based off FTC Dozer")
        
        return await super().send(content, **kwargs)
