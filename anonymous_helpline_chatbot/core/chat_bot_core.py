from contextlib import contextmanager
from typing import Set, Any, Callable, Optional, Generator

from .db_connector import DatabaseConnectionPool
from .users import UsersController
from .conversations import ConversationsController
from .invitations import InvitationsController


class ChatBotCore:
    def __init__(self, db_host: str, db_name: str, db_username: str, db_password: str,
                 send_invitation_callback: Callable[[int, int, str], int],
                 delete_invitation_callback: Callable[[int, int], Any]):
        conn_pool = DatabaseConnectionPool(db_host, db_name, db_username, db_password)
        self._users_controller = UsersController(conn_pool)
        self._conversations_controller = ConversationsController(conn_pool)
        self._invitations_controller = InvitationsController(conn_pool,
                                                             self._users_controller, self._conversations_controller,
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

    @contextmanager
    def request_conversation_with_locking(self, client_chat_id: int) -> Generator[bool, None, None]:
        with self._conversations_controller.request_conversation_with_locking(client_chat_id) as res:
            if res:
                self.invite_to_client(client_chat_id)
            yield res

    @contextmanager
    def begin_conversation_with_locking(self, client_chat_id: int, operator_chat_id: int) -> Generator[int, None, None]:
        with self._conversations_controller.begin_conversation_with_locking(client_chat_id, operator_chat_id) as res:
            if res == 0:
                self.clear_invitations_to_client(client_chat_id)
                self.clear_invitations_for_operator(operator_chat_id)
            yield res

    @contextmanager
    def end_conversation_or_cancel_request_with_locking(self,
                                                        client_chat_id: int) -> Generator[Optional[int], None, None]:
        with self._conversations_controller.end_conversation_or_cancel_request_with_locking(client_chat_id) as \
                operator_chat_id:

            if operator_chat_id == -1:
                self.clear_invitations_to_client(client_chat_id)
            elif operator_chat_id is not None:
                self.invite_for_operator(operator_chat_id)
                # If this conversation's client is an operator, restore invitations for him, too
                if self._users_controller.is_operator(operator_chat_id):
                    self.invite_for_operator(client_chat_id)
            yield operator_chat_id
