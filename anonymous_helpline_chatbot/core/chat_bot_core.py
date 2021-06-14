from typing import Set, Any, Callable, Optional

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

    def invite_to_client(self, client_chat_id: int) -> bool:
        with self._conversations_controller.lock_conversations_and_requests_list():
            (_, _), (_, operator_chat_id) = self.get_conversing(client_chat_id)
            if operator_chat_id is None:  # Not in a conversation
                self._invitations_controller.invite_to_client(client_chat_id)
                return True
            else:
                return False

    def invite_for_operator(self, operator_chat_id: int) -> bool:
        with self._conversations_controller.lock_conversations_and_requests_list():
            (client_chat_id, _), (_, _) = self.get_conversing(operator_chat_id)
            if client_chat_id is None:  # Not in a conversation
                self._invitations_controller.invite_for_operator(operator_chat_id)
                return True
            else:
                return False

    def request_conversation(self, client_chat_id: int) -> bool:
        if self._conversations_controller.request_conversation(client_chat_id):
            self.invite_to_client(client_chat_id)
            return True
        else:
            return False

    def begin_conversation(self, client_chat_id: int, operator_chat_id: int) -> int:
        res = self._conversations_controller.begin_conversation(client_chat_id, operator_chat_id)
        if res == 0:
            # FIXME: thread-safety suffers here. And somewhere near too, probably
            self.clear_invitations_to_client(client_chat_id)
            self.clear_invitations_for_operator(operator_chat_id)
        return res

    def end_conversation_or_cancel_request(self, client_chat_id: int) -> Optional[int]:
        operator_chat_id = self._conversations_controller.end_conversation_or_cancel_request(client_chat_id)
        if operator_chat_id == -1:
            self.clear_invitations_to_client(client_chat_id)
        elif operator_chat_id is not None:
            self.invite_for_operator(operator_chat_id)
            # If this conversation's client is an operator, restore invitations for him, too
            if self._users_controller.is_operator(operator_chat_id):
                self.invite_for_operator(client_chat_id)
        return operator_chat_id
