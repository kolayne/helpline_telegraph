from typing import Set, Any, Callable

from .db_connector import DatabaseConnectionPool
from .users import UsersController
from .conversations import ConversationsController
from .invitations import InvitationsController


class ChatBotCore:
    # When working on #37, I'm going to "override" `begin_conversation`/`end_conversation` methods, so that
    # `ChatBotCore` will do some additional work there. TODO: not forget to mention this ability of the class in its
    #  docs when I'll be writing them (#33)

    def __init__(self, db_host: str, db_name: str, db_username: str, db_password: str,
                 send_invitation_callback: Callable[[int, int, str], int],
                 delete_invitation_callback: Callable[[int, int], Any]):
        conn_pool = DatabaseConnectionPool(db_host, db_name, db_username, db_password)
        self._users_controller = UsersController(conn_pool)
        self._conversations_controller = ConversationsController(conn_pool)
        self._invitations_controller = InvitationsController(conn_pool, self._users_controller,
                                                             send_invitation_callback, delete_invitation_callback)

    def __dir__(self) -> Set[str]:
        # Pretend that besides the attributes the object really has and the overridden methods, it also has the methods
        # defined in the controllers
        return set().union(
            super().__dir__(),  # Attributes/methods we actually have
            dir(self._users_controller),
            dir(self._conversations_controller),
            dir(self._invitations_controller)
        )

    def __getattr__(self, item):
        for controller in (self._users_controller, self._conversations_controller, self._invitations_controller):
            if hasattr(controller, item):
                return controller.__getattribute__(item)

        # If reached this point, then `item` is not defined in any of the controllers. Produce `AttributeError`
        # (by calling `object.__getattribute__`):
        return super().__getattribute__(item)
