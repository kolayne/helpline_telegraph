/*
 "Crying operator" is an operator, who is currently using bot as a client
 */

CREATE TABLE users
(
    chat_id     integer NOT NULL PRIMARY KEY,
    local_id    serial UNIQUE,
    is_operator BOOLEAN NOT NULL DEFAULT FALSE,
    is_admin    BOOLEAN NOT NULL DEFAULT FALSE
);

/*
 Note that unlike `send_invitations` table, `conversations` stores information about **requested conversations**, not
 invitations messages.

 `conversations.operator_chat_id` set to `NULL` indicates that the user `client_chat_id` has requested a conversation.
 Information about requests is stored in the `conversations` table, not in a separate one, to have current conversations
 and conversation requests synchronized: obviously, any user can either be waiting for a conversation or having a
 conversation, not both at the same time.
 */
CREATE TABLE conversations
(
    client_chat_id   integer NOT NULL UNIQUE REFERENCES users,
    /* `operator_chat_id` being `NULL` indicates that the client is waiting for an invitation to be accepted. */
    operator_chat_id integer UNIQUE REFERENCES users
);

/*
 Note that every message is expected to be stored twice in this table: one row has interlocutor1 and interlocutor2
 swapped.

 This **might** be a subject to refactoring: probably it would be better to store every message once and make some big
 long query (most likely hidden inside a function), which would select the "other interlocutor's" data. If you have any
 thoughts, please, file an issue!
 */
CREATE TABLE reflected_messages
(
    interlocutor1_chat_id    integer NOT NULL REFERENCES users,
    interlocutor1_message_id integer NOT NULL,
    interlocutor2_chat_id    integer NOT NULL REFERENCES users,
    interlocutor2_message_id integer NOT NULL
);

/*
 Note that `sent_invitations` only represents the **invitation messages** sent, not the fact that a user has requested
 a conversation! If you want to do something with conversation requests, use the `conversations` table.

 Indeed, say, if all the operators are busy, there are no invitations sent for any user, so the `sent_invitations` table
 is empty, however, there could still be users waiting for conversations.
 */
CREATE TABLE sent_invitations
(
    operator_chat_id      integer NOT NULL REFERENCES users,
    client_chat_id        integer NOT NULL REFERENCES users,
    invitation_message_id integer NOT NULL,
    UNIQUE (operator_chat_id, client_chat_id)
);


CREATE FUNCTION user_is_operator(integer) RETURNS boolean
AS
'SELECT is_operator
 FROM users
 WHERE chat_id = $1' LANGUAGE SQL VOLATILE;

CREATE FUNCTION operator_is_operating(integer) RETURNS boolean
AS
'SELECT exists(SELECT 1
               FROM conversations
               WHERE operator_chat_id = $1)' LANGUAGE SQL VOLATILE;

CREATE FUNCTION operator_is_crying(integer) RETURNS boolean
AS
'SELECT exists(SELECT 1
               FROM conversations
               WHERE client_chat_id = $1)'
    LANGUAGE SQL VOLATILE;


ALTER TABLE conversations
    ADD CONSTRAINT client_is_not_operating CHECK ( NOT user_is_operator(client_chat_id) OR
                                                   NOT operator_is_operating(client_chat_id) );

ALTER TABLE conversations
    ADD CONSTRAINT operator_is_operator_and_is_not_crying CHECK ( user_is_operator(operator_chat_id) AND
                                                                  NOT operator_is_crying(operator_chat_id) );

ALTER TABLE conversations
    ADD CONSTRAINT client_and_operator_are_different CHECK ( client_chat_id <> operator_chat_id );
