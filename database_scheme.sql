CREATE TYPE user_type AS ENUM ('client', 'operator');

CREATE TABLE users
(
    id    serial PRIMARY KEY,
    tg_id integer   NOT NULL UNIQUE,
    type  user_type NOT NULL
);

CREATE TABLE conversations
(
    client_id   integer NOT NULL UNIQUE REFERENCES users,
    operator_id integer NOT NULL REFERENCES users
);

CREATE TABLE reflected_messages
(
    sender_chat_id      integer NOT NULL REFERENCES users (tg_id),
    sender_message_id   integer NOT NULL,
    receiver_chat_id    integer NOT NULL REFERENCES users (tg_id),
    receiver_message_id integer NOT NULL
);
