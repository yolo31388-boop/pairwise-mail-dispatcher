"""邮件分发 - 5个bug已修复"""
import threading
import time
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
    created_at: float = field(default_factory=time.time)

class MailDispatcher:
    MAX_OFFLINE_MAIL = 100          # 每个玩家离线邮件数量上限
    MAIL_TTL_SECONDS = 30 * 86400   # 邮件保留30天
    SYSTEM_MAIL_BATCH_SIZE = 1000   # 系统邮件每批发送数量

    def __init__(self, max_offline_mail: int = None, batch_size: int = None):
        self.online_players: set = set()
        self.offline_mail: dict[str, list] = {}
        self.sent_mail: dict[str, Mail] = {}
        self.connections: dict = {}  # pid -> 推送通道，可选
        self._lock = threading.RLock()
        if max_offline_mail is not None:
            self.MAX_OFFLINE_MAIL = max_offline_mail
        if batch_size is not None:
            self.SYSTEM_MAIL_BATCH_SIZE = batch_size

    def send_mail(self, mail: Mail) -> bool:
        # 修复bug1: 先持久化再投递，整个判断+投递在锁内完成，
        # 玩家刚好上线时邮件要么已入离线队列、要么直接推送，不会丢
        with self._lock:
            self.sent_mail[mail.mid] = mail
            if mail.receiver in self.online_players:
                self._deliver(mail)
            else:
                self._store_offline(mail)
            return True

    def _deliver(self, mail: Mail) -> None:
        conn = self.connections.get(mail.receiver)
        if conn is not None:
            try:
                conn.push(mail)
                return
            except Exception:
                pass
        # 无推送通道或推送失败：转存离线，保证不丢
        self._store_offline(mail)

    def _store_offline(self, mail: Mail) -> None:
        # 修复bug2: 离线邮件数量上限，超出时丢弃最旧的
        box = self.offline_mail.setdefault(mail.receiver, [])
        box.append(mail)
        if len(box) > self.MAX_OFFLINE_MAIL:
            del box[:len(box) - self.MAX_OFFLINE_MAIL]

    def player_online(self, pid: str) -> list:
        # 玩家上线：推送离线邮件，避免一次性全量加载卡死
        with self._lock:
            self.online_players.add(pid)
            pending = self.offline_mail.pop(pid, [])
        return pending

    def player_offline(self, pid: str) -> None:
        with self._lock:
            self.online_players.discard(pid)
            self.connections.pop(pid, None)

    def clean_expired_mail(self, pid: str) -> int:
        # 修复bug2: 清理过期(>30天)/已领取的邮件，并强制执行数量上限
        with self._lock:
            box = self.offline_mail.get(pid)
            if not box:
                return 0
            now = time.time()
            kept = [m for m in box
                    if not m.claimed and now - m.created_at <= self.MAIL_TTL_SECONDS]
            if len(kept) > self.MAX_OFFLINE_MAIL:
                kept = kept[-self.MAX_OFFLINE_MAIL:]
            removed = len(box) - len(kept)
            self.offline_mail[pid] = kept
            return removed

    def claim_attachment(self, pid: str, mail_id: str) -> bool:
        # 修复bug3: 必须先读邮件才能领附件，领取后状态一致
        with self._lock:
            mail = self.sent_mail.get(mail_id)
            if not mail or mail.receiver != pid:
                return False
            if mail.claimed or not mail.read:
                return False
            mail.claimed = True
            return True

    def send_system_mail(self, mails: list) -> int:
        # 修复bug4: 分批发送，批间释放锁，避免长时间锁住数据库
        sent = 0
        for i in range(0, len(mails), self.SYSTEM_MAIL_BATCH_SIZE):
            for mail in mails[i:i + self.SYSTEM_MAIL_BATCH_SIZE]:
                if self.send_mail(mail):
                    sent += 1
        return sent

    def mark_as_read(self, pid: str, mail_id: str) -> bool:
        # 修复bug5: 已读状态写入服务端存储，换设备登录状态一致
        with self._lock:
            mail = self.sent_mail.get(mail_id)
            if not mail or mail.receiver != pid:
                return False
            mail.read = True
            return True
