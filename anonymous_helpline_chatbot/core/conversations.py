from contextlib import contextmanager
from typing import Union, Tuple, Optional, Generator, Iterable

from .db_connector import DatabaseConnectionPool, cursor_type


Conversing = Union[Tuple[Tuple[int, int], Tuple[int, int]],
                   Tuple[Tuple[None, None], Tuple[None, None]]]


class ConversationsController:
    def __init__(self, database_connection_pool: DatabaseConnectionPool):
        self._conn_pool = database_connection_pool

    @contextmanager
    def lock_conversations_list(self) -> Generator[None, None, None]:
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("LOCK TABLE conversations IN SHARE MODE")
            yield

    def _get_conversing_for_share(self, cursor: cursor_type, chat_id: int) -> Conversing:
        """
        Just like `.get_conversing` (see below), but accepts `cursor`, which is a database cursor, and retrieves
        the ids using that cursor with the `SELECT FOR SHARE` query. Thus, if the conversation exists, it is guaranteed
        to not be finished at least until the current transaction of `cursor` is finished (or rolled back to a
        savepoint). **WARNING**: it is NOT guaranteed that if conversation doesn't exist now then it won't start.
        """
        cursor.execute("SELECT client_chat_id,   (SELECT local_id FROM users WHERE chat_id=client_chat_id), "
                       "       operator_chat_id, (SELECT local_id FROM users WHERE chat_id=operator_chat_id) "
                       "FROM conversations "
                       "WHERE client_chat_id = %s OR operator_chat_id = %s "
                       "FOR SHARE",
                       (chat_id, chat_id))
        result = cursor.fetchone()
        if result is None:
            result = (None, None, None, None)
        a, b, c, d = result
        return (a, b), (c, d)

    def get_conversing(self, chat_id: int) -> Conversing:
        """
        Get client and operator from a conversation with a user with the given identifier

        Retrieves both telegram and local identifiers of both client and operator of the conversation, in which the
        given user takes part. This function can be used for understanding whether current user is a client or an
        operator in his conversation, retrieving information about his interlocutor, etc

        Warning: if your application is working in a multi-threaded environment (which is extremely likely), the
        conversations are expected to be started or finished sometimes, so something might change between the moment
        when you call this function and the moment when you use the returned result. That's why it is highly recommended
        to only use this function together with the `.lock_conversations_list` context manager. For example,

        ```
        # WRONG!!!
        (_, _), (operator_chat_id, _) = conversations_controller.get_conversing(some_user_chat_id)
        if operator_chat_id is None:
            # Another thread might have already created a conversation with that user, so we're using outdated data
            print("User is not in a conversation")
        ```

        ```
        # CORRECT
        with conversations_controller.lock_conversations_list():
            # While we're inside of this block, no conversations can start or finish. All the other threads will wait
            (_, _), (operator_chat_id, _) = conversations_controller.get_conversing(some_user_chat_id)
            if operator_chat_id is None:
                print("User is not in a conversation")
        ```

        :param chat_id: Messenger identifier of either a client or an operator
        :return: If the given user is not in conversation, `((None, None), (None, None))` is returned. Otherwise a
            tuple of two tuples is returned, where the first tuple describes the client, the second tuple describes the
            operator, and each of them consists of two `int`s, the first of which is the telegram id of a person, the
            second is the local id
        """
        with self._conn_pool.PrettyCursor() as cursor:
            # Note: no conversation locking happens here! Well, formally, this conversation is locked by
            # `_get_conversing_for_share`, but this lock is released immediately, because `get_conversing` returns and
            # the transaction commits. So there is no benefit of this locking for the outside user
            return self._get_conversing_for_share(cursor, chat_id)

    @contextmanager
    def get_conversing_with_locking(self, chat_id: int) -> Generator[Conversing, None, None]:
        """
        Just like `.get_conversing`, but is a context manager and the conversation, **if it exists**, is preserved until
        you exit the context.

        **WARNING**: this function **DOES NOT** lock a "not existing conversation": if the given user is not conversing
        at the moment when the context is entered, the conversation **can** begin, even if the context is not exited.
        Only an existing conversation gets locked.

        Example usage:
        ```
        with conversations_controller.get_conversing_with_locking(some_user_id) as \
                ((client_chat_id, client_local_id), (operator_chat_id, operator_local_id)):
            if client_chat_id is None:
                print("We think that the user is not in a conversation right now, but IT MIGHT CHANGE at any point")
            else:
                print("We are sure that the user is in a conversation, and IT WON'T CHANGE until the context is exited")
                # Can do something here, relying on who the user is in conversation with
        ```

        :param chat_id: Messenger identifier of either a client or an operator
        :return: Yields the same `.get_conversing` would return
        """
        with self._conn_pool.PrettyCursor() as cursor:
            # Unlike `get_conversing`, the "FOR SHARE" gives benefits here: the row (if it exists), which is selected in
            # `_get_conversing_for_share`, gets locked until the context is exited
            yield self._get_conversing_for_share(cursor, chat_id)

    def request_conversation(self, client_chat_id: int) -> bool:
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("INSERT INTO conversations(client_chat_id, operator_chat_id) VALUES (%s, NULL) "
                           "ON CONFLICT (client_chat_id) DO NOTHING",
                           (client_chat_id,))
            return cursor.rowcount > 0

    def begin_conversation(self, client_chat_id: int, operator_chat_id: int) -> int:
        """
        Begins a conversation between a client and an operator

        :param client_chat_id: Telegram id of the client to start conversation with
        :param operator_chat_id: Telegram id of the operator to start conversation with
        :return: If the conversation began successfully, `0` is returned. If the conversation can't begin, because the
            client is an operator in another conversation, `1` is returned. If the conversation can't begin, because the
            operator has requested a conversation, `2` is returned. If the conversation can't begin, because the
            operator is a client in another conversation, `3` is returned. If the conversation can't begin, because the
            operator is an operator already in another conversation, `4` is returned. If the conversation can't begin,
            because the client is in a conversation as a client already (another operator has already accepted the
            invitation?), `5` is returned
        """
        with self._conn_pool.PrettyCursor() as cursor:
            # Must lock the whole table, because I'm going to later rely on the fact that there is _no_
            # conversation/request with `operator_chat_id` is a client, but it's only possible to lock an _existing_
            # row, not the fact that a row doesn't exist
            cursor.execute("LOCK TABLE conversations IN SHARE MODE")

            # Ensure client is not operating (note: if client has requested a conversation, it's perfectly fine; if
            # client is a client in another conversation, this will be naturally handled later)
            another_client_chat_id, another_operator_chat_id = self.get_conversing(client_chat_id)
            if another_operator_chat_id == client_chat_id:
                # Error, client is operating
                return 1

            # Ensure operator is absolutely free
            another_client_chat_id, another_operator_chat_id = self.get_conversing(operator_chat_id)
            if another_client_chat_id is not None:
                # Error, operator is busy with something. Now check, with what exactly
                if another_operator_chat_id is None:
                    # Operator has requested a conversation
                    return 2
                elif another_client_chat_id == operator_chat_id:
                    # Operator is a client in another conversation
                    return 3
                else:
                    # Operator is an operator in another conversation
                    return 4

            # If the client is **not** waiting for a conversation, a new row will be inserted (might be a subject
            # for a change).
            # If the client **is** waiting for a conversation (i.e. `conversations.operator_chat_id IS NULL`), the
            # operator is set (`UPDATE SET operator_chat_id` happens).
            # If the client is in a conversation with an operator already, nothing happens (`UPDATE` updates 0 rows)
            cursor.execute("INSERT INTO conversations(client_chat_id, operator_chat_id) VALUES (%s, %s) "
                           "ON CONFLICT (client_chat_id) DO "
                           "    UPDATE SET operator_chat_id = excluded.operator_chat_id "
                           "           WHERE conversations.operator_chat_id IS NULL",
                           (client_chat_id, operator_chat_id))

            if cursor.rowcount > 0:
                # Success!
                return 0
            else:
                # The client is in a conversation already (another operator has accepted the invitation?)
                return 5

    def end_conversation_or_cancel_request(self, client_chat_id: int) -> Optional[int]:
        """
        If there is a conversation between the client and an operator, cancel it. If the client has requested a
        conversation, cancel the request.

        Note that this function can only be called with a client id. Operator is unable to end a conversation in the
        current implementation.

        :param client_chat_id: Messenger id of the client ending the conversation
        :return: If the client was having a conversation, his operator's chat id. If client has _only requested_ a
            conversation, `-1`. Otherwise `None`
        """
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("DELETE FROM conversations WHERE client_chat_id = %s RETURNING operator_chat_id",
                           (client_chat_id,))
            if cursor.rowcount > 0:
                return cursor.fetchone()[0] or -1

    @contextmanager
    def get_conversations_requesters_with_locking(self) -> Generator[Iterable[int], None, None]:
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("SELECT client_chat_id FROM conversations WHERE operator_chat_id IS NULL FOR SHARE")
            # Be careful: not `yield from`, because we need to yield an iterable (because of `contextmanager`)
            yield (i[0] for i in cursor.fetchall())
