from ._init_objects import bot
# Create `bot` handlers
from . import tg_message_handlers as _
from . import tg_callback_handlers as _


__all__ = ["bot"]
