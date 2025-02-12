import secrets


def generate_token():
    return secrets.token_hex(16)


def get_active_username(token):
    from resources import session_table
    from aws_lambda_powertools.event_handler.exceptions import UnauthorizedError

    try:
        res = session_table.get_item(Key={"Token": token})
        return res["Item"]["Username"]
    except:
        raise UnauthorizedError("Session not found")


def get_session_token(app):
    from aws_lambda_powertools.event_handler.exceptions import UnauthorizedError

    try:
        return app.current_event.headers["x-session-token"]
    except KeyError:
        raise UnauthorizedError("Session token not found")
