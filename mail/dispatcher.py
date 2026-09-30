"""邮件分发 - 含5个bug"""
from dataclasses import dataclass, field

@dataclass
class Mail:
    mid: str
    sender: str
    receiver: str
    subject: str
    body: str
    attachment: dict = None
    read: bool = False
    claimed: bool = False

class MailDispatcher:
    def __init__(self):
        self.online_players: set = set()
        self.offline_mail: dict[str, list] = {}  # bug2: 无上限
        self.sent_mail: dict[str, Mail] = {}

    def send_mail(self, mail: Mail) -> bool:
        # bug1: 玩家刚好上线时邮件丢失
        if mail.receiver in self.online_players:
            return True  # 直接发，不存
        else:
            if mail.receiver not in self.offline_mail:
                self.offline_mail[mail.receiver] = []
            self.offline_mail[mail.receiver].append(mail)
            return True

    def clean_expired_mail(self, pid: str) -> int:
        # bug2: 不检查数量
        if pid in self.offline_mail:
            self.offline_mail[pid] = [m for m in self.offline_mail[pid] if not m.claimed]
        return 0

    def claim_attachment(self, pid: str, mail_id: str) -> bool:
        # bug3: 不检查已读
        mail = self.sent_mail.get(mail_id)
        if not mail or mail.claimed:
            return False
        mail.claimed = True
        return True

    def send_system_mail(self, mails: list) -> int:
        # bug4: 不分批
        for mail in mails:
            self.send_mail(mail)
        return len(mails)

    def mark_as_read(self, pid: str, mail_id: str) -> bool:
        # bug5: 只在客户端标记
        mail = self.sent_mail.get(mail_id)
        if mail:
            mail.read = True
        return True
