CREATE TYPE user_type AS ENUM ('client', 'operator');

CREATE TABLE users
(
    tg_id    integer   NOT NULL PRIMARY KEY,
    local_id serial UNIQUE,
    type     user_type NOT NULL
);

CREATE FUNCTION user_is_operator(integer) RETURNS boolean
AS
'SELECT type = ''operator''
 FROM users
 WHERE tg_id = $1' LANGUAGE SQL VOLATILE;

CREATE TABLE conversations
(
    client_id   integer NOT NULL UNIQUE REFERENCES users CHECK ( not user_is_operator(client_id) ),
    operator_id integer NOT NULL REFERENCES users CHECK ( user_is_operator(operator_id) )
);

CREATE TABLE reflected_messages
(
    sender_chat_id      integer NOT NULL REFERENCES users (tg_id),
    sender_message_id   integer NOT NULL,
    receiver_chat_id    integer NOT NULL REFERENCES users (tg_id),
    receiver_message_id integer NOT NULL
);
