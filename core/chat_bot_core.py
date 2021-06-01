from .db_connector import DatabaseConnectionPool
from .users import UsersController
from .conversations import ConversationsController
from .invitations import InvitationsController


class ChatBotCore(UsersController, ConversationsController, InvitationsController):
    # TODO: When working on #37 I'm going to redesign this class in the following way (and make the explanation below
    #  its documentation)
    # TODO: Also, when working on #33, I should
    """
    NOT WORKING THIS WAY YET, THIS IS A DRAFT

    `ChatBotCore` accumulates all the back-end (aka core) features and should be used as an interface for front-end's
    interaction with back-end. Most methods are derived from the base classes defined in the `core` package, however
    there are a couple of methods overridden. For example, `ChatBotCore` takes responsibility for keeping invitations
    consistent (i.e. remove invitations for users which join conversations, and restore them when conversations
    finish). For that, e.g. the `begin_conversation` and `end_conversation` methods are overridden, because
    `ChatBotCore` does some additional work with invitations when conversations statuses are updated.
    """

    def __init__(self, db_host: str, db_name: str, db_username: str, db_password: str):
        conn_pool = DatabaseConnectionPool(db_host, db_name, db_username, db_password)
        UsersController.__init__(self, conn_pool)
        ConversationsController.__init__(self, conn_pool)
        InvitationsController.__init__(self, self, self)
