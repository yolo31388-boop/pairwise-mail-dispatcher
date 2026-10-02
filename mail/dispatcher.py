"""邮件分发"""
import threading
import time
from dataclasses import dataclass, field

MAX_OFFLINE_MAIL = 100
MAIL_EXPIRE_DAYS = 30
SYSTEM_MAIL_BATCH_SIZE = 1000


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
    timestamp: float = field(default_factory=time.time)


class MailDispatcher:
    def __init__(self):
        self.online_players: set = set()
        self.offline_mail: dict[str, list] = {}
        self.sent_mail: dict[str, Mail] = {}
        self.batch_sizes: list[int] = []
        self._lock = threading.RLock()

    def send_mail(self, mail: Mail) -> bool:
        # 事务保证：在线状态检查与投递/落库在同一把锁内完成，
        # 与玩家上线流程互斥，邮件要么在线投递，要么存入离线，不会丢。
        with self._lock:
            if mail.receiver in self.online_players:
                self.sent_mail[mail.mid] = mail
                return True
            box = self.offline_mail.setdefault(mail.receiver, [])
            box.append(mail)
            if len(box) > MAX_OFFLINE_MAIL:
                del box[: len(box) - MAX_OFFLINE_MAIL]
            return True

    def player_login(self, pid: str) -> list:
        # 玩家上线：与 send_mail 互斥，原子地把离线邮件搬到已投递队列，
        # 解决“发送过程中刚好上线”导致的邮件丢失。
        with self._lock:
            self.online_players.add(pid)
            mails = self.offline_mail.pop(pid, [])
            for mail in mails:
                self.sent_mail[mail.mid] = mail
            return mails

    def player_logout(self, pid: str) -> None:
        with self._lock:
            self.online_players.discard(pid)

    go_online = player_login
    go_offline = player_logout

    def _find_mail(self, pid: str, mail_id: str):
        mail = self.sent_mail.get(mail_id)
        if mail is not None and mail.receiver == pid:
            return mail
        for candidate in self.offline_mail.get(pid, []):
            if candidate.mid == mail_id:
                return candidate
        return None

    def clean_expired_mail(self, pid: str) -> int:
        # 清理已领取、超过 30 天的邮件，并强制数量上限。
        with self._lock:
            box = self.offline_mail.get(pid, [])
            cutoff = time.time() - MAIL_EXPIRE_DAYS * 86400
            kept = [
                mail
                for mail in box
                if not mail.claimed and mail.timestamp >= cutoff
            ]
            if len(kept) > MAX_OFFLINE_MAIL:
                kept = kept[-MAX_OFFLINE_MAIL:]
            removed = len(box) - len(kept)
            if kept:
                self.offline_mail[pid] = kept
            else:
                self.offline_mail.pop(pid, None)
            return removed

    def claim_attachment(self, pid: str, mail_id: str) -> bool:
        # 必须是本人的、已读的、带附件且未领取过的邮件才能领取。
        with self._lock:
            mail = self._find_mail(pid, mail_id)
            if mail is None or mail.claimed:
                return False
            if not mail.attachment or not mail.read:
                return False
            mail.claimed = True
            return True

    def send_system_mail(self, mails: list) -> int:
        # 分批发送，每批短暂持锁，避免一次性群发锁死数据库。
        mails = list(mails)
        sent = 0
        for start in range(0, len(mails), SYSTEM_MAIL_BATCH_SIZE):
            batch = mails[start : start + SYSTEM_MAIL_BATCH_SIZE]
            self.batch_sizes.append(len(batch))
            with self._lock:
                for mail in batch:
                    if self.send_mail(mail):
                        sent += 1
        return sent

    def mark_as_read(self, pid: str, mail_id: str) ->bool:
        # 已读状态直接写到服务端存储（含离线邮件），换设备登录状态仍在。
        with self._lock:
            mail = self._find_mail(pid, mail_id)
            if mail is None:
                return False
            mail.read = True
            return True
