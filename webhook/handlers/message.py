# -*- coding: utf-8 -*-
from datetime import datetime

import redis

from common.azfunc_helper import write_http_response
from common.fb_message import send_fb_message, send_buttons
from common.config import REDIS_HOST, REDIS_PASSWD
from common.azure_db import Options, Vote, Sensors


def is_processed(id):
    # this function is used to avoid responses duplication:
    # facebook resend events to the webhook if doesn't get 200 response in 20 seconds
    # so on function cold start bot may get duplicated messages
    redis_client = redis.StrictRedis(host=REDIS_HOST, port=6380, password=REDIS_PASSWD, ssl=True, db=0)
    if not redis_client.get(id):
        redis_client.set(id, "1")
        redis_client.expire(id, 90)  # expire in 1.5 minutes
        return False
    return True


def handle_message(data):
    """
    Handle message
    :param data: data that comes from sender
    :return: status of response '200'
    """
    if data.get("object") == "page":
        for webhook_event in [entry["messaging"][0] for entry in data.get("entry") if "messaging" in entry]:
            # from request get postback
            postback = webhook_event.get("postback", {})
            # from request get recipient id
            sender_psid = webhook_event["sender"]["id"]
            timestamp = webhook_event.get("timestamp")
            # from request get message
            message = webhook_event.get("message", {})

            if message.get("quick_reply") and not is_processed(message["mid"]):

                # handle sender's choice
                result_vote = Vote.get_user_vote_or_empty(sender_psid)
                result_vote["vote"] = message["text"]
                result_vote["payload"] = message["quick_reply"]["payload"]
                result_vote["sender_id"] = sender_psid
                result_vote["timestamp"] = str(datetime.now())
                Vote.upsert_docs(result_vote)
                send_buttons(sender_psid)

            # handle start button
            elif postback and not is_processed("{}{}".format(sender_psid, timestamp)):
                if postback.get("payload") == "get_started":
                    send_buttons(sender_psid)

                # handle vote
                elif postback.get("payload") == "vote":
                    message_body = {
                        "text": "🌿 What should I do with the plant?",
                        "quick_replies": Options.QUICK_REPLIES
                    }
                    send_fb_message(sender_psid, message_body)

                # handle results of voting
                elif postback.get("payload") == "voting_result":
                    message_body = {"text": Vote.get_voting_results()}
                    send_fb_message(sender_psid, message_body)
                    send_buttons(sender_psid)

                # handle sensors
                elif postback.get("payload") == "sensors_latest":
                    message_body = {"text": Sensors.get_latest_data()}
                    send_fb_message(sender_psid, message_body)
                    send_buttons(sender_psid)

            # handle any text from sender
            elif message.get("text") and not is_processed(message["mid"]):
                send_buttons(sender_psid)

    # notify facebook that message is received
    write_http_response(200)
