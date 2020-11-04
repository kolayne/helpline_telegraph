import psycopg2.errors

from db_connector import PrettyCursor


def start_conversation(tg_id: int) -> str:
    """Start conversation with an operator

    :param tg_id: Telegram id of the user starting a conversation
    :return: One of the strings: `'ok'`: the conversation has been started successfully, `'not a client'`: an operator
            has requested a conversation, `'conversation already exists'`: the previous conversation is not finished
    """
    with PrettyCursor() as cursor:
        try:
            cursor.execute("INSERT INTO conversations(client_id, operator_id) SELECT "
                           "(SELECT id FROM users WHERE tg_id=%s), id FROM users "
                           "WHERE type='operator' ORDER BY random() LIMIT 1", (tg_id,))
        except psycopg2.errors.UniqueViolation:
            return 'conversation already exists'
        except psycopg2.errors.CheckViolation:
            return 'not a client'
        else:
            return 'ok'
