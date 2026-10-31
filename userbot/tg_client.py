import argparse
import asyncio
import os
import sys

from telethon import TelegramClient, errors, utils
from telethon.tl import types as ttltypes
from telethon.tl.functions.channels import CreateChannelRequest, EditAdminRequest, InviteToChannelRequest
from telethon.tl.functions.messages import AddChatUserRequest, ExportChatInviteRequest
from telethon.tl.types import ChatAdminRights

API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
BASE = os.path.dirname(os.path.abspath(__file__))
SESSION = os.path.join(BASE, "mulhim")
BOT_USERNAME = "mulhimstudio_hr_bot"


def _client():
    return TelegramClient(
        SESSION,
        API_ID,
        API_HASH,
        device_model="MacBook Pro",
        system_version="14.5",
        app_version="10.5",
        lang_code="ar",
        system_lang_code="ar",
    )


async def _wait_for_file(path, timeout):
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    value = fh.read().strip()
            except OSError:
                value = ""
            try:
                os.remove(path)
            except OSError:
                pass
            if value:
                return value
        await asyncio.sleep(1)
    raise TimeoutError(path)


async def cmd_login(phone):
    client = _client()
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        print("ALREADY", me.id, flush=True)
        await client.disconnect()
        return
    try:
        await client.send_code_request(phone)
    except errors.FloodWaitError as exc:
        print("FLOOD_WAIT", exc.seconds, flush=True)
        return
    print("CODE_SENT", flush=True)
    try:
        code = await _wait_for_file("/tmp/tg_login_code.txt", 600)
    except TimeoutError:
        print("CODE_WAIT_TIMEOUT", flush=True)
        return
    try:
        await client.sign_in(phone=phone, code=code)
    except errors.SessionPasswordNeededError:
        print("NEEDS_2FA", flush=True)
        try:
            password = await _wait_for_file("/tmp/tg_login_2fa.txt", 600)
        except TimeoutError:
            print("2FA_WAIT_TIMEOUT", flush=True)
            return
        try:
            await client.sign_in(password=password)
        except errors.PasswordHashInvalidError:
            print("2FA_INVALID", flush=True)
            return
    except errors.PhoneCodeInvalidError:
        print("CODE_INVALID", flush=True)
        return
    except errors.PhoneCodeExpiredError:
        print("CODE_EXPIRED", flush=True)
        return
    me = await client.get_me()
    print("SIGNED_IN", me.id, me.first_name or "", flush=True)
    await client.disconnect()


async def cmd_dialogs():
    client = _client()
    await client.connect()
    if not await client.is_user_authorized():
        print("NOT_AUTHORIZED", flush=True)
        return
    async for d in client.iter_dialogs():
        if d.is_group or d.is_channel:
            kind = "channel" if d.is_channel else "group"
            print("{}\t{}\t{}".format(d.id, kind, d.title or ""), flush=True)
    await client.disconnect()


async def _resolve_chat(client, chat_id):
    target_id = int(chat_id)
    async for d in client.iter_dialogs():
        if d.id == target_id or getattr(d.entity, "id", None) == abs(target_id):
            return d.input_entity, d.entity
    raise ValueError("chat not found in dialogs: {}".format(chat_id))


async def cmd_add(chat_id, username):
    client = _client()
    await client.connect()
    if not await client.is_user_authorized():
        print("NOT_AUTHORIZED", flush=True)
        return
    target, entity = await _resolve_chat(client, chat_id)
    bot = await client.get_input_entity(username)
    is_broadcast = bool(getattr(entity, "broadcast", False))
    if isinstance(entity, ttltypes.Chat):
        try:
            await client(
                AddChatUserRequest(int(chat_id), utils.get_input_user(bot), fwd_limit=0)
            )
            print("INVITED", flush=True)
        except errors.UserAlreadyParticipantError:
            print("ALREADY_MEMBER", flush=True)
        except Exception as exc:
            print("INVITE_FAILED", type(exc).__name__, str(exc)[:300], flush=True)
    elif is_broadcast:
        rights = ChatAdminRights(
            post_messages=True,
            edit_messages=True,
            delete_messages=True,
            add_admins=False,
            ban_users=True,
            invite_users=True,
            change_info=False,
            pin_messages=True,
        )
        try:
            await client(EditAdminRequest(target, bot, rights, "Mulhim Jobs"))
            print("PROMOTED_ADMIN", flush=True)
        except errors.UserAlreadyParticipantError:
            print("ALREADY_MEMBER", flush=True)
        except Exception as exc:
            print("PROMOTE_FAILED", type(exc).__name__, str(exc)[:300], flush=True)
    else:
        try:
            await client(InviteToChannelRequest(target, [bot]))
            print("INVITED", flush=True)
        except errors.UserAlreadyParticipantError:
            print("ALREADY_MEMBER", flush=True)
        except Exception as exc:
            print("INVITE_FAILED", type(exc).__name__, str(exc)[:300], flush=True)
    await client.disconnect()


async def cmd_send(chat_id, text):
    client = _client()
    await client.connect()
    if not await client.is_user_authorized():
        print("NOT_AUTHORIZED", flush=True)
        return
    await client.send_message(chat_id, text)
    print("SENT", flush=True)
    await client.disconnect()


async def cmd_create_channel(title, about):
    client = _client()
    await client.connect()
    if not await client.is_user_authorized():
        print("NOT_AUTHORIZED", flush=True)
        return
    result = await client(
        CreateChannelRequest(title=title, about=about, broadcast=True, megagroup=False)
    )
    channel = result.chats[0]
    print("CHANNEL_ID", utils.get_peer_id(channel), flush=True)
    print("CHANNEL_TITLE", channel.title, flush=True)
    try:
        invite = await client(ExportChatInviteRequest(channel.id))
        print("INVITE", invite.link, flush=True)
    except Exception as exc:
        print("INVITE_FAILED", type(exc).__name__, str(exc)[:200], flush=True)
    await client.disconnect()


async def cmd_digest(channel):
    parent = os.path.dirname(BASE)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    from channel_digest import build_digest

    text = build_digest()
    if not text:
        print("EMPTY_DIGEST", flush=True)
        return
    target = int(channel) if channel.lstrip("-").isdigit() else channel
    client = _client()
    await client.connect()
    if not await client.is_user_authorized():
        print("NOT_AUTHORIZED", flush=True)
        return
    await client.send_message(target, text, link_preview=False, parse_mode=None)
    print("SENT", flush=True)
    await client.disconnect()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("login")
    p.add_argument("phone")
    sub.add_parser("dialogs")
    p = sub.add_parser("add")
    p.add_argument("chat_id")
    p.add_argument("username", nargs="?", default=BOT_USERNAME)
    p = sub.add_parser("send")
    p.add_argument("chat_id")
    p.add_argument("text")
    p = sub.add_parser("createchannel")
    p.add_argument("title")
    p.add_argument("--about", default="")
    p = sub.add_parser("digest")
    p.add_argument("channel")
    args = ap.parse_args()
    if args.cmd == "login":
        asyncio.run(cmd_login(args.phone))
    elif args.cmd == "dialogs":
        asyncio.run(cmd_dialogs())
    elif args.cmd == "add":
        asyncio.run(cmd_add(args.chat_id, args.username))
    elif args.cmd == "send":
        asyncio.run(cmd_send(args.chat_id, args.text))
    elif args.cmd == "createchannel":
        asyncio.run(cmd_create_channel(args.title, args.about))
    elif args.cmd == "digest":
        asyncio.run(cmd_digest(args.channel))


if __name__ == "__main__":
    main()
