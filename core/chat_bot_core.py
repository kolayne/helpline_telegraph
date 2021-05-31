from .db_connector import DatabaseConnectionPool
from .users import UsersController
from .conversations import ConversationsController
from .invitations import InvitationsController


class ChatBotCore:
    def __init__(self, db_host, db_name, db_username, db_password):
        self._conn_pool = DatabaseConnectionPool(db_host, db_name, db_username, db_password)
        self.users_controller = UsersController(self._conn_pool)
        self.conversations_controller = ConversationsController(self._conn_pool)
        self.invitations_controller = InvitationsController(self.users_controller, self.conversations_controller)
