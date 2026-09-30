"""邮件分发 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mail.dispatcher import MailDispatcher, Mail

class TestNoMailLoss:
    def test_mail_stored_when_player_comes_online(self):
        md = MailDispatcher()
        mail = Mail("m1", "sys", "p1", "test", "body")
        md.send_mail(mail)
        md.online_players.add("p1")
        # 邮件应该还能找到
        assert "p1" in md.offline_mail or mail.mid in md.sent_mail

class TestOfflineMailLimit:
    def test_offline_mail_has_max_count(self):
        md = MailDispatcher()
        for i in range(1000):
            mail = Mail(f"m{i}", "sys", "p1", "test", "body")
            md.send_mail(mail)
        assert len(md.offline_mail.get("p1", [])) <= 100

class TestClaimRequiresRead:
    def test_cannot_claim_unread_mail_attachment(self):
        md = MailDispatcher()
        mail = Mail("m1", "sys", "p1", "test", "body", attachment={"gold": 100}, read=False)
        md.sent_mail["m1"] = mail
        assert md.claim_attachment("p1", "m1") == False

class TestBatchSystemMail:
    def test_system_mail_sent_in_batches(self):
        md = MailDispatcher()
        mails = [Mail(f"m{i}", "sys", f"p{i}", "test", "body") for i in range(100)]
        count = md.send_system_mail(mails)
        assert count == 100

class TestReadSync:
    def test_read_status_synced_to_server(self):
        md = MailDispatcher()
        mail = Mail("m1", "sys", "p1", "test", "body")
        md.sent_mail["m1"] = mail
        md.mark_as_read("p1", "m1")
        assert md.sent_mail["m1"].read == True
