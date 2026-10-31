import os
import tempfile
import unittest

os.environ.setdefault(
    "MULHIM_DB", os.path.join(tempfile.gettempdir(), "mulhim_test.db")
)

import bot


class FakeMessage:
    message_id = 55

    def __init__(self):
        self.replies = []

    async def reply_text(self, text, reply_to_message_id=None, reply_markup=None):
        self.replies.append(
            {
                "text": text,
                "reply_to": reply_to_message_id,
                "markup": reply_markup,
            }
        )


class FakeChat:
    def __init__(self, chat_id=-100111, chat_type="supergroup"):
        self.id = chat_id
        self.type = chat_type


class FakeUpdate:
    def __init__(self, chat=None):
        self.effective_chat = chat or FakeChat()
        self.message = FakeMessage()


class FakeContext:
    def __init__(self):
        self.bot_data = {}


class GroupReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_replies_to_job_keyword(self):
        update = FakeUpdate()
        ctx = FakeContext()
        await bot.group_auto_reply(update, ctx, "مطلوب موظف محاسب ببغداد")
        self.assertEqual(len(update.message.replies), 1)
        reply = update.message.replies[0]
        self.assertEqual(reply["reply_to"], 55)
        self.assertIn("بوت ملهم", reply["text"])
        markup = reply["markup"]
        urls = [b.url for row in markup.inline_keyboard for b in row]
        self.assertIn(bot.BOT_LINK + "?start=jobs", urls)
        self.assertIn(bot.BOT_LINK + "?start=company", urls)

    async def test_ignores_plain_text(self):
        update = FakeUpdate()
        ctx = FakeContext()
        await bot.group_auto_reply(update, ctx, "مرحبا جميعاً")
        self.assertEqual(update.message.replies, [])

    async def test_ignores_own_link(self):
        update = FakeUpdate()
        ctx = FakeContext()
        await bot.group_auto_reply(update, ctx, "شوفو " + bot.BOT_LINK)
        self.assertEqual(update.message.replies, [])

    async def test_cooldown_per_chat(self):
        update1 = FakeUpdate(chat=FakeChat(chat_id=-1001))
        ctx = FakeContext()
        await bot.group_auto_reply(update1, ctx, "وظيفة شاغرة")
        update2 = FakeUpdate(chat=FakeChat(chat_id=-1001))
        await bot.group_auto_reply(update2, ctx, "وظيفة شاغرة")
        self.assertEqual(len(update1.message.replies), 1)
        self.assertEqual(update2.message.replies, [])
        update3 = FakeUpdate(chat=FakeChat(chat_id=-1002))
        await bot.group_auto_reply(update3, ctx, "وظيفة شاغرة")
        self.assertEqual(len(update3.message.replies), 1)

    async def test_cooldown_bypass_after_window(self):
        update = FakeUpdate(chat=FakeChat(chat_id=-1003))
        ctx = FakeContext()
        await bot.group_auto_reply(update, ctx, "hiring")
        ctx.bot_data["group_auto_reply_ts"]["-1003"] -= (
            bot.GROUP_REPLY_COOLDOWN + 1
        )
        update2 = FakeUpdate(chat=FakeChat(chat_id=-1003))
        await bot.group_auto_reply(update2, ctx, "hiring")
        self.assertEqual(len(update2.message.replies), 1)


if __name__ == "__main__":
    unittest.main()
