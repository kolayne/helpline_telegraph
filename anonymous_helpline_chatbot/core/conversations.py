from contextlib import contextmanager
from typing import Union, Tuple, Optional, Generator, Iterable

from .db_connector import DatabaseConnectionPool, cursor_type


Conversing = Union[Tuple[int, Optional[int]], Tuple[None, None]]


class ConversationsController:
    def __init__(self, database_connection_pool: DatabaseConnectionPool):
        self._conn_pool = database_connection_pool

    @contextmanager
    def lock_conversations_and_requests_list(self) -> Generator[None, None, None]:
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("LOCK TABLE conversations IN SHARE MODE")
            yield

    @staticmethod
    def _get_conversing_for_share(cursor: cursor_type, chat_id: int) -> Conversing:
        """
        Just like `.get_conversing` (see below), but accepts `cursor`, which is a database cursor, and retrieves
        the ids using that cursor with the `SELECT FOR SHARE` query. Thus, if the conversation exists, it is guaranteed
        to not be finished at least until the current transaction of `cursor` is finished (or rolled back to a
        savepoint). **WARNING**: it is NOT guaranteed that a conversation won't start if it doesn't exist at the moment
        of a function call
        """
        cursor.execute("SELECT client_chat_id, operator_chat_id FROM conversations "
                       "WHERE client_chat_id = %s OR operator_chat_id = %s "
                       "FOR SHARE",
                       (chat_id, chat_id))
        return cursor.fetchone() or (None, None)

    def get_conversing(self, chat_id: int) -> Conversing:
        """
        Get client and operator from a conversation in which the user with the given identifier takes part

        Retrieves messenger identifiers of both client and operator of the conversation, in which the
        given user takes part. This function can be used for understanding whether current user is a client or an
        operator in his conversation, retrieving information about his interlocutor, etc

        Warning: if your application is working in a multi-threaded environment (which is extremely likely), the
        conversations should sometimes be started or finished by parallel threads, therefore it's not thread-safe
        to rely on the information returned by this function, if no locking is used, because it might change at any
        point, probably even before you have a chance to process the returned value. That's why it is highly recommended
        to only use this function together with the `.lock_conversations_and_requests_list` context manager (or use
        `.get_conversing_with_plocking` instead of this one, see below). For example,

        ```
        # WRONG!!!
        _, operator_chat_id = conversations_controller.get_conversing(some_user_chat_id)
        if operator_chat_id is None:
            # Another thread might have already created a conversation with that user, so we rely on outdated data
            print("User is not in a conversation")  # Who knows???
        ```

        ```
        # CORRECT
        with conversations_controller.lock_conversations_and_requests_list():
            # While we're inside of this block, no conversations can start or finish. All the threads trying to modify
            # conversations or requests will have to wait for this context to be exited
            _, operator_chat_id = conversations_controller.get_conversing(some_user_chat_id)
            if operator_chat_id is None:
                print("User is not in a conversation")
                # Do something, relying on this fact
            else:
                print("User is in a conversation")
                # Do something, relying on this fact

            # If there was only the `else` part, and we didn't want to fixate the "not existing" state of a
            # conversation, it would be better to use `conversations_controller.get_conversing_with_plocking` (see
            # below)
        ```

        Also note that if you only need to do something if a conversation or request **does** exist for the given user,
        but you don't need to rely on the fact, that a conversation **doesn't** exist, it's recommended to use
        the `.get_conversing_with_plocking` method - instead of `.get_conversing` in conjunction with
        `.lock_conversations_and_requests_list` - because
        the latter method locks all the conversations entirely, which leads to all the threads trying to begin/end
        conversations or send/remove a conversation request to pause and wait for the thread calling the method to
        release the lock (which happens when the context of `.lock_conversations_and_requests_list` context manager is
        exited). Partially locking functions work differently (please, see the documentation of the appropriate method
        for details!)

        :param chat_id: Messenger identifier of either a client or an operator
        :return: If the given user is in a conversation, `(client_chat_id, operator_chat_id)` is returned. Otherwise, if
            the user has requested a conversation, `(chat_id, None)` is returned. Otherwise `(None, None)` is returned.
        """
        with self._conn_pool.PrettyCursor() as cursor:
            # Note: no conversation locking happens here! Well, formally, this conversation is locked by
            # `_get_conversing_for_share`, but this lock is released immediately, because `get_conversing` returns and
            # the transaction commits. So there is no benefit of this locking for the outside user
            return self._get_conversing_for_share(cursor, chat_id)

    @contextmanager
    def get_conversing_with_plocking(self, chat_id: int) -> Generator[Conversing, None, None]:
        """
        Just like `.get_conversing`, but is a context manager and the conversation, **if it exists**, is preserved until
        the context is exited.

        "plocking" stands for partial locking, which means that not all the conversations, but (in this case) only
        one conversation/request's state is locked (if it exists).

        **WARNING**: this function **DOES NOT** lock a "not existing conversation": if the given user is not conversing
        at the moment when the context is entered, the conversation **can** begin, even before the context is exited.
        Only an existing conversation gets locked.
        If you want a non-existing conversation to be locked in that state, use the `.get_conversing` method together
        with `.lock_conversations_and_requests_list` instead

        Example usage:
        ```
        with conversations_controller.get_conversing_with_locking(some_user_id) as (client_chat_id, operator_chat_id):
            if client_chat_id is None:
                print("We think that the user is not in a conversation right now, but THIS MIGHT CHANGE at any point")
            else:
                print("We are sure that the user is in a conversation or has requested it (can be distinguished based "
                      "on `operator_chat_id`), and THIS WON'T CHANGE until the context is exited")
                # Can do something here, relying on who the user is in conversation with
        ```

        :param chat_id: Messenger identifier of either a client or an operator
        :return: Returns the same `.get_conversing` would return
        """
        with self._conn_pool.PrettyCursor() as cursor:
            # Unlike `get_conversing`, the "FOR SHARE" gives benefits here: the row (if it exists), which is selected in
            # `_get_conversing_for_share`, gets locked until the context is exited
            yield self._get_conversing_for_share(cursor, chat_id)

    @contextmanager
    def request_conversation_with_locking(self, client_chat_id: int) -> Generator[int, None, None]:
        # To the docs: `0` is ok, `1` is requested already, `2` is in a conversation already
        with self._conn_pool.PrettyCursor() as cursor:
            # Lock in order to rely on the fact that client is not in a conversation
            cursor.execute("LOCK TABLE conversations IN SHARE MODE")

            another_client_chat_id, another_operator_chat_id = self.get_conversing(client_chat_id)
            if another_client_chat_id is None:
                cursor.execute("INSERT INTO conversations(client_chat_id, operator_chat_id) VALUES (%s, NULL) ",
                               (client_chat_id,))
                yield 0
            elif another_operator_chat_id is None:
                yield 1
            else:
                yield 2

    @contextmanager
    def begin_conversation_with_locking(self, client_chat_id: int, operator_chat_id: int) -> Generator[int, None, None]:
        """
        Context manager, which begins a conversation between a client and an operator, and guarantees, that no other
        conversations begin or end and no conversation requests are handled before the context is exited.

        :param client_chat_id: Messenger id of the client to start conversation with
        :param operator_chat_id: Messenger id of the operator to start conversation with
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
            # conversation/request with `operator_chat_id` as a client, but it's only possible to lock an _existing_
            # row, not the fact that a row doesn't exist, without locking the whole table
            cursor.execute("LOCK TABLE conversations IN SHARE MODE")

            # Ensure client is not operating (note: if client has requested a conversation, it's perfectly fine; if
            # client is a client in another conversation, this will be naturally handled later)
            another_client_chat_id, another_operator_chat_id = self.get_conversing(client_chat_id)
            if another_operator_chat_id == client_chat_id:
                # Error, client is operating
                yield 1
                return

            # Ensure operator is absolutely free
            another_client_chat_id, another_operator_chat_id = self.get_conversing(operator_chat_id)
            if another_client_chat_id is not None:
                # Error, operator is busy with something. Now check, with what exactly
                if another_operator_chat_id is None:
                    # Operator has requested a conversation
                    yield 2
                    return
                elif another_client_chat_id == operator_chat_id:
                    # Operator is a client in another conversation
                    yield 3
                    return
                else:
                    # Operator is an operator in another conversation
                    yield 4
                    return

            """
            Explanation of the query below:
            - If the client is **not** waiting for a conversation, a new row will be inserted (this behavior might be
                a subject for a change).
            - If the client **is** waiting for a conversation (i.e. `conversations.operator_chat_id IS NULL`), the
                operator is set (`UPDATE SET operator_chat_id` happens).
            - If the client is in a conversation with an operator already, nothing happens (`UPDATE` updates 0 rows
                because of `WHERE`)
            """
            cursor.execute("INSERT INTO conversations(client_chat_id, operator_chat_id) VALUES (%s, %s) "
                           "ON CONFLICT (client_chat_id) DO "
                           "    UPDATE SET operator_chat_id = excluded.operator_chat_id "
                           "           WHERE conversations.operator_chat_id IS NULL",
                           (client_chat_id, operator_chat_id))

            if cursor.rowcount > 0:
                # Success!
                yield 0
            else:
                # The client is in a conversation already (another operator has accepted the invitation?)
                yield 5

    @contextmanager
    def end_conversation_or_cancel_request_with_plocking(self,
                                                         client_chat_id: int) -> Generator[Optional[int], None, None]:
        """
        Context manager, which finishes a conversation where the user `client_chat_id` is a client (if such conversation
        exists),
        or cancels the conversation request sent by the user (if the request exists). Actions performed in the context of this
        context manager are treated as a part of the conversation ending (request cancellation) process in the sense that
        it's guaranteed that other threads trying to query information about the conversation/request will keep getting the
        old data (as if conversation/request would still exist) until the context is exited, and threads trying to anyhow
        modify the conversation/request's state will be paused until the context is exited.
        Technically, this is achieved by the `DELETE` query being performed _before_ the context is entered, but the
        transaction being committed committed _after_ the context is exited.

        "plocking" stands for partial locking, which means that not all the conversations, but (in this case) only
        one conversation/request's state is locked (if it exists).

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
                yield cursor.fetchone()[0] or -1
            else:
                yield None

    @contextmanager
    def get_conversations_requesters_with_plocking(self) -> Generator[Iterable[int], None, None]:
        with self._conn_pool.PrettyCursor() as cursor:
            cursor.execute("SELECT client_chat_id FROM conversations WHERE operator_chat_id IS NULL FOR SHARE")
            # Be careful: not `yield from`, because we need to yield an iterable (because of `contextmanager`)
            yield (i[0] for i in cursor.fetchall())
