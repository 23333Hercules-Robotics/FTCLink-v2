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
            branding = "Powered by Orihost (tm) · Based off FTC Dozer"
            
            # Check if branding is already present
            if embed.footer and embed.footer.text:
                if "Powered by Orihost" not in embed.footer.text:
                    # Append to existing footer, preserving icon_url if it exists
                    if embed.footer.icon_url:
                        embed.set_footer(text=f"{embed.footer.text} | {branding}", icon_url=embed.footer.icon_url)
                    else:
                        embed.set_footer(text=f"{embed.footer.text} | {branding}")
            else:
                # Set new footer with branding
                embed.set_footer(text=branding)
        
        return await super().send(content, **kwargs)
